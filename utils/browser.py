#!/usr/bin/env python3
import logging
import asyncio
from typing import Dict, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class BrowserClient:
    """
    Headless browser client for handling JavaScript-based pagination and dynamic content.
    Uses Playwright to interact with websites that require JavaScript for pagination.
    """

    def __init__(self, headless: bool = True, proxy: Dict[str, str] = None):
        self.headless = headless
        self.proxy = proxy
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Start the browser"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            context_options = {
                "viewport": {"width": 1366, "height": 768},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "extra_http_headers": {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Sec-CH-UA': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'Sec-CH-UA-Mobile': '?0',
                    'Sec-CH-UA-Platform': '"macOS"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                },
                "java_script_enabled": True,
                "locale": 'en-US'
            }

            if self.proxy:
                context_options["proxy"] = self.proxy
                logger.info(f"Using proxy: {self.proxy['server']}")

            self.context = await self.browser.new_context(**context_options)
            self.page = await self.context.new_page()

            # Add stealth measures to avoid bot detection
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)
            logger.info("Browser started successfully")
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            raise

    async def close(self):
        """Close the browser and clean up resources"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            logger.info("Browser closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

    async def goto(self, url: str, wait_for_selector: str = None, additional_delay: float = 0,
                   enable_scroll: bool = False, max_scrolls: int = 5, scroll_delay: float = 1.0) -> bool:
        """
        Navigate to a URL with optional wait conditions and infinite scroll support
        """
        try:
            await self.page.goto(url, wait_until="networkidle", timeout=60000)
            logger.info(f"Navigated to {url}")

            if wait_for_selector:
                try:
                    await self.page.wait_for_selector(wait_for_selector, timeout=30000)
                    logger.info(f"Selector '{wait_for_selector}' found on {url}")
                except Exception as e:
                    logger.warning(f"Timeout waiting for selector '{wait_for_selector}' on {url}: {e}")

            if additional_delay > 0:
                logger.info(f"Waiting additional {additional_delay} seconds for JS to complete")
                await asyncio.sleep(additional_delay)

            if enable_scroll:
                logger.info(f"Starting infinite scroll: {max_scrolls} scrolls with {scroll_delay}s delay")
                for i in range(max_scrolls):
                    try:
                        prev_height = await self.page.evaluate("document.body.scrollHeight")
                        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        logger.info(f"Scroll {i+1}/{max_scrolls} completed")
                        await asyncio.sleep(scroll_delay)
                        new_height = await self.page.evaluate("document.body.scrollHeight")
                        if new_height == prev_height:
                            logger.info(f"No new content loaded after scroll {i+1}, stopping")
                            break
                    except Exception as e:
                        logger.warning(f"Error during scroll {i+1}: {e}")
                        break
                logger.info(f"Infinite scroll completed")

            return True
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            return False

    async def get_html(self) -> str:
        """Get the current page HTML"""
        try:
            return await self.page.content()
        except Exception as e:
            logger.error(f"Error getting page HTML: {e}")
            return ""
