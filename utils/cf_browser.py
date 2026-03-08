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
        """Close browser and restart with next proxy in chain.

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

        With CloakBrowser, this is automatic - no CFVerify needed!
        The C++ patches handle all detection automatically.

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
            await self.page.goto(url, wait_until="domcontentloaded", timeout=120000)

            # Wait for CF challenge to resolve and redirect to actual page
            # CF challenge completes → JS runs → redirects → real page loads
            logger.debug("Waiting for CF challenge to resolve...")
            max_retries = 6  # 6 retries × 5s = 30s per proxy level
            for attempt in range(max_retries):
                await asyncio.sleep(5)  # Wait 5s between attempts

                try:
                    title = await self.page.title()
                    cf_blocked = any(
                        p in title.lower()
                        for p in [
                            "just a moment",
                            "attention required",
                            "access denied",
                            "please wait",
                            "one more step",
                            "checking your browser",
                            "enable javascript and cookies",
                        ]
                    )
                    if cf_blocked:
                        logger.debug(
                            f"CF challenge still active after {(attempt + 1) * 5}s "
                            f"(attempt {attempt + 1}/{max_retries}), waiting..."
                        )
                        continue

                    # Title changed - CF challenge passed
                    logger.info(
                        f"CF bypass successful after {(attempt + 1) * 5}s - title: {title!r}"
                    )
                    self.cf_verified = True
                    return True

                except Exception as e:
                    if "navigating" in str(e).lower():
                        logger.debug(
                            f"Page still navigating (attempt {attempt + 1}/{max_retries})"
                        )
                    else:
                        raise

            logger.warning(f"CF challenge not resolved after {max_retries * 5}s")
            return False

        except Exception as e:
            logger.error(f"Error during navigation: {e}")
            return False

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

                # Wait for content to be fully available after CF bypass
                await asyncio.sleep(1)

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
