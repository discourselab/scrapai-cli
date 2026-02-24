"""Shared mixin for database-driven spiders."""

import json
import logging
from scrapy.exceptions import CloseSpider

logger = logging.getLogger(__name__)


class BaseDBSpiderMixin:
    """Mixin providing shared logic for DatabaseSpider and SitemapDatabaseSpider."""

    def _load_settings_from_db(self, spider_record):
        """Deserialize settings from DB spider record into custom_settings."""
        if not getattr(self, "custom_settings", None):
            self.custom_settings = {}

        if not spider_record.settings:
            return

        for s in spider_record.settings:
            val = s.value
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                if isinstance(val, str):
                    if val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    elif val.isdigit():
                        val = int(val)
            self.custom_settings[s.key] = val

    def _setup_cloudflare_handlers(self):
        """Configure Cloudflare download handlers if enabled."""
        cf_enabled = self.custom_settings.get("CLOUDFLARE_ENABLED", False)
        if cf_enabled:
            logger.info(f"Cloudflare bypass mode enabled for {self.spider_name}")
            self.custom_settings["DOWNLOAD_HANDLERS"] = {
                "http": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                "https": "handlers.cloudflare_handler.CloudflareDownloadHandler",
            }

    @classmethod
    def _apply_cf_to_crawler(cls, spider, crawler):
        """Apply Cloudflare handlers to crawler settings after spider init."""
        if hasattr(spider, "custom_settings"):
            cf_enabled = spider.custom_settings.get("CLOUDFLARE_ENABLED", False)
            if cf_enabled:
                logger.info(
                    "[from_crawler] Applying Cloudflare handlers to crawler settings"
                )
                crawler.settings.set(
                    "DOWNLOAD_HANDLERS",
                    {
                        "http": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                        "https": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                    },
                    priority="spider",
                )

        spider._item_limit = crawler.settings.getint("CLOSESPIDER_ITEMCOUNT", 0)
        if spider._item_limit:
            logger.info(f"Item limit set to {spider._item_limit}")

    async def _extract_article(self, response, source_label="database_spider"):
        """Shared article extraction logic."""
        default_strategies = ["newspaper", "trafilatura", "playwright"]

        strategies = self.custom_settings.get("EXTRACTOR_ORDER")
        if isinstance(strategies, str):
            try:
                strategies = json.loads(strategies.replace("'", '"'))
            except Exception:
                strategies = None
        if not isinstance(strategies, list):
            strategies = default_strategies

        logger.info(f"Using strategies: {strategies}")

        custom_selectors = self.custom_settings.get("CUSTOM_SELECTORS")
        if isinstance(custom_selectors, str):
            try:
                custom_selectors = json.loads(custom_selectors.replace("'", '"'))
            except Exception:
                custom_selectors = None

        if custom_selectors:
            logger.info(f"Using custom selectors: {list(custom_selectors.keys())}")

        from core.extractors import SmartExtractor

        extractor = SmartExtractor(
            strategies=strategies, custom_selectors=custom_selectors
        )

        logger.info(f"Processing {response.url} (Length: {len(response.text)})")
        title_hint = response.css("title::text").get()
        if title_hint:
            logger.info(f"Title tag: {title_hint}")

        include_html = self.settings.getbool("INCLUDE_HTML_IN_OUTPUT", False)

        wait_for_selector = self.custom_settings.get("PLAYWRIGHT_WAIT_SELECTOR")
        wait_delay = self.custom_settings.get("PLAYWRIGHT_DELAY", 0)
        enable_scroll = self.custom_settings.get("INFINITE_SCROLL", False)
        max_scrolls = self.custom_settings.get("MAX_SCROLLS", 5)
        scroll_delay = self.custom_settings.get("SCROLL_DELAY", 1.0)

        if wait_for_selector:
            logger.info(f"Playwright will wait for selector: {wait_for_selector}")
        if wait_delay and float(wait_delay) > 0:
            logger.info(f"Playwright will wait additional {wait_delay} seconds")
        if enable_scroll:
            logger.info(
                f"Infinite scroll enabled: {max_scrolls} scrolls with {scroll_delay}s delay"
            )

        article = await extractor.extract(
            response.url,
            response.text,
            title_hint=title_hint,
            include_html=include_html,
            wait_for_selector=wait_for_selector,
            additional_delay=float(wait_delay) if wait_delay else 0,
            enable_scroll=bool(enable_scroll),
            max_scrolls=int(max_scrolls) if max_scrolls else 5,
            scroll_delay=float(scroll_delay) if scroll_delay else 1.0,
        )

        if article:
            item = article.model_dump()
            item["spider_name"] = self.spider_name
            item["spider_id"] = self.spider_config.id
            item["source"] = source_label

            self._items_scraped += 1
            if self._item_limit and self._items_scraped >= self._item_limit:
                logger.info(
                    f"Reached item limit ({self._item_limit}), stopping spider immediately"
                )
                yield item
                raise CloseSpider(f"Item limit reached: {self._item_limit}")

            yield item
        else:
            logger.warning(f"Failed to extract article from {response.url}")
