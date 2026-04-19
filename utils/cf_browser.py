"""
Cloudflare bypass browser client using CloakBrowser.

CloakBrowser provides source-level C++ stealth patches for maximum
bot detection bypass (0.9 reCAPTCHA score, passes FingerprintJS, etc.).
"""

import asyncio
import logging
import random
import threading
from typing import List, Optional

from cloakbrowser import launch_async

logger = logging.getLogger(__name__)


def random_delay(min_sec: float, max_sec: float) -> float:
    """Generate random delay to mimic human timing variance."""
    return random.uniform(min_sec, max_sec)


class CloudflareBrowserClient:
    """Persistent browser session with CloakBrowser for maximum stealth.

    Supports proxy escalation: tries each proxy in chain until CF bypass succeeds.
    Chain is typically: [None (direct), datacenter_url, residential_url]

    On escalation the browser is restarted only when the proxy changes, because
    Chromium binds the proxy at launch time. However, the browser is kept alive
    between CF retry attempts within the same proxy level — killing and
    restarting the browser on every retry loses cookies/session and makes CF
    harder to solve.

    Advantages:
    - Source-level C++ patches (vs UC-style runtime patches)
    - 0.9 reCAPTCHA v3 score (vs ~0.5-0.7)
    - Passes FingerprintJS, BrowserScan (30/30 tests)
    - Clean Playwright API
    - Actively maintained

    Usage:
        async with CloudflareBrowserClient(headless=False) as browser:
            html1 = await browser.fetch("https://example.com/page1")
            html2 = await browser.fetch("https://example.com/page2")
    """

    def __init__(
        self,
        headless: bool = False,
        cf_max_retries: int = 5,
        cf_retry_interval: int = 1,
        post_cf_delay: int = 5,
        proxy_url: Optional[str] = None,
        proxy_chain: Optional[List[Optional[str]]] = None,
    ):
        """Initialize CloakBrowser client.

        Args:
            headless: Run in headless mode (visible by default for debugging)
            cf_max_retries: Max retry attempts (kept for API compat, not needed)
            cf_retry_interval: Retry interval (kept for API compat, not needed)
            post_cf_delay: Seconds to wait after CF verification
            proxy_url: Single proxy URL (legacy, wraps into proxy_chain)
            proxy_chain: Ordered list of proxy URLs to try (None = direct connection).
                         Escalates through chain until CF bypass succeeds.
        """
        self.browser = None
        self.context = None
        self.page = None
        self.headless = headless
        self.cf_verified = False
        self.post_cf_delay = post_cf_delay
        self.fetch_lock = None  # Created lazily on first fetch
        self._lock_init_lock = threading.Lock()

        # Not needed with CloakBrowser (automatic bypass), kept for API compat
        self.cf_max_retries = cf_max_retries
        self.cf_retry_interval = cf_retry_interval

        # Proxy chain - build from proxy_chain or fallback to single proxy_url
        if proxy_chain is not None:
            self._proxy_chain = proxy_chain
        elif proxy_url is not None:
            self._proxy_chain = [proxy_url]
        else:
            self._proxy_chain = [None]

        self._chain_index = 0  # Current position in proxy chain

        # Compatibility attrs for nodriver-style code
        self.driver = None  # Alias for browser
        self.tab = None  # Alias for page

    @property
    def proxy_url(self) -> Optional[str]:
        """Current proxy URL being used."""
        if self._chain_index < len(self._proxy_chain):
            return self._proxy_chain[self._chain_index]
        return None

    async def start(self):
        """Start CloakBrowser instance with current proxy."""
        proxy = self.proxy_url
        if proxy:
            logger.info(f"Starting CloakBrowser with proxy: {proxy}")
        else:
            logger.info("Starting CloakBrowser (direct connection)")

        try:
            launch_kwargs = {"headless": self.headless}
            if proxy:
                launch_kwargs["proxy"] = proxy
                launch_kwargs["geoip"] = (
                    True  # Match timezone/locale to proxy IP for CF bypass
                )
            self.browser = await launch_async(**launch_kwargs)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()

            # Compatibility aliases
            self.driver = self.browser
            self.tab = self.page

            logger.info("CloakBrowser started successfully")

            # Initial delay (mimic human)
            init_delay = random_delay(1.5, 2.5)
            logger.debug(f"Waiting {init_delay:.2f}s for initialization...")
            await asyncio.sleep(init_delay)

        except Exception as e:
            logger.error(f"Failed to start CloakBrowser: {e}")
            raise

    async def _escalate(self) -> bool:
        """Restart browser with next proxy in chain.

        Chromium binds the proxy at launch time, so we must restart when
        switching proxies. However, this only happens when moving to a
        different proxy level — NOT on every retry within the same level.

        Returns:
            True if escalated successfully, False if chain exhausted.
        """
        self._chain_index += 1
        if self._chain_index >= len(self._proxy_chain):
            return False

        next_proxy = self._proxy_chain[self._chain_index]
        proxy_label = next_proxy if next_proxy else "direct"
        logger.warning(f"CF bypass failed - escalating to next proxy: {proxy_label}")

        await self.close()
        self.cf_verified = False
        self.fetch_lock = None
        await self.start()
        return True

    async def verify_cloudflare(self, url: str) -> bool:
        """Navigate to URL and verify Cloudflare.

        Keeps the browser alive between retry attempts. Clicks the Turnstile
        checkbox when detected. Only returns False (triggering proxy escalation)
        when all retries are exhausted or the page is geo-blocked.

        Args:
            url: URL to navigate and verify

        Returns:
            True if successful, False otherwise
        """
        if not self.page:
            await self.start()

        try:
            logger.info(f"Navigating to {url} (CloakBrowser auto-bypasses CF)")

            # Navigate (CloakBrowser automatically bypasses Cloudflare)
            # Some CF-protected sites return 403 which causes goto to throw —
            # catch it and let the challenge page load anyway
            try:
                await self.page.goto(url, wait_until="domcontentloaded", timeout=120000)
            except Exception as nav_err:
                err_str = str(nav_err).lower()
                if "response_code_failure" in err_str or "403" in err_str:
                    logger.debug(
                        f"Got HTTP error during navigation (expected for CF): {nav_err}"
                    )
                    await asyncio.sleep(2)
                else:
                    raise

            # Wait for CF challenge to resolve — keep browser alive the whole time
            logger.debug("Waiting for CF challenge to resolve...")
            max_retries = 24  # 24 retries × 5s = 120s per proxy level
            turnstile_clicked = False
            for attempt in range(max_retries):
                await asyncio.sleep(5)  # Wait 5s between checks

                try:
                    title = await self.page.title()
                    # Check page content size — CF challenge pages are ~30KB
                    # with very little actual text content
                    html_check = await self.page.content()
                    cf_blocked = any(
                        p in title.lower()
                        for p in [
                            "just a moment",
                            "attention required",
                            "please wait",
                            "one more step",
                            "checking your browser",
                            "enable javascript and cookies",
                            "bir dakika",  # Turkish
                            "しばらくお待ち",  # Japanese
                            "un moment",  # French
                            "einen moment",  # German
                            "un momento",  # Spanish/Italian
                        ]
                    )
                    # Also detect CF by checking for turnstile in page content
                    if not cf_blocked and "challenges.cloudflare.com" in html_check:
                        if len(html_check) < 35000:
                            cf_blocked = True
                    if cf_blocked:
                        logger.debug(
                            f"CF challenge still active after {(attempt + 1) * 5}s "
                            f"(attempt {attempt + 1}/{max_retries}), waiting..."
                        )

                        # Try clicking Turnstile checkbox — retry every 15s
                        if not turnstile_clicked or (attempt % 3 == 0):
                            try:
                                clicked = await self._click_turnstile()
                                if clicked:
                                    turnstile_clicked = True
                            except Exception as e:
                                logger.debug(f"Turnstile click attempt failed: {e}")

                        continue

                    # Title changed — check for geo-block / access denied
                    html = await self.page.content()
                    geo_blocked = any(
                        phrase in html.lower()
                        for phrase in [
                            "access blocked",
                            "unavailable to visitors",
                            "prohibited from your location",
                            "regulations imposed by your country",
                        ]
                    )
                    if geo_blocked and len(html) < 2000:
                        logger.warning(
                            f"Geo-blocked after CF bypass with proxy {self.proxy_url} - "
                            f"will escalate to next proxy"
                        )
                        return False

                    # Check for generic "Access Denied" that isn't CF
                    if "access denied" in title.lower():
                        access_denied = any(
                            phrase in html.lower()
                            for phrase in [
                                "nothing wrong with the site",
                                "regulations imposed",
                                "prohibited from your location",
                            ]
                        )
                        if access_denied and len(html) < 2000:
                            logger.warning(
                                f"Access denied (geo-block) with proxy {self.proxy_url}"
                            )
                            return False

                    # CF challenge passed
                    logger.info(
                        f"CF bypass successful after {(attempt + 1) * 5}s - title: {title!r}"
                    )
                    self.cf_verified = True
                    return True

                except Exception as e:
                    err_msg = str(e).lower()
                    if "navigat" in err_msg or "destroyed" in err_msg:
                        logger.debug(
                            f"Page navigating/redirecting (attempt {attempt + 1}/{max_retries}) — "
                            f"CF may have just resolved, waiting..."
                        )
                    else:
                        raise

            logger.warning(f"CF challenge not resolved after {max_retries * 5}s")
            return False

        except Exception as e:
            logger.error(f"Error during navigation: {e}")
            return False

    async def _click_turnstile(self) -> bool:
        """Detect and click Cloudflare Turnstile checkbox.

        Turnstile renders inside an iframe from challenges.cloudflare.com.
        Uses multiple strategies to find and click the checkbox:
        1. Try to find the iframe element by selector and click its center
        2. Try to find the challenge container div and click within it
        3. Fall back to clicking known coordinates on the CF challenge page

        Returns:
            True if a Turnstile widget was found and clicked.
        """
        if not self.page:
            return False

        # Verify CF challenge frame exists
        cf_frames = [f for f in self.page.frames if "challenges.cloudflare" in f.url]
        if not cf_frames:
            return False

        # Strategy 1: Find iframe element by selector
        for selector in [
            'iframe[src*="challenges.cloudflare"]',
            'iframe[src*="turnstile"]',
            "#challenge-stage iframe",
            "#turnstile-wrapper iframe",
        ]:
            locator = self.page.locator(selector)
            count = await locator.count()
            if count > 0:
                box = await locator.first.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    cx = box["x"] + box["width"] / 2
                    cy = box["y"] + box["height"] / 2
                    logger.info(
                        f"Turnstile iframe found at ({cx:.0f}, {cy:.0f}), clicking..."
                    )
                    await self.page.mouse.click(
                        cx + random_delay(-5, 5),
                        cy + random_delay(-3, 3),
                    )
                    await asyncio.sleep(random_delay(1.0, 2.0))
                    return True

        # Strategy 2: Find the challenge container and click within it
        for selector in [
            "#challenge-stage",
            "#turnstile-wrapper",
            ".cf-turnstile",
            'div[class*="challenge"]',
        ]:
            locator = self.page.locator(selector)
            count = await locator.count()
            if count > 0:
                box = await locator.first.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    # Click left-center area where checkbox typically is
                    cx = box["x"] + 30
                    cy = box["y"] + box["height"] / 2
                    logger.info(
                        f"Challenge container found, clicking at ({cx:.0f}, {cy:.0f})..."
                    )
                    await self.page.mouse.click(
                        cx + random_delay(-3, 3),
                        cy + random_delay(-3, 3),
                    )
                    await asyncio.sleep(random_delay(1.0, 2.0))
                    return True

        # Strategy 3: Fall back to known coordinates
        # CF Turnstile checkbox is rendered at a consistent position on
        # the challenge page — typically around (230, 335) on a 1280x720 viewport
        logger.info(
            "No iframe/container found via selectors, clicking known Turnstile position..."
        )
        await self.page.mouse.click(
            230 + random_delay(-10, 10),
            337 + random_delay(-5, 5),
        )
        await asyncio.sleep(random_delay(1.0, 2.0))
        return True

    async def fetch(
        self, url: str, wait_selector: Optional[str] = None, wait_timeout: int = 10
    ) -> Optional[str]:
        """Fetch a URL using CloakBrowser, escalating proxies if CF blocks.

        Args:
            url: URL to fetch
            wait_selector: CSS selector to wait for (optional)
            wait_timeout: Max seconds to wait for selector

        Returns:
            HTML content as string, or None if all proxies exhausted
        """
        # Lazy lock creation
        if self.fetch_lock is None:
            with self._lock_init_lock:
                if self.fetch_lock is None:
                    self.fetch_lock = asyncio.Lock()

        # Use lock to ensure sequential fetching (reusing same page)
        async with self.fetch_lock:
            # First request - verify CF, escalating through proxy chain if needed
            if not self.cf_verified:
                success = False
                while not success:
                    success = await self.verify_cloudflare(url)
                    if not success:
                        escalated = await self._escalate()
                        if not escalated:
                            logger.error("All proxies exhausted - CF bypass failed")
                            return None

                # After CF verify, re-navigate to target URL to get actual content
                # CF Turnstile solve may leave the browser on the challenge DOM
                # even though verification passed — re-navigating forces a fresh load
                logger.info(f"CF verified, re-navigating to {url} for actual content")
                try:
                    await self.page.goto(
                        url, wait_until="domcontentloaded", timeout=60000
                    )
                except Exception as e:
                    err_str = str(e).lower()
                    if "response_code_failure" in err_str:
                        logger.debug(f"HTTP error on post-CF navigate: {e}")
                        await asyncio.sleep(2)
                    else:
                        raise

                await asyncio.sleep(3)
                html = await self.page.content()
                logger.info(f"Fetched {len(html)} bytes from {url}")
                return html

            # Subsequent requests - reuse same page
            logger.info(f"Fetching {url} using verified session (reusing page)")
            try:
                # Navigate same page to new URL
                # Use domcontentloaded (recommended by Playwright, faster than load)
                await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

                # Let page stabilize after navigation
                await asyncio.sleep(2)

                # Wait for specific selector if requested
                if wait_selector:
                    logger.info(
                        f"Waiting for selector '{wait_selector}' (timeout: {wait_timeout}s)"
                    )
                    try:
                        await self.page.wait_for_selector(
                            wait_selector, timeout=wait_timeout * 1000
                        )
                        logger.info(f"Selector '{wait_selector}' found")
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.warning(f"Timeout waiting for selector: {e}")
                        await asyncio.sleep(1.5)
                else:
                    # No selector - wait for content to fully render
                    await asyncio.sleep(2)

                # Get HTML content
                html = await self.page.content()

                # Only warn about small HTML if it's not robots.txt or similar
                if "robots.txt" not in url.lower():
                    text_length = len(html.replace("<", "").replace(">", "").strip())
                    if text_length < 1000:
                        logger.debug(
                            f"HTML seems small ({text_length} chars), waiting longer..."
                        )
                        await asyncio.sleep(1.5)  # Additional wait for content
                        html = await self.page.content()

                logger.info(f"Fetched {len(html)} bytes from {url}")
                return html

            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

    async def close(self):
        """Close CloakBrowser."""
        if self.browser:
            try:
                await self.browser.close()
                self.browser = None
                self.context = None
                self.page = None
                self.driver = None
                self.tab = None
                logger.info("CloakBrowser closed")
            except Exception as e:
                logger.warning(f"Error closing CloakBrowser: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
