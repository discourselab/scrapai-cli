"""
Scrapy download handler for Cloudflare-protected sites.

This handler uses a hybrid approach:
1. A central browser verifies CF once per host (cookies are per-hostname) to get
   the CF cookie. Verification is held at one gate, so concurrent requests never
   drive the browser at the same time.
2. Fast concurrent HTTP requests with the cached cookie for everything else.
3. Reactive (not time-based) reverify: only when a host has no cookie yet, or an
   HTTP response comes back blocked. On a block, all requests hold, ONE
   reverifies, everyone retries with the fresh cookie — so a transient cookie
   death pauses briefly instead of failing requests.

Strategies:
- 'hybrid': Browser once per host + HTTP with cookies (fast, default)
- 'browser_only': Browser for every request (slow, legacy)
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Optional
from urllib.parse import urlparse

from scrapy.http import HtmlResponse, Request, XmlResponse
from twisted.internet import threads
from settings import USER_AGENT

logger = logging.getLogger(__name__)


def _make_response(url: str, body: str, request):
    """Pick the right Scrapy response class based on URL pattern.

    Scrapy's SitemapSpider only treats responses as sitemaps when they're
    XmlResponse instances (or url.endswith('.xml')) — paginated sitemap URLs
    like `sitemap.xml?page=1` fail the URL check, so we route by pattern here.
    """
    u = url.lower().split("?", 1)[0]
    is_xml = u.endswith(".xml") or "/sitemap" in u
    cls = XmlResponse if is_xml else HtmlResponse
    return cls(url=url, body=body.encode("utf-8"), encoding="utf-8", request=request)


def _start_event_loop(loop):
    """Run event loop forever in a dedicated thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


