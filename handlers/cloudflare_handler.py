"""
Scrapy download handler for Cloudflare-protected sites.

This handler uses a hybrid approach:
1. Browser verification (once per 25 min) to get CF cookies
2. Fast HTTP requests with cached cookies for subsequent requests
3. Automatic fallback to browser if cookies become invalid

Strategies:
- 'hybrid': Browser once + HTTP with cookies (fast, default)
- 'browser_only': Browser for every request (slow, legacy)
"""

import asyncio
import logging
import time
from typing import Dict, Optional

import aiohttp
from scrapy.http import HtmlResponse, Request
from twisted.internet import defer

logger = logging.getLogger(__name__)


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
    - Cookies cached per spider
    - Proactive refresh before expiry (25 min)
    - Automatic fallback to browser on block

    Settings:
    - CLOUDFLARE_STRATEGY: 'hybrid' or 'browser_only' (default: 'hybrid')
    - CLOUDFLARE_COOKIE_REFRESH_THRESHOLD: seconds before refresh (default: 1500)
    """

    # Class-level (shared) browser state
    _shared_browser = None
    _browser_started = False
    _browser_startup_lock = asyncio.Lock()  # Protect browser startup (1 at a time)

    # Cookie cache: {spider_name: {'cookies': {}, 'user_agent': str, 'timestamp': float}}
    _cookie_cache: Dict[str, Dict] = {}
    _cookie_cache_lock = asyncio.Lock()

    # Default: refresh cookies after 10 minutes
    DEFAULT_COOKIE_REFRESH_THRESHOLD = 600  # seconds (10 minutes)

    def __init__(self, settings, crawler=None):
        """Initialize the handler.

        Args:
            settings: Scrapy settings
            crawler: Scrapy crawler instance
        """
        self.crawler = crawler
        self.loop = None

    @classmethod
    def from_crawler(cls, crawler):
        """Create handler from crawler (Scrapy convention)."""
        return cls(crawler.settings, crawler)

    def open(self):
        """Called when spider opens - prepare handler."""
        # Browser will be started lazily on first request
        logger.info("CloudflareDownloadHandler: Handler opened (browser will start on first request)")

    def close(self):
        """Called when spider closes - close browser and wait for completion."""
        if CloudflareDownloadHandler._browser_started and CloudflareDownloadHandler._shared_browser:
            try:
                logger.info("CloudflareDownloadHandler: Closing shared browser...")

                # Close browser synchronously (wait for completion)
                # driver.stop() is synchronous, so call it directly
                if CloudflareDownloadHandler._shared_browser.driver:
                    CloudflareDownloadHandler._shared_browser.driver.stop()
                    logger.info("CloudflareDownloadHandler: Browser stopped successfully")

                # Clean up state
                CloudflareDownloadHandler._shared_browser = None
                CloudflareDownloadHandler._browser_started = False
                logger.info("CloudflareDownloadHandler: Closed shared browser")

            except Exception as e:
                logger.error(f"CloudflareDownloadHandler: Error closing browser: {e}")
        else:
            logger.info("CloudflareDownloadHandler: No browser to close")

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
        # Wrap the async coroutine in a Deferred for Scrapy's synchronous middleware
        return defer.ensureDeferred(self._download_request_async(request, spider))

    async def _download_request_async(self, request: Request, spider):
        """Async implementation of download_request."""
        spider_settings = getattr(spider, 'custom_settings', {})

        # Get strategy (hybrid by default)
        strategy = spider_settings.get('CLOUDFLARE_STRATEGY', 'hybrid').lower()

        if strategy == 'browser_only':
            # Legacy mode: browser for every request
            return await self._browser_only_fetch(request, spider)
        else:
            # Hybrid mode: browser once + HTTP with cookies
            return await self._hybrid_fetch(request, spider)

    async def _browser_only_fetch(self, request: Request, spider):
        """Legacy browser-only mode (slow but reliable)."""
        try:
            await self._ensure_browser_started(spider)
            html = await self._fetch_with_browser(request.url, spider)

            if html:
                return HtmlResponse(
                    url=request.url,
                    body=html.encode('utf-8'),
                    encoding='utf-8',
                    request=request
                )
            else:
                raise Exception(f"Failed to fetch {request.url}")
        except Exception as e:
            logger.error(f"Browser fetch error for {request.url}: {e}")
            raise

    async def _hybrid_fetch(self, request: Request, spider):
        """Hybrid mode: browser once + HTTP with cookies (fast)."""
        try:
            spider_name = spider.name

            # Check if we need cookies (first request or expired)
            need_refresh = await self._should_refresh_cookies(spider_name, spider)

            if need_refresh:
                logger.info(f"[{spider_name}] Getting/refreshing CF cookies via browser")
                await self._refresh_cookies(spider_name, request.url, spider)

            # Fetch with HTTP + cookies
            cached = CloudflareDownloadHandler._cookie_cache.get(spider_name)
            if not cached:
                raise Exception("No cookies available after refresh")

            html = await self._fetch_with_http(request.url, cached)

            # Check if blocked
            if self._is_blocked(html):
                logger.warning(f"[{spider_name}] Blocked despite cookies - re-verifying CF")
                # Invalidate cache and retry
                await self._invalidate_cookies(spider_name)
                await self._refresh_cookies(spider_name, request.url, spider)
                cached = CloudflareDownloadHandler._cookie_cache[spider_name]
                html = await self._fetch_with_http(request.url, cached)

                if self._is_blocked(html):
                    # Still blocked - fallback to browser
                    logger.error(f"[{spider_name}] Still blocked - falling back to browser")
                    html = await self._fetch_with_browser(request.url, spider)

            if html:
                return HtmlResponse(
                    url=request.url,
                    body=html.encode('utf-8'),
                    encoding='utf-8',
                    request=request
                )
            else:
                raise Exception(f"Failed to fetch {request.url}")

        except Exception as e:
            logger.error(f"Hybrid fetch error for {request.url}: {e}")
            raise

    async def _should_refresh_cookies(self, spider_name: str, spider) -> bool:
        """Check if cookies need refreshing."""
        spider_settings = getattr(spider, 'custom_settings', {})
        threshold = spider_settings.get(
            'CLOUDFLARE_COOKIE_REFRESH_THRESHOLD',
            self.DEFAULT_COOKIE_REFRESH_THRESHOLD
        )

        async with CloudflareDownloadHandler._cookie_cache_lock:
            if spider_name not in CloudflareDownloadHandler._cookie_cache:
                return True

            cached = CloudflareDownloadHandler._cookie_cache[spider_name]
            age = time.time() - cached['timestamp']

            if age > threshold:
                logger.info(f"[{spider_name}] Cookies aging ({age/60:.1f} min) - refreshing proactively")
                return True

            return False

    async def _refresh_cookies(self, spider_name: str, url: str, spider):
        """Get fresh cookies via browser."""
        await self._ensure_browser_started(spider)

        # Fetch page with browser to get cookies
        html = await self._fetch_with_browser(url, spider)

        if not html:
            raise Exception(f"Failed to verify CF for {url}")

        # Extract cookies from browser
        cookies, user_agent = await self._extract_cookies_from_browser()

        # Cache cookies
        async with CloudflareDownloadHandler._cookie_cache_lock:
            CloudflareDownloadHandler._cookie_cache[spider_name] = {
                'cookies': cookies,
                'user_agent': user_agent,
                'timestamp': time.time()
            }

        logger.info(f"[{spider_name}] Cached {len(cookies)} cookies (cf_clearance: {cookies.get('cf_clearance', 'N/A')[:20]}...)")

    async def _invalidate_cookies(self, spider_name: str):
        """Invalidate cached cookies."""
        async with CloudflareDownloadHandler._cookie_cache_lock:
            if spider_name in CloudflareDownloadHandler._cookie_cache:
                del CloudflareDownloadHandler._cookie_cache[spider_name]
                logger.info(f"[{spider_name}] Cookie cache invalidated")

    async def _fetch_with_http(self, url: str, cached: Dict) -> Optional[str]:
        """Fetch URL with HTTP + cached cookies."""
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    cookies=cached['cookies'],
                    headers={'User-Agent': cached['user_agent']},
                    timeout=timeout
                ) as response:
                    html = await response.text()
                    logger.debug(f"HTTP fetch: {url} -> {response.status} ({len(html)} bytes)")
                    return html
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
            ('cloudflare' in html_lower and 'checking your browser' in html_lower),
            'just a moment' in html_lower and 'cloudflare' in html_lower,
            '<title>just a moment...</title>' in html_lower,

            # CF block pages
            'sorry, you have been blocked' in html_lower,
            'access denied' in html_lower and 'cloudflare' in html_lower,
            'error 1020' in html_lower,  # CF Access Denied
            'error 1015' in html_lower,  # CF Rate Limited

            # Very short response (likely challenge page)
            (len(html) < 5000 and 'cloudflare' in html_lower),
        ]

        is_blocked = any(blocked_indicators)

        if is_blocked:
            logger.debug(f"Detected CF block/challenge in response ({len(html)} bytes)")

        return is_blocked

    async def _ensure_browser_started(self, spider):
        """Ensure browser is started (thread-safe)."""
        async with CloudflareDownloadHandler._browser_startup_lock:
            if not CloudflareDownloadHandler._browser_started:
                from utils.cf_browser import CloudflareBrowserClient

                spider_settings = getattr(spider, 'custom_settings', {})
                cf_max_retries = spider_settings.get('CF_MAX_RETRIES', 5)
                cf_retry_interval = spider_settings.get('CF_RETRY_INTERVAL', 1)
                cf_post_delay = spider_settings.get('CF_POST_DELAY', 5)

                logger.info("Starting shared browser for CF verification")

                CloudflareDownloadHandler._shared_browser = CloudflareBrowserClient(
                    headless=False,
                    cf_max_retries=cf_max_retries,
                    cf_retry_interval=cf_retry_interval,
                    post_cf_delay=cf_post_delay
                )

                await CloudflareDownloadHandler._shared_browser.start()
                CloudflareDownloadHandler._browser_started = True
                logger.info("Browser started successfully")

    async def _fetch_with_browser(self, url: str, spider) -> Optional[str]:
        """Fetch URL using browser."""
        spider_settings = getattr(spider, 'custom_settings', {})
        wait_selector = spider_settings.get('CF_WAIT_SELECTOR')
        wait_timeout = spider_settings.get('CF_WAIT_TIMEOUT', 10)

        html = await CloudflareDownloadHandler._shared_browser.fetch(
            url,
            wait_selector=wait_selector,
            wait_timeout=wait_timeout
        )

        logger.debug(f"Browser fetch: {url} -> {len(html) if html else 0} bytes")
        return html

    async def _extract_cookies_from_browser(self):
        """Extract cookies and user-agent from browser."""
        if not CloudflareDownloadHandler._shared_browser:
            raise Exception("Browser not started")

        tab = CloudflareDownloadHandler._shared_browser.tab
        if not tab:
            raise Exception("No browser tab available")

        # Get cookies via CDP
        import nodriver as uc
        cookies_cdp = await tab.send(uc.cdp.network.get_cookies())
        cookies = {c.name: c.value for c in cookies_cdp if c.name}  # Filter empty names

        # Get user agent
        try:
            user_agent = await tab.evaluate('navigator.userAgent')
        except Exception:
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

        return cookies, user_agent

