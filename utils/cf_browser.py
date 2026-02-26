"""
Cloudflare bypass browser client using nodriver.

This module provides a persistent browser session that can solve Cloudflare
challenges once and reuse the verified session for subsequent requests.
"""

import os
import asyncio
import logging
import random
import threading
from typing import Optional

import nodriver as uc
from nodriver_cf_verify import CFVerify

logger = logging.getLogger(__name__)


def random_delay(min_sec: float, max_sec: float) -> float:
    """Generate random delay to mimic human timing variance"""
    return random.uniform(min_sec, max_sec)


class CloudflareBrowserClient:
    """Persistent browser session with Cloudflare bypass capability.

    This client starts a browser once, solves the Cloudflare challenge on first
    request, and reuses the verified session for all subsequent requests.

    Usage:
        async with CloudflareBrowserClient(headless=False) as browser:
            html1 = await browser.fetch("https://example.com/page1")
            html2 = await browser.fetch("https://example.com/page2")  # Reuses session
    """

    def __init__(
        self,
        headless: bool = False,
        cf_max_retries: int = 5,
        cf_retry_interval: int = 1,
        post_cf_delay: int = 5,
    ):
        """Initialize the Cloudflare browser client.

        Args:
            headless: Whether to run browser in headless mode (may fail CF verification)
            cf_max_retries: Maximum number of CF verification attempts
            cf_retry_interval: Seconds to wait between CF retry attempts
            post_cf_delay: Seconds to wait after successful CF verification
        """
        self.driver = None
        self.tab = None
        self.headless = headless
        self.cf_verified = False
        self.cf_max_retries = cf_max_retries
        self.cf_retry_interval = cf_retry_interval
        self.post_cf_delay = post_cf_delay
        self.fetch_lock = (
            None  # Created lazily on first fetch to bind to correct event loop
        )
        self._lock_init_lock = threading.Lock()  # Thread-safe lock initialization

    async def start(self):
        """Start the browser instance."""
        from utils.display_helper import ensure_display_for_cf

        # Check if display is available for CF bypass
        try:
            ensure_display_for_cf()
        except RuntimeError as e:
            logger.error(str(e))
            raise

        # Try to find Chrome/Chromium binary
        browser_path = os.getenv("CHROME_PATH")
        if not browser_path:
            # Try common paths based on OS
            import sys
            import glob

            if sys.platform == "darwin":
                # macOS - Playwright Chromium
                pattern = os.path.expanduser(
                    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
                )
                matches = glob.glob(pattern)
                if matches:
                    browser_path = matches[0]
                    logger.info(f"Found Playwright Chromium: {browser_path}")
            else:
                # Linux - try both chrome-linux64 (newer) and chrome-linux (older)
                for pattern in [
                    "~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome",
                    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
                ]:
                    playwright_chrome = os.path.expanduser(pattern)
                    matches = glob.glob(playwright_chrome)
                    if matches:
                        browser_path = matches[0]
                        logger.info(f"Found Playwright Chromium: {browser_path}")
                        break

        browser_args = [
            "--disable-dev-shm-usage",
        ]

        try:
            self.driver = await uc.start(
                headless=self.headless,
                browser_executable_path=(
                    browser_path
                    if browser_path and os.path.exists(browser_path)
                    else None
                ),
                browser_args=browser_args,
                sandbox=False,  # Disable sandbox
            )
            logger.info("Started nodriver browser for Cloudflare bypass")

            # Wait for browser to fully initialize (random delay like human)
            init_delay = random_delay(1.5, 2.5)
            logger.debug(
                f"Waiting {init_delay:.2f}s for browser to fully initialize..."
            )
            await asyncio.sleep(init_delay)
            logger.debug("Browser initialization wait complete")
        except Exception as e:
            logger.error(f"Failed to start nodriver browser: {e}")
            raise

    async def verify_cloudflare(self, url: str) -> bool:
        """Navigate to URL and solve Cloudflare challenge.

        Args:
            url: The URL to navigate to and verify

        Returns:
            True if verification succeeded, False otherwise
        """
        if not self.driver:
            await self.start()

        try:
            # Navigate to URL (timeout set at browser config level)
            self.tab = await self.driver.get(url)
            logger.info(f"Navigating to {url} for Cloudflare verification")

            # Create CF verifier and solve challenge
            cf_verify = CFVerify(
                _browser_tab=self.tab, _debug=logger.level <= logging.DEBUG
            )

            success = await cf_verify.verify(
                _max_retries=10,  # More attempts
                _interval_between_retries=2,  # More time between attempts
                _reload_page_after_n_retries=3,  # Reload after 3 failed attempts
            )

            if not success:
                logger.error(f"Failed to verify Cloudflare for {url}")
                return False

            logger.info(f"Cloudflare verified successfully for {url}")
            self.cf_verified = True

            # Wait for content to load after CF verification (random like human)
            post_delay = random_delay(
                max(3.0, self.post_cf_delay - 1), self.post_cf_delay + 2
            )
            logger.info(
                f"Waiting {post_delay:.2f}s for content to load after CF verification"
            )
            await self.tab.sleep(post_delay)

            # Additional wait to ensure full page render (random)
            render_delay = random_delay(2.0, 4.0)
            logger.info(f"Waiting {render_delay:.2f}s for full page render...")
            await self.tab.sleep(render_delay)

            return True

        except Exception as e:
            logger.error(f"Error during Cloudflare verification: {e}")
            return False

    async def fetch(
        self, url: str, wait_selector: Optional[str] = None, wait_timeout: int = 10
    ) -> Optional[str]:
        """Fetch a URL using the verified session.

        On first call, this will verify Cloudflare. Subsequent calls reuse
        the same tab (sequential fetching with lock).

        Args:
            url: The URL to fetch
            wait_selector: CSS selector to wait for before extracting HTML (e.g., 'h1.title-med-1')
            wait_timeout: Maximum seconds to wait for selector (default: 10)

        Returns:
            HTML content as string, or None if fetch failed
        """
        # Lazy lock creation - ensures lock is bound to correct event loop
        # Use double-checked locking to prevent race condition
        if self.fetch_lock is None:
            with self._lock_init_lock:
                if self.fetch_lock is None:  # Double-check after acquiring thread lock
                    self.fetch_lock = asyncio.Lock()

        # Use lock to ensure only one fetch at a time (sequential, using same tab)
        async with self.fetch_lock:
            # First request - verify CF
            if not self.cf_verified:
                success = await self.verify_cloudflare(url)
                if not success:
                    return None
                # Return content from CF verification
                html = await self.tab.get_content()
                logger.info(f"Fetched {len(html)} bytes from {url}")
                return html

            # Subsequent requests - reuse same tab
            logger.info(
                f"Fetching {url} using verified Cloudflare session (reusing tab)"
            )
            try:
                # Navigate same tab to new URL
                await self.tab.get(url)

                # Wait for page to fully load (random like human)
                stabilize_delay = random_delay(1.5, 2.5)
                logger.debug(f"Waiting {stabilize_delay:.2f}s for page to stabilize...")
                await self.tab.sleep(stabilize_delay)

                # If wait_selector provided, wait for it to appear
                if wait_selector:
                    logger.info(
                        f"Waiting for selector '{wait_selector}' to appear (timeout: {wait_timeout}s)"
                    )
                    try:
                        # Wait for the selector to be present in the DOM
                        await self.tab.select(wait_selector, timeout=wait_timeout)
                        logger.info(f"Selector '{wait_selector}' found")
                        # Additional wait to ensure full rendering (random)
                        render_wait = random_delay(1.5, 2.5)
                        await self.tab.sleep(render_wait)
                    except Exception as e:
                        logger.warning(
                            f"Timeout waiting for selector '{wait_selector}': {e}"
                        )
                        # Wait longer anyway - maybe content is loading (random)
                        fallback_wait = random_delay(2.5, 4.0)
                        await self.tab.sleep(fallback_wait)
                else:
                    # No specific selector - wait longer for full page render (random)
                    full_render_wait = random_delay(4.0, 6.0)
                    logger.info(
                        f"No wait selector specified, waiting {full_render_wait:.2f}s for full page render"
                    )
                    await self.tab.sleep(full_render_wait)

                # Verify we got actual content, not empty skeleton
                html = await self.tab.get_content()
                text_length = len(html.replace("<", "").replace(">", "").strip())

                if text_length < 5000:
                    additional_wait = random_delay(4.0, 6.0)
                    logger.warning(
                        f"HTML seems small ({text_length} chars), waiting {additional_wait:.2f}s longer for content..."
                    )
                    await self.tab.sleep(additional_wait)
                    html = await self.tab.get_content()
                    text_length = len(html.replace("<", "").replace(">", "").strip())
                    logger.info(f"After additional wait: {text_length} chars")

                # Get HTML content
                html = await self.tab.get_content()
                logger.info(f"Fetched {len(html)} bytes from {url}")
                return html

            except Exception as e:
                logger.error(f"Error navigating to {url}: {e}")
                return None

    async def close(self):
        """Close the browser."""
        if self.driver:
            try:
                self.driver.stop()
                logger.info("Closed nodriver browser")
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
