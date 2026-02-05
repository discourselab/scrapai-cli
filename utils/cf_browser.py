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
            # Try common paths
            playwright_chrome = os.path.expanduser(
                '~/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome'
            )
            if os.path.exists(playwright_chrome):
                browser_path = playwright_chrome

        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ]

        try:
            self.driver = await uc.start(
                headless=self.headless,
                browser_executable_path=browser_path if browser_path and os.path.exists(browser_path) else None,
                browser_args=browser_args,
                sandbox=False  # Disable sandbox - required when running as root
            )
            logger.info("Started nodriver browser for Cloudflare bypass")
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
            # Navigate to URL
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
            await self.tab.sleep(self.post_cf_delay)
            return True

        except Exception as e:
            logger.error(f"Error during Cloudflare verification: {e}")
            return False

    async def fetch(self, url: str) -> Optional[str]:
        """Fetch a URL using the verified session.

        On first call, this will verify Cloudflare. Subsequent calls reuse
        the verified session.

        Args:
            url: The URL to fetch

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
                await self.tab.get(url)
                # Short delay for page load
                await self.tab.sleep(1)
            except Exception as e:
                logger.error(f"Error navigating to {url}: {e}")
                return None

        # Get HTML content
        try:
            html = await self.tab.get_content()
            logger.debug(f"Fetched {len(html)} bytes from {url}")
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
