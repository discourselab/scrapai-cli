"""
Scrapy download handler for Cloudflare-protected sites.

This handler routes all requests through a persistent nodriver browser session
that can solve Cloudflare challenges and reuse the verified session.
"""

import asyncio
import logging
from typing import Callable

from scrapy.http import HtmlResponse, Request
from twisted.internet import defer
from twisted.internet.defer import Deferred

logger = logging.getLogger(__name__)


class CloudflareDownloadHandler:
    """
    Scrapy download handler that uses persistent nodriver browser
    for Cloudflare bypass.

    This handler:
    1. Opens a persistent browser when spider starts
    2. Solves Cloudflare challenge on first request
    3. Reuses verified session for all subsequent requests
    4. Closes browser when spider closes

    NOTE: Browser instance is shared across all handler instances (class-level)
    to prevent Scrapy from creating multiple browsers when running concurrent requests.
    """

    # Class-level (shared) browser state
    _shared_browser = None
    _browser_started = False
    _browser_startup_lock = asyncio.Lock()  # Protect browser startup (1 at a time)

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

    def download_request(self, request: Request, spider) -> Deferred:
        """Handle request by routing through persistent browser if CF enabled.

        Args:
            request: Scrapy request to download
            spider: Scrapy spider instance

        Returns:
            Deferred that will fire with HtmlResponse or error
        """
        # Check if Cloudflare mode is enabled for this spider
        spider_settings = getattr(spider, 'custom_settings', {})
        cf_enabled = spider_settings.get('CLOUDFLARE_ENABLED', False)

        # If CF not enabled, use default Scrapy downloader
        if not cf_enabled:
            from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
            handler = HTTP11DownloadHandler(self.crawler.settings)
            return handler.download_request(request, spider)

        # CF enabled - use browser
        dfd = Deferred()

        async def fetch_async():
            """Fetch URL using CF browser and return response."""
            try:
                # Protect browser startup with a lock (prevent multiple browsers)
                async with CloudflareDownloadHandler._browser_startup_lock:
                    if not CloudflareDownloadHandler._browser_started:
                        from utils.cf_browser import CloudflareBrowserClient

                        # Get CF settings from spider
                        spider_settings = getattr(spider, 'custom_settings', {})
                        cf_max_retries = spider_settings.get('CF_MAX_RETRIES', 5)
                        cf_retry_interval = spider_settings.get('CF_RETRY_INTERVAL', 1)
                        cf_post_delay = spider_settings.get('CF_POST_DELAY', 5)

                        logger.info(
                            f"CloudflareDownloadHandler: Starting shared browser "
                            f"(single tab, sequential fetching, retries={cf_max_retries}, "
                            f"interval={cf_retry_interval}s, delay={cf_post_delay}s)"
                        )

                        CloudflareDownloadHandler._shared_browser = CloudflareBrowserClient(
                            headless=False,
                            cf_max_retries=cf_max_retries,
                            cf_retry_interval=cf_retry_interval,
                            post_cf_delay=cf_post_delay
                        )

                        await CloudflareDownloadHandler._shared_browser.start()
                        CloudflareDownloadHandler._browser_started = True
                        logger.info("CloudflareDownloadHandler: Shared browser started (single tab mode)")

                # Fetch using single tab (sequential, lock handled by browser client)
                logger.debug(f"CloudflareDownloadHandler: Fetching {request.url}")

                # Get wait selector settings
                spider_settings = getattr(spider, 'custom_settings', {})
                wait_selector = spider_settings.get('CF_WAIT_SELECTOR')
                wait_timeout = spider_settings.get('CF_WAIT_TIMEOUT', 10)

                # Fetch through persistent browser with optional wait selector
                html = await CloudflareDownloadHandler._shared_browser.fetch(
                    request.url,
                    wait_selector=wait_selector,
                    wait_timeout=wait_timeout
                )
                logger.debug(f"CloudflareDownloadHandler: Completed {request.url}")

                if html:
                    # Create Scrapy response
                    response = HtmlResponse(
                        url=request.url,
                        body=html.encode('utf-8'),
                        encoding='utf-8',
                        request=request
                    )
                    dfd.callback(response)
                else:
                    error_msg = f"Failed to fetch {request.url} with Cloudflare bypass"
                    logger.error(f"CloudflareDownloadHandler: {error_msg}")
                    dfd.errback(Exception(error_msg))

            except Exception as e:
                logger.error(f"CloudflareDownloadHandler error for {request.url}: {e}")
                dfd.errback(e)

        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

        # Schedule async fetch
        asyncio.ensure_future(fetch_async(), loop=loop)

        return dfd
