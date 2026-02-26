"""Shared mixin for database-driven spiders."""

import json
import logging

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

            # Yield item first, let Scrapy's CLOSESPIDER_ITEMCOUNT handle the limit
            yield item

            # Increment counter after yielding (so item can be processed)
            self._items_scraped += 1
        else:
            logger.warning(f"Failed to extract article from {response.url}")

    def _extract_field(self, selector, config):
        """Extract a single field using CSS or XPath selector.

        Args:
            selector: Scrapy Selector object
            config: Dict with 'css' or 'xpath' key, optional 'get_all' flag

        Returns:
            Extracted value (string, list, or None)
        """
        css = config.get("css")
        xpath = config.get("xpath")
        get_all = config.get("get_all", False)

        if css:
            result = selector.css(css)
        elif xpath:
            result = selector.xpath(xpath)
        else:
            return None

        if get_all:
            return result.getall()
        else:
            return result.get()

    def _extract_nested_list(self, selector, config, depth=0, max_depth=3):
        """Extract a list of items with nested field extraction.

        Args:
            selector: Scrapy Selector object
            config: Dict with 'selector' and 'extract' keys
            depth: Current nesting depth
            max_depth: Maximum nesting depth to prevent infinite loops

        Returns:
            List of dicts with extracted fields
        """
        if depth >= max_depth:
            logger.warning(f"Max nesting depth {max_depth} reached, stopping")
            return []

        item_selector = config.get("selector")
        extract_config = config.get("extract", {})

        if not item_selector or not extract_config:
            logger.warning("nested_list requires 'selector' and 'extract' keys")
            return []

        items = []
        for item_node in selector.css(item_selector):
            item = {}
            for field_name, field_config in extract_config.items():
                # Handle nested_list recursively
                if field_config.get("type") == "nested_list":
                    item[field_name] = self._extract_nested_list(
                        item_node, field_config, depth=depth + 1, max_depth=max_depth
                    )
                else:
                    item[field_name] = self._extract_field(item_node, field_config)
            items.append(item)

        return items

    def _make_callback(self, callback_name, callback_config):
        """Generate a dynamic callback method for custom field extraction.

        Args:
            callback_name: Name of the callback (e.g., 'parse_product')
            callback_config: Dict with 'extract' key containing field definitions

        Returns:
            Async generator function for Scrapy callback
        """

        async def dynamic_callback(response):
            """Generated callback that extracts custom fields and applies processors."""
            from core.processors import apply_processors

            extract_config = callback_config.get("extract", {})
            if not extract_config:
                logger.warning(
                    f"Callback {callback_name} has no extraction config, skipping"
                )
                return

            # Build the item with custom fields
            item = {
                "url": response.url,
                "spider_name": self.spider_name,
                "spider_id": self.spider_config.id,
                "source": "custom_callback",
                "_callback": callback_name,  # Mark as callback item for pipeline
            }

            # Extract all custom fields
            for field_name, field_config in extract_config.items():
                # Handle nested_list type
                if field_config.get("type") == "nested_list":
                    value = self._extract_nested_list(response, field_config)
                else:
                    value = self._extract_field(response, field_config)

                # Apply processors if defined
                processors = field_config.get("processors", [])
                if processors:
                    value = apply_processors(value, processors)

                # Store custom fields directly on item (pipeline will move to metadata_json)
                item[field_name] = value

            logger.info(
                f"Extracted {len(extract_config)} fields from {response.url} using {callback_name}"
            )

            yield item

            # Increment counter
            self._items_scraped += 1

        return dynamic_callback
