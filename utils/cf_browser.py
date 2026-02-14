"""
Cloudflare bypass browser client using nodriver.

This module provides a persistent browser session that can solve Cloudflare
challenges once and reuse the verified session for subsequent requests.
"""

import os
import asyncio
import logging
from typing import Optional

import nodriver as uc
from nodriver_cf_verify import CFVerify

logger = logging.getLogger(__name__)


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
        post_cf_delay: int = 5
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
        browser_path = os.getenv('CHROME_PATH')
        if not browser_path:
            # Try common paths based on OS
            import sys
            import glob

            if sys.platform == 'darwin':
                # macOS - Playwright Chromium
                pattern = os.path.expanduser('~/Library/Caches/ms-playwright/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium')
                matches = glob.glob(pattern)
                if matches:
                    browser_path = matches[0]
                    logger.info(f"Found Playwright Chromium: {browser_path}")
            else:
                # Linux
                playwright_chrome = os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome')
                matches = glob.glob(playwright_chrome)
                if matches:
                    browser_path = matches[0]
                    logger.info(f"Found Playwright Chromium: {browser_path}")

        browser_args = [
            '--disable-dev-shm-usage',
        ]

        try:
            self.driver = await uc.start(
                headless=self.headless,
                browser_executable_path=browser_path if browser_path and os.path.exists(browser_path) else None,
                browser_args=browser_args,
                sandbox=False  # Disable sandbox
            )
            logger.info(f"Started nodriver browser for Cloudflare bypass")
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
                _browser_tab=self.tab,
                _debug=logger.level <= logging.DEBUG
            )

            success = await cf_verify.verify(
                _max_retries=self.cf_max_retries,
                _interval_between_retries=self.cf_retry_interval,
                _reload_page_after_n_retries=0
            )

            if not success:
                logger.error(f"Failed to verify Cloudflare for {url}")
                return False

            logger.info(f"Cloudflare verified successfully for {url}")
            self.cf_verified = True

            # Wait for content to load after CF verification
            logger.info(f"Waiting {self.post_cf_delay}s for content to load after CF verification")
            await self.tab.sleep(self.post_cf_delay)

            # Additional wait to ensure full page render
            logger.info("Waiting additional time for full page render...")
            await self.tab.sleep(3)

            return True

        except Exception as e:
            logger.error(f"Error during Cloudflare verification: {e}")
            return False

    async def fetch(self, url: str, wait_selector: Optional[str] = None, wait_timeout: int = 10) -> Optional[str]:
        """Fetch a URL using the verified session.

        On first call, this will verify Cloudflare. Subsequent calls reuse
        the verified session.

        Args:
            url: The URL to fetch
            wait_selector: CSS selector to wait for before extracting HTML (e.g., 'h1.title-med-1')
            wait_timeout: Maximum seconds to wait for selector (default: 10)

        Returns:
            HTML content as string, or None if fetch failed
        """
        if not self.cf_verified:
            # First request - need to verify CF
            success = await self.verify_cloudflare(url)
            if not success:
                return None
        else:
            # Subsequent requests - reuse verified session
            logger.info(f"Fetching {url} using verified Cloudflare session")
            try:
                # Navigate to URL (timeout set at browser config level)
                await self.tab.get(url)

                # Wait for page to fully load (not just network idle)
                logger.debug("Waiting for page to stabilize...")
                await self.tab.sleep(2)  # Initial wait for JS to start

                # If wait_selector provided, wait for it to appear
                if wait_selector:
                    logger.info(f"Waiting for selector '{wait_selector}' to appear (timeout: {wait_timeout}s)")
                    try:
                        # Wait for the selector to be present in the DOM
                        await self.tab.select(wait_selector, timeout=wait_timeout)
                        logger.info(f"Selector '{wait_selector}' found")
                        # Additional wait to ensure full rendering
                        await self.tab.sleep(2)
                    except Exception as e:
                        logger.warning(f"Timeout waiting for selector '{wait_selector}': {e}")
                        # Wait longer anyway - maybe content is loading
                        await self.tab.sleep(3)
                else:
                    # No specific selector - wait longer for full page render
                    logger.info("No wait selector specified, waiting for full page render")
                    await self.tab.sleep(5)

                # Verify we got actual content, not empty skeleton
                html = await self.tab.get_content()
                text_length = len(html.replace('<', '').replace('>', '').strip())

                if text_length < 5000:
                    logger.warning(f"HTML seems small ({text_length} chars), waiting longer for content...")
                    await self.tab.sleep(5)
                    html = await self.tab.get_content()
                    text_length = len(html.replace('<', '').replace('>', '').strip())
                    logger.info(f"After additional wait: {text_length} chars")

            except Exception as e:
                logger.error(f"Error navigating to {url}: {e}")
                return None

        # Get HTML content
        try:
            html = await self.tab.get_content()
            logger.info(f"Fetched {len(html)} bytes from {url}")
            return html
        except Exception as e:
            logger.error(f"Error getting content from {url}: {e}")
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
