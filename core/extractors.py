import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict

import newspaper
import trafilatura
from bs4 import BeautifulSoup
from .schemas import ScrapedArticle

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base class for content extractors"""

    @abstractmethod
    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        """
        Extract content from HTML.

        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources (e.g. metadata)
            include_html: Whether to include raw HTML in output (for JSONL exports)

        Returns:
            ScrapedArticle object or None if extraction fails
        """
        pass


class NewspaperExtractor(BaseExtractor):
    """Extractor using newspaper4k"""

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        try:
            # newspaper4k usually fetches itself, but we can pass html
            article = newspaper.Article(url)
            article.download(input_html=html)
            article.parse()

            # Use hint if newspaper failed to find title
            title = article.title
            if not title and title_hint:
                title = title_hint.strip()

            # Basic validation before creating model
            if not title or not article.text:
                text_len = len(article.text) if article.text else 0
                logger.warning(
                    f"NewspaperExtractor validation failed: title='{title}', text_len={text_len}"
                )
                return None

            return ScrapedArticle(
                url=url,
                title=title,
                content=article.text,
                author=", ".join(article.authors) if article.authors else None,
                published_date=article.publish_date,
                source="newspaper4k",
                metadata={
                    "top_image": article.top_image,
                    "keywords": article.keywords,
                    "summary": article.summary,
                },
                html=html if include_html else None,
            )
        except Exception as e:
            logger.debug(f"NewspaperExtractor failed for {url}: {e}")
            return None


class TrafilaturaExtractor(BaseExtractor):
    """Extractor using trafilatura"""

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        try:
            # trafilatura.bare_extraction returns a Document object or dict
            extracted = trafilatura.bare_extraction(html, url=url)

            if not extracted:
                return None

            # Convert to dict if it's a Document object
            if hasattr(extracted, "as_dict"):
                data = extracted.as_dict()
            elif isinstance(extracted, dict):
                data = extracted
            else:
                return None

            if not data.get("text"):
                return None

            # Use hint if trafilatura failed to find title
            title = data.get("title")
            if not title and title_hint:
                title = title_hint.strip()

            return ScrapedArticle(
                url=url,
                title=title or "",
                content=data.get("text"),
                author=data.get("author"),
                published_date=data.get("date"),
                source="trafilatura",
                metadata={
                    "description": data.get("description"),
                    "sitename": data.get("sitename"),
                    "categories": data.get("categories"),
                    "tags": data.get("tags"),
                    "fingerprint": data.get("fingerprint"),
                    "license": data.get("license"),
                },
                html=html if include_html else None,
            )
        except Exception as e:
            logger.debug(f"TrafilaturaExtractor failed for {url}: {e}")
            return None


class CustomExtractor(BaseExtractor):
    """Extractor using custom CSS selectors"""

    def __init__(self, selectors: Dict[str, str]):
        """
        Initialize with custom selectors.

        Args:
            selectors: Dict mapping field names to CSS selectors
                      e.g., {"title": "h1.title", "content": "div.article"}
        """
        self.selectors = selectors

    def extract(
        self, url: str, html: str, title_hint: str = None, include_html: bool = False
    ) -> Optional[ScrapedArticle]:
        """
        Extract content using custom CSS selectors.

        Standard fields: title, author, content, date
        Custom fields: anything else goes into metadata
        """
        try:
            soup = BeautifulSoup(html, "lxml")

            # Extract standard fields
            title = self._extract_text(soup, self.selectors.get("title"))
            logger.debug(
                f"Extracted title: '{title}' using selector '{self.selectors.get('title')}'"
            )
            if not title and title_hint:
                title = title_hint.strip()
                logger.debug(f"Using title hint: '{title}'")

            author = self._extract_text(soup, self.selectors.get("author"))
            logger.debug(
                f"Extracted author: '{author}' using selector '{self.selectors.get('author')}'"
            )

            content = self._extract_text(soup, self.selectors.get("content"))
            content_len = len(content) if content else 0
            logger.debug(
                f"Extracted content: {content_len} chars using selector '{self.selectors.get('content')}'"
            )
            if content and content_len < 200:
                logger.debug(f"Content preview: '{content[:200]}'")

            date_str = self._extract_text(soup, self.selectors.get("date"))
            logger.debug(
                f"Extracted date: '{date_str}' using selector '{self.selectors.get('date')}'"
            )

            # Validation: at minimum need title and content
            if not title or not content:
                logger.warning(
                    f"CustomExtractor validation failed: title='{title}', content_len={content_len}"
                )
                return None

            # Parse date if present
            published_date = None
            if date_str:
                try:
                    from dateutil import parser

                    published_date = parser.parse(date_str)
                except Exception as e:
                    logger.debug(f"Failed to parse date '{date_str}': {e}")

            # Extract custom fields into metadata
            metadata = {}
            for field_name, selector in self.selectors.items():
                # Skip standard fields
                if field_name in ["title", "author", "content", "date"]:
                    continue

                # Extract custom field
                value = self._extract_text(soup, selector)
                if value:
                    metadata[field_name] = value

            return ScrapedArticle(
                url=url,
                title=title,
                content=content,
                author=author,
                published_date=published_date,
                source="custom",
                metadata=metadata,
                html=html if include_html else None,
            )

        except Exception as e:
            logger.error(f"CustomExtractor failed for {url}: {e}")
            return None

    def _extract_text(
        self, soup: BeautifulSoup, selector: Optional[str]
    ) -> Optional[str]:
        """
        Extract text from HTML using CSS selector.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string

        Returns:
            Extracted text or None
        """
        if not selector:
            return None

        try:
            # Find element
            element = soup.select_one(selector)
            if not element:
                logger.debug(f"Selector '{selector}' found no elements")
                return None

            # Get text and clean it
            text = element.get_text(separator=" ", strip=True)
            return text if text else None

        except Exception as e:
            logger.debug(f"Error extracting with selector '{selector}': {e}")
            return None


class SmartExtractor:
    """
    Intelligent extractor that tries multiple strategies in order.
    Strategies:
    1. 'custom': Use custom CSS selectors if provided
    2. 'newspaper': Use newspaper4k on provided HTML
    3. 'trafilatura': Use trafilatura on provided HTML
    4. 'playwright': Fetch rendered HTML via browser, then try trafilatura
    """

    def __init__(
        self, strategies: List[str] = None, custom_selectors: Dict[str, str] = None
    ):
        self.strategies = strategies or ["newspaper", "trafilatura", "playwright"]
        self.custom_selectors = custom_selectors

    async def extract(
        self,
        url: str,
        html: str,
        title_hint: str = None,
        include_html: bool = False,
        wait_for_selector: str = None,
        additional_delay: float = 0,
        enable_scroll: bool = False,
        max_scrolls: int = 5,
        scroll_delay: float = 1.0,
    ) -> Optional[ScrapedArticle]:
        """
        Async version of extract method with Playwright support.

        Tries each strategy in order, including Playwright for JS-rendered content.
        Falls back to next strategy if one fails.

        Args:
            url: The URL of the page
            html: The raw HTML content
            title_hint: Optional title extracted from other sources
            include_html: Whether to include raw HTML in output
            wait_for_selector: CSS selector to wait for when using Playwright
            additional_delay: Additional seconds to wait after page load when using Playwright
            enable_scroll: Whether to perform infinite scroll when using Playwright
            max_scrolls: Maximum number of scrolls to perform
            scroll_delay: Delay between scrolls in seconds
        """
        # Try each strategy in order
        for strategy in self.strategies:
            if strategy == "custom":
                if self.custom_selectors:
                    logger.info(f"Trying custom extractor for {url}")
                    try:
                        result = await asyncio.to_thread(
                            CustomExtractor(self.custom_selectors).extract,
                            url,
                            html,
                            title_hint,
                            include_html,
                        )
                        if result:
                            logger.info(f"Successfully extracted {url} using custom")
                            return result
                        else:
                            logger.debug(
                                f"Custom extractor returned no result for {url}"
                            )
                    except Exception as e:
                        logger.debug(f"Custom extractor failed for {url}: {e}")
                else:
                    logger.debug(
                        "Skipping 'custom' strategy - no custom selectors provided"
                    )

            elif strategy == "newspaper":
                logger.info(f"Trying newspaper extractor for {url}")
                try:
                    result = await asyncio.to_thread(
                        NewspaperExtractor().extract,
                        url,
                        html,
                        title_hint,
                        include_html,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using newspaper")
                        return result
                    else:
                        logger.debug(
                            f"Newspaper extractor returned no result for {url}"
                        )
                except Exception as e:
                    logger.debug(f"Newspaper extractor failed for {url}: {e}")

            elif strategy == "trafilatura":
                logger.info(f"Trying trafilatura extractor for {url}")
                try:
                    result = await asyncio.to_thread(
                        TrafilaturaExtractor().extract,
                        url,
                        html,
                        title_hint,
                        include_html,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using trafilatura")
                        return result
                    else:
                        logger.debug(
                            f"Trafilatura extractor returned no result for {url}"
                        )
                except Exception as e:
                    logger.debug(f"Trafilatura extractor failed for {url}: {e}")

            elif strategy == "playwright":
                logger.info(f"Trying playwright extractor for {url}")
                try:
                    result = await self._extract_with_playwright_async(
                        url,
                        title_hint,
                        include_html,
                        wait_for_selector,
                        additional_delay,
                        enable_scroll,
                        max_scrolls,
                        scroll_delay,
                    )
                    if result:
                        logger.info(f"Successfully extracted {url} using playwright")
                        return result
                    else:
                        logger.debug(
                            f"Playwright extractor returned no result for {url}"
                        )
                except Exception as e:
                    logger.debug(f"Playwright extractor failed for {url}: {e}")

        # All extractors failed
        logger.error(f"All extractors failed for {url}")
        return None

    async def _extract_with_playwright_async(
        self,
        url: str,
        title_hint: str = None,
        include_html: bool = False,
        wait_for_selector: str = None,
        additional_delay: float = 0,
        enable_scroll: bool = False,
        max_scrolls: int = 5,
        scroll_delay: float = 1.0,
    ) -> Optional[ScrapedArticle]:
        """
        Fetch via Playwright (async) and extract using Trafilatura

        Args:
            url: The URL to fetch
            title_hint: Optional title hint
            include_html: Whether to include raw HTML in output
            wait_for_selector: CSS selector to wait for after navigation
            additional_delay: Additional seconds to wait after page load
            enable_scroll: Whether to perform infinite scroll
            max_scrolls: Maximum number of scrolls to perform
            scroll_delay: Delay between scrolls in seconds
        """
        try:
            logger.info(f"Starting Playwright fetch for {url}")
            if wait_for_selector:
                logger.info(f"Will wait for selector: {wait_for_selector}")
            if additional_delay > 0:
                logger.info(f"Will wait additional {additional_delay} seconds")
            if enable_scroll:
                logger.info(
                    f"Will perform infinite scroll: {max_scrolls} scrolls with {scroll_delay}s delay"
                )

            from utils.browser import BrowserClient

            async with BrowserClient() as browser:
                logger.info("BrowserClient started")
                if await browser.goto(
                    url,
                    wait_for_selector,
                    additional_delay,
                    enable_scroll,
                    max_scrolls,
                    scroll_delay,
                ):
                    logger.info("Browser navigated")
                    html = await browser.get_html()
                    logger.info(f"Got HTML from browser: {len(html)} bytes")
                    if html:
                        # Try Trafilatura on rendered HTML
                        return await asyncio.to_thread(
                            TrafilaturaExtractor().extract,
                            url,
                            html,
                            title_hint,
                            include_html,
                        )
                else:
                    logger.warning("Browser navigation failed")
        except Exception as e:
            logger.error(f"Playwright fetch failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
        return None