class CloudflareDownloadHandler:
    """
    Hybrid Cloudflare handler with cookie caching.

    Strategies:
    1. HYBRID (default, fast):
       - Browser verification once per 25 minutes
       - HTTP requests with cached cookies
       - 20-100x faster than browser-only

    2. BROWSER_ONLY (legacy, slow):
       - Browser for every request
       - Most reliable, but slow

    Cookie Management:
    - Cookies cached per spider + host
    - Reactive reverify (no timer): on first hit of a host, or on a blocked
      response — held at one gate so the browser runs once

    Settings:
    - CLOUDFLARE_STRATEGY: 'hybrid' or 'browser_only' (default: 'hybrid')
    """

    lazy = True  # Scrapy lazy loading attribute

    # Class-level (shared) browser state
    _shared_browser = None
    _browser_started = False
    _browser_startup_lock = threading.Lock()  # Protect browser startup (1 at a time)

    # Expert-in-the-loop: residential proxy flagged for production crawl approval
    _residential_available = False
    _residential_url = None

    # Persistent event loop for all async browser operations
    # All asyncio.Lock and browser calls run on this single loop,
    # avoiding "bound to a different event loop" errors with concurrent requests.
    _event_loop = None
    _event_loop_thread = None
    _event_loop_lock = threading.Lock()

    # Cookie cache keyed by "<spider>|<host>" — CF cookies are per-hostname, so
    # each host (www., hemeroteca., …) verifies independently.
    # Value: {'cookies': {}, 'user_agent': str, 'seq': int, ...}
    _cookie_cache: Dict[str, Dict] = {}
    _cookie_cache_lock = threading.Lock()
    _refresh_lock = None  # Async lock: holds all requests during one reverify
    _cookie_seq = 0  # monotonic; identifies a cookie generation for the gate

    @staticmethod
    def _cache_key(spider_name, url):
        """Per-spider, per-host cookie key."""
        return f"{spider_name}|{urlparse(url).hostname}"

    def __init__(self, settings, crawler=None):
        """Initialize the handler.

        Args:
            settings: Scrapy settings
            crawler: Scrapy crawler instance
        """
        self.settings = settings
        self.crawler = crawler
        self.loop = None

    @classmethod
    def from_crawler(cls, crawler):
        """Create handler from crawler (Scrapy convention)."""
        return cls(crawler.settings, crawler)

    @classmethod
    def _get_event_loop(cls):
        """Get or create the persistent event loop (thread-safe)."""
        with cls._event_loop_lock:
            if cls._event_loop is None or cls._event_loop.is_closed():
                cls._event_loop = asyncio.new_event_loop()
                cls._event_loop_thread = threading.Thread(
                    target=_start_event_loop,
                    args=(cls._event_loop,),
                    daemon=True,
                    name="cf-event-loop",
                )
                cls._event_loop_thread.start()
                logger.info(
                    "CloudflareDownloadHandler: Started persistent event loop thread"
                )
            return cls._event_loop

    @classmethod
    def _run_async(cls, coro):
        """Run a coroutine on the persistent event loop from any thread.

        Raises:
            TimeoutError: If browser operation takes longer than 300 seconds
        """
        loop = cls._get_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=300)  # 5 minute timeout
        except TimeoutError:
            logger.error(
                "Browser operation timed out after 300 seconds. "
                "This may indicate browser subprocess hung or network issues."
            )
            raise
        except Exception as e:
            logger.error(f"Browser operation failed: {e}")
            raise

    def open(self):
        """Called when spider opens - prepare handler."""
        # Browser will be started lazily on first request
        logger.info(
            "CloudflareDownloadHandler: Handler opened (browser will start on first request)"
        )

    async def close(self, spider=None):
        """Close browser, drop this spider's cookies, and stop the event loop.

        Each cleanup step is in its own try/finally so a failure earlier in
        the sequence (e.g. browser hang) still releases the event loop and
        the daemon thread that hosts it. Otherwise we'd leak a Chromium
        subprocess on every spider that crashed during shutdown.
        """
        try:
            if (
                CloudflareDownloadHandler._browser_started
                and CloudflareDownloadHandler._shared_browser
            ):
                logger.info("CloudflareDownloadHandler: Closing shared browser...")
                if CloudflareDownloadHandler._shared_browser.browser:
                    try:
                        await asyncio.get_running_loop().run_in_executor(
                            None, lambda: self._run_async(self._stop_browser_async())
                        )
                        logger.info("CloudflareDownloadHandler: Browser stopped")
                    except Exception as e:
                        logger.warning(f"Error during browser cleanup: {e}")
                CloudflareDownloadHandler._shared_browser = None
                CloudflareDownloadHandler._browser_started = False
            else:
                logger.info("CloudflareDownloadHandler: No browser to close")
        finally:
            spider_name = getattr(spider, "name", None) or getattr(
                spider, "spider_name", None
            )
            if spider_name:
                with CloudflareDownloadHandler._cookie_cache_lock:
                    if spider_name in CloudflareDownloadHandler._cookie_cache:
                        del CloudflareDownloadHandler._cookie_cache[spider_name]
                        logger.info(
                            f"CloudflareDownloadHandler: Dropped cookie cache for "
                            f"{spider_name}"
                        )

            if (
                CloudflareDownloadHandler._event_loop
                and not CloudflareDownloadHandler._event_loop.is_closed()
            ):
                CloudflareDownloadHandler._event_loop.call_soon_threadsafe(
                    CloudflareDownloadHandler._event_loop.stop
                )
                CloudflareDownloadHandler._event_loop = None
                CloudflareDownloadHandler._event_loop_thread = None
                logger.info("CloudflareDownloadHandler: Stopped persistent event loop")

    async def _stop_browser_async(self):
        """Stop browser on the correct event loop to avoid 'different loop' errors."""
        if CloudflareDownloadHandler._shared_browser:
            await CloudflareDownloadHandler._shared_browser.close()

    def download_request(self, request: Request, spider):
        """Handle request using hybrid or browser-only strategy.

        Note: This handler is only used when spider explicitly enables
        CLOUDFLARE_ENABLED=True in settings.

        Args:
            request: Scrapy request to download
            spider: Spider instance (passed by Scrapy)

        Returns:
            Deferred that resolves to HtmlResponse
        """
        spider_settings = getattr(spider, "custom_settings", {})
        strategy = spider_settings.get("CLOUDFLARE_STRATEGY", "hybrid").lower()

        if strategy == "browser_only":
            # Legacy mode: browser for every request
            return threads.deferToThread(self._browser_only_fetch_sync, request, spider)
        else:
            # Hybrid mode: browser once + HTTP with cookies
            return threads.deferToThread(self._hybrid_fetch_sync, request, spider)

    def _browser_only_fetch_sync(self, request: Request, spider):
        """Legacy browser-only mode (slow but reliable). Runs in thread."""
        try:
            # Run async code on persistent event loop (shared across all threads)
            html = CloudflareDownloadHandler._run_async(
                self._browser_only_fetch_async(request, spider)
            )

            if html:
                return _make_response(request.url, html, request)
            else:
                raise Exception(f"Failed to fetch {request.url}")
        except Exception as e:
            logger.error(f"Browser fetch error for {request.url}: {e}")
            raise

    async def _browser_only_fetch_async(self, request: Request, spider):
        """Async implementation of browser-only fetch."""
        await self._ensure_browser_started(spider)
        html = await self._fetch_with_browser(request.url, spider)
        return html

    def _hybrid_fetch_sync(self, request: Request, spider):
        """Hybrid mode: browser once + HTTP with cookies (fast). Runs in thread."""
        try:
            # Run async code on persistent event loop (shared across all threads)
            html = CloudflareDownloadHandler._run_async(
                self._hybrid_fetch_async(request, spider)
            )

            if html:
                return _make_response(request.url, html, request)
            else:
                raise Exception(f"Failed to fetch {request.url}")
        except Exception as e:
            logger.error(f"Hybrid fetch error for {request.url}: {e}")
            raise

    async def _hybrid_fetch_async(self, request: Request, spider):
        """Browser verifies a host once -> cached cookie -> fast concurrent HTTP.

        No time-based reverify: the browser is touched only when a host has no
        cookie yet, or an HTTP response comes back blocked. On a block, all
        requests hold at one gate, ONE reverifies, everyone retries — so a
        transient cookie death never fails a request, it just pauses briefly.
        """
        spider_name = spider.name
        key = self._cache_key(spider_name, request.url)

        # First hit for this host: verify (held at the gate so only one browser run).
        if key not in CloudflareDownloadHandler._cookie_cache:
            await self._reverify(key, request.url, spider, used_seq=None)

        cached = CloudflareDownloadHandler._cookie_cache.get(key)
        if not cached:
            raise Exception(f"No cookies available after verify for {request.url}")

        # Reuse the HTML the browser just fetched during a verify of this exact URL.
        if cached.get("last_browser_url") == request.url and cached.get(
            "last_browser_html"
        ):
            html = cached["last_browser_html"]
            with CloudflareDownloadHandler._cookie_cache_lock:
                entry = CloudflareDownloadHandler._cookie_cache.get(key)
                if entry:
                    entry["last_browser_html"] = None
                    entry["last_browser_url"] = None
            return html

        # Fast path: HTTP with the cached cookie.
        html = await self._fetch_with_http(request.url, cached)

        is_utility_file = request.url.endswith(("robots.txt", "sitemap.xml", ".ico"))
        if not is_utility_file and self._is_blocked(html):
            # Blocked: hold + reverify once + retry with the fresh cookie.
            logger.warning(
                f"[{spider_name}] Blocked on {urlparse(request.url).hostname} "
                "- holding to reverify"
            )
            await self._reverify(key, request.url, spider, used_seq=cached.get("seq"))
            cached = CloudflareDownloadHandler._cookie_cache[key]
            html = await self._fetch_with_http(request.url, cached)
            if self._is_blocked(html):
                # Still blocked right after a fresh verify => a real block
                # (IP/rate limit), not a stale cookie. Surface it.
                raise Exception(f"Still blocked after reverify: {request.url}")

        return html

    async def _reverify(self, key: str, url: str, spider, used_seq):
        """The gate: hold all callers, let ONE drive the browser, cache the host
        cookie. `used_seq` is the cookie generation the caller already tried —
        if the cache now holds a newer one, another caller already reverified
        and we return so the caller retries HTTP instead of re-driving the
        browser. `used_seq=None` is a first-hit (verify if no cookie exists)."""
        if CloudflareDownloadHandler._refresh_lock is None:
            CloudflareDownloadHandler._refresh_lock = asyncio.Lock()

        async with CloudflareDownloadHandler._refresh_lock:
            with CloudflareDownloadHandler._cookie_cache_lock:
                cached = CloudflareDownloadHandler._cookie_cache.get(key)
                already = cached is not None and (
                    used_seq is None or cached.get("seq", 0) > used_seq
                )
            if already:
                logger.info(f"[{key}] Cookie already (re)verified by another request")
                return

            host = urlparse(url).hostname
            # Prefer the ONE shared browser service (so N crawls share one
            # browser); fall back to a local browser if it isn't running.
            via_service = await self._verify_via_service(url, spider)
            if via_service is not None:
                logger.info(f"[{key}] Verified CF for {host} via browser service")
                html, cookies, user_agent = via_service
            else:
                logger.info(f"[{key}] Verifying CF for {host} via local browser")
                await self._ensure_browser_started(spider)
                html = await self._fetch_with_browser(url, spider)
                if not html:
                    raise Exception(f"Failed to verify CF for {url}")
                cookies, user_agent = await self._extract_cookies_from_browser(url)

            with CloudflareDownloadHandler._cookie_cache_lock:
                CloudflareDownloadHandler._cookie_seq += 1
                CloudflareDownloadHandler._cookie_cache[key] = {
                    "cookies": cookies,
                    "user_agent": user_agent,
                    "seq": CloudflareDownloadHandler._cookie_seq,
                    "timestamp": time.time(),
                    "last_browser_url": url,
                    "last_browser_html": html,
                }
            cookie_names = ", ".join(sorted(cookies.keys())) or "none"
            logger.info(f"[{key}] Cached {len(cookies)} cookies: {cookie_names}")

    async def _verify_via_service(self, url, spider):
        """Verify CF through the warm browser service (one browser shared by all
        crawls). If the service was stopped, bring it back up and retry — so a
        mistakenly-stopped service self-heals instead of every crawl spawning its
        own browser. Returns (html, cookies, user_agent), or None if the service
        still isn't reachable (caller then falls back to a local browser). The
        blocking socket/startup work runs in an executor so the loop never stalls."""
        from utils import browser_client

        session_name = getattr(spider, "custom_settings", {}).get("SESSION")

        def _call():
            resp = browser_client.request("cf_verify", url=url, session=session_name)
            if resp is None:
                # Service down (e.g. someone ran `browser stop`) — restart + retry.
                if browser_client.ensure_running():
                    resp = browser_client.request(
                        "cf_verify", url=url, session=session_name
                    )
            return resp

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, _call)
        if resp is None:
            return None  # couldn't reach or start the service -> local fallback
        if not resp.get("ok"):
            raise Exception(f"Browser service failed to verify CF for {url}")
        return resp["html"], resp["cookies"], resp["user_agent"]

    async def _fetch_with_http(self, url: str, cached: Dict) -> Optional[str]:
        """Fetch URL with HTTP + cached cookies using curl_cffi for TLS stealth."""
        try:
            import curl_cffi.requests as curl_requests

            cookie_str = "; ".join([f"{k}={v}" for k, v in cached["cookies"].items()])
            headers = {
                "User-Agent": cached["user_agent"],
                "Cookie": cookie_str,
            }

            # Proxy from the single source — prefer residential, else datacenter.
            from core import proxy as proxy_cfg

            proxy_url = proxy_cfg.residential_url() or proxy_cfg.datacenter_url()
            proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None

            # Run curl_cffi in thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: curl_requests.get(
                    url,
                    headers=headers,
                    proxies=proxies,
                    impersonate="chrome",
                    timeout=60,
                ),
            )

            logger.debug(
                f"HTTP fetch (curl_cffi): {url} -> {response.status_code} ({len(response.text)} bytes)"
            )
            return response.text
        except Exception as e:
            logger.error(f"HTTP fetch failed for {url}: {e}")
            return None

    def _is_blocked(self, html: Optional[str]) -> bool:
        """Check if response indicates CF block or challenge."""
        if not html:
            return True

        html_lower = html.lower()

        blocked_indicators = [
            # CF challenge pages
            ("cloudflare" in html_lower and "checking your browser" in html_lower),
            "just a moment" in html_lower and "cloudflare" in html_lower,
            "<title>just a moment...</title>" in html_lower,
            # CF block pages
            "sorry, you have been blocked" in html_lower,
            "access denied" in html_lower and "cloudflare" in html_lower,
            "error 1020" in html_lower,  # CF Access Denied
            "error 1015" in html_lower,  # CF Rate Limited
            # Very short response (likely challenge page)
            (len(html) < 5000 and "cloudflare" in html_lower),
        ]

        is_blocked = any(blocked_indicators)

        if is_blocked:
            logger.debug(f"Detected CF block/challenge in response ({len(html)} bytes)")

        return is_blocked

    async def _ensure_browser_started(self, spider):
        """Ensure browser is started (thread-safe)."""
        with CloudflareDownloadHandler._browser_startup_lock:
            if not CloudflareDownloadHandler._browser_started:
                from utils.cf_browser import CloudflareBrowserClient

                spider_settings = getattr(spider, "custom_settings", {})
                cf_max_retries = spider_settings.get("CF_MAX_RETRIES", 5)
                cf_retry_interval = spider_settings.get("CF_RETRY_INTERVAL", 1)
                cf_post_delay = spider_settings.get("CF_POST_DELAY", 5)
                cf_headless = spider_settings.get("CLOUDFLARE_HEADLESS", False)

                headless_mode = "headless" if cf_headless else "visible"
                logger.info(
                    f"Starting shared browser for CF verification ({headless_mode} mode)"
                )

                # Build proxy escalation chain based on crawl type
                # Test crawls: auto-escalate silently (direct → dc → residential)
                # Production crawls: stop at datacenter; residential needs approval
                is_test_crawl = self.settings.getint("CLOSESPIDER_ITEMCOUNT", 0) > 0
                spider_settings = getattr(spider, "custom_settings", {})
                proxy_type = spider_settings.get(
                    "PROXY_TYPE", self.settings.get("PROXY_TYPE", "auto")
                )

                from core import proxy

                dc_url = proxy.datacenter_url()
                res_url = proxy.residential_url()

                # Build chain based on proxy_type
                proxy_from_start = bool(spider_settings.get("PROXY_FROM_START"))
                if proxy_type == "residential":
                    # Skip straight to residential proxy (for geo-blocked / strict CF sites)
                    proxy_chain = [res_url] if res_url else [None]
                elif proxy_type in ("datacenter", "auto"):
                    # PROXY_FROM_START: skip the direct attempt, go straight to proxies
                    proxy_chain = [] if proxy_from_start else [None]
                    if dc_url:
                        proxy_chain.append(dc_url)
                    if res_url and (is_test_crawl or proxy_from_start):
                        proxy_chain.append(res_url)
                    elif res_url and not is_test_crawl:
                        CloudflareDownloadHandler._residential_available = True
                        CloudflareDownloadHandler._residential_url = res_url
                    if not proxy_chain:
                        proxy_chain = [None]
                else:
                    proxy_chain = [None]

                # A saved login session (spider's SESSION setting) — the browser
                # context is created already logged in. → core/sessions.py
                session_file = None
                session_name = spider_settings.get("SESSION")
                if session_name:
                    from core.sessions import session_path

                    p = session_path(session_name)
                    if p.exists():
                        session_file = str(p)
                        logger.info(f"Using login session '{session_name}'")
                    else:
                        logger.warning(
                            f"SESSION '{session_name}' not found at {p} — "
                            "crawling without it (run `scrapai session login`)"
                        )

                CloudflareDownloadHandler._shared_browser = CloudflareBrowserClient(
                    headless=cf_headless,
                    cf_max_retries=cf_max_retries,
                    cf_retry_interval=cf_retry_interval,
                    post_cf_delay=cf_post_delay,
                    proxy_chain=proxy_chain,
                    session_file=session_file,
                )

                await CloudflareDownloadHandler._shared_browser.start()
                CloudflareDownloadHandler._browser_started = True
                logger.info("Browser started successfully")

    async def _fetch_with_browser(self, url: str, spider) -> Optional[str]:
        """Fetch URL using browser."""
        spider_settings = getattr(spider, "custom_settings", {})
        wait_selector = spider_settings.get("CF_WAIT_SELECTOR")
        wait_timeout = spider_settings.get("CF_WAIT_TIMEOUT", 10)

        html = await CloudflareDownloadHandler._shared_browser.fetch(
            url, wait_selector=wait_selector, wait_timeout=wait_timeout
        )

        # If all proxies exhausted in production crawl, show expert-in-the-loop message
        if html is None and CloudflareDownloadHandler._residential_available:
            spider_name = getattr(spider, "name", "unknown")
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning(
                "⚠️  EXPERT-IN-THE-LOOP: Browser CF bypass failed (datacenter proxy blocked)"
            )
            logger.warning("")
            logger.warning(
                "🏠 Residential proxy is available but requires explicit approval"
            )
            logger.warning("")
            logger.warning("To retry with residential proxy, run:")
            logger.warning(
                f"  ./scrapai crawl {spider_name} --project <project> --proxy-type residential"
            )
            logger.warning("")
            logger.warning("=" * 80)
            logger.warning("")
            CloudflareDownloadHandler._residential_available = False  # Show once

        logger.debug(f"Browser fetch: {url} -> {len(html) if html else 0} bytes")
        return html

    async def _extract_cookies_from_browser(self, url=None):
        """Extract cookies + user-agent from the browser, scoped to ``url``'s
        host. The shared context accumulates cookies from every subdomain it
        visits; passing the URL makes Playwright return only the cookies valid
        for that host, so a host's cached entry can't pick up another
        subdomain's per-host cf_clearance."""
        if not CloudflareDownloadHandler._shared_browser:
            raise Exception("Browser not started")

        context = CloudflareDownloadHandler._shared_browser.context
        page = CloudflareDownloadHandler._shared_browser.page

        if not context or not page:
            raise Exception("No browser context/page available")

        # Scope to the URL's host (None -> all, for back-compat)
        cookies_list = await context.cookies(url)
        cookies = {c["name"]: c["value"] for c in cookies_list if c.get("name")}

        # Get user agent
        try:
            user_agent = await page.evaluate("navigator.userAgent")
        except Exception:
            user_agent = USER_AGENT

        return cookies, user_agent
