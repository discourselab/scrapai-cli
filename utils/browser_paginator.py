"""Browser-driven listing paginator.

Opens a listing URL in CloakBrowser, clicks the "Next" button through all
paginated results, and streams article URLs selected by a CSS selector as
each page is walked.

Useful for JS-paginated listing pages where article URLs aren't discoverable
via LinkExtractor on a single page load (WP content lists, infinite-scroll
tiles that still expose a Next button, etc.).
"""

import asyncio
import logging
from typing import AsyncIterator, List, Optional

from utils.cf_browser import CloudflareBrowserClient

logger = logging.getLogger(__name__)


class BrowserPaginator:
    """Paginate through a JS-driven listing and stream article URLs."""

    def __init__(
        self,
        url: str,
        link_selector: str,
        next_selector: str,
        wait_selector: Optional[str] = None,
        max_pages: int = 100,
        click_delay: float = 1.5,
        headless: bool = True,
    ):
        self.url = url
        self.link_selector = link_selector
        self.next_selector = next_selector
        self.wait_selector = wait_selector
        self.max_pages = max_pages
        self.click_delay = click_delay
        self.headless = headless

    async def stream(self) -> AsyncIterator[str]:
        """Open the listing and yield article URLs as each page is walked.

        Streams so callers can enqueue downstream requests progressively
        rather than waiting for every page to be collected first.

        Stops on: Next button missing, click failure, max_pages reached,
        or a full page yielding zero new URLs.
        """
        seen: set = set()
        total = 0

        async with CloudflareBrowserClient(headless=self.headless) as browser:
            logger.info(f"[paginator] Loading listing: {self.url}")
            html = await browser.fetch(self.url, wait_selector=self.wait_selector)
            if not html:
                logger.error(f"[paginator] Failed to load {self.url}")
                return

            page = browser.page

            for page_num in range(1, self.max_pages + 1):
                urls = await self._collect_page_urls(page)
                new_urls = [u for u in urls if u not in seen]
                for u in new_urls:
                    seen.add(u)
                    total += 1
                    yield u

                logger.info(
                    f"[paginator] Page {page_num}: +{len(new_urls)} new "
                    f"(total: {total})"
                )

                if not new_urls and page_num > 1:
                    logger.info(f"[paginator] No new URLs on page {page_num}, stopping")
                    break

                if not await self._click_next(page, page_num):
                    break

                await self._wait_for_refresh(page)

        logger.info(f"[paginator] Done — {total} URLs from {self.url}")

    async def _collect_page_urls(self, page) -> List[str]:
        """Read hrefs from elements matching link_selector on the current page."""
        try:
            return await page.eval_on_selector_all(
                self.link_selector,
                "(els) => els.map(el => el.href).filter(h => h)",
            )
        except Exception as e:
            logger.warning(f"[paginator] Failed to read links: {e}")
            return []

    async def _click_next(self, page, page_num: int) -> bool:
        """Click the Next button. Returns False if no more pages."""
        try:
            locator = page.locator(self.next_selector).first
            count = await locator.count()
        except Exception as e:
            logger.warning(f"[paginator] Next locator error: {e}")
            return False

        if count == 0:
            logger.info(f"[paginator] No next button on page {page_num}, stopping")
            return False

        try:
            await locator.click(timeout=5000)
            return True
        except Exception as e:
            logger.warning(f"[paginator] Click failed on page {page_num}: {e}")
            return False

    async def _wait_for_refresh(self, page):
        """Wait for new content to load after clicking Next."""
        await asyncio.sleep(self.click_delay)
        if self.wait_selector:
            try:
                await page.wait_for_selector(self.wait_selector, timeout=10000)
            except Exception as e:
                logger.debug(f"[paginator] wait_for_selector timed out: {e}")
