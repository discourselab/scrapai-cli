import scrapy
from scrapy.spiders import SitemapSpider
from scrapy.exceptions import CloseSpider
from core.db import get_db
from core.models import Spider
import logging
import json

logger = logging.getLogger(__name__)

class SitemapDatabaseSpider(SitemapSpider):
    """
    Spider for crawling sites via sitemap.xml files.
    Automatically extracts all URLs from sitemap and crawls them.
    """
    name = "sitemap_database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        # Support both direct instantiation and dynamic class generation
        if not spider_name:
            spider_name = getattr(self.__class__, '_spider_name', None)

        if not spider_name:
            raise ValueError("spider_name argument is required")

        self.spider_name = spider_name
        self._load_config()
        super().__init__(*args, **kwargs)

        # Initialize item counter for immediate stop on limit
        self._items_scraped = 0
        self._item_limit = None

    def _load_config(self):
        """Load spider configuration from database"""
        db = next(get_db())
        spider = db.query(Spider).filter(Spider.name == self.spider_name).first()

        if not spider:
            raise ValueError(f"Spider '{self.spider_name}' not found in database")

        if not spider.active:
            raise ValueError(f"Spider '{self.spider_name}' is inactive")

        self.spider_config = spider
        self.allowed_domains = spider.allowed_domains

        # For sitemap spider, start_urls become sitemap_urls
        self.sitemap_urls = spider.start_urls

        logger.info(f"Sitemap spider configured with sitemap URLs: {self.sitemap_urls}")

        # Sitemap rules - scrape all URLs from sitemap by default
        # Different page types handled by extraction strategies
        self.sitemap_rules = [
            ('/', 'parse_article'),  # Parse all URLs - extraction will handle page type detection
        ]

        logger.info(f"Sitemap spider will scrape all URLs from sitemap")

        # Apply settings
        if spider.settings:
            if not getattr(self, 'custom_settings', None):
                self.custom_settings = {}

            for s in spider.settings:
                val = s.value
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    if isinstance(val, str):
                        if val.lower() == 'true':
                            val = True
                        elif val.lower() == 'false':
                            val = False
                        elif val.isdigit():
                            val = int(val)

                self.custom_settings[s.key] = val

        # Check if Cloudflare mode enabled
        cf_enabled = self.custom_settings.get('CLOUDFLARE_ENABLED', False)

        if cf_enabled:
            # Enable CF download handler only for this spider
            logger.info(f"Cloudflare bypass mode enabled for sitemap spider {self.spider_name}")
            if not getattr(self, 'custom_settings', None):
                self.custom_settings = {}
            self.custom_settings['DOWNLOAD_HANDLERS'] = {
                'http': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
                'https': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
            }
        # If not CF enabled, use default Scrapy HTTP handler

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Called by Scrapy to create spider instance from crawler."""
        spider = super(SitemapDatabaseSpider, cls).from_crawler(crawler, *args, **kwargs)
        spider._item_limit = crawler.settings.getint('CLOSESPIDER_ITEMCOUNT', 0)
        if spider._item_limit:
            logger.info(f"Item limit set to {spider._item_limit} for sitemap spider")
        return spider

    async def parse_article(self, response):
        """
        Parse article page from sitemap.
        Uses same extraction logic as DatabaseSpider.
        """
        # Initialize SmartExtractor with configured strategies
        default_strategies = ['newspaper', 'trafilatura', 'playwright']

        strategies = self.custom_settings.get('EXTRACTOR_ORDER')

        if isinstance(strategies, str):
            try:
                strategies = json.loads(strategies.replace("'", '"'))
            except json.JSONDecodeError:
                strategies = default_strategies

        if not strategies or not isinstance(strategies, list):
            strategies = default_strategies

        logger.info(f"Using strategies: {strategies}")

        # Get custom selectors if configured
        custom_selectors = self.custom_settings.get('CUSTOM_SELECTORS', {})

        # Initialize extractor
        from core.extractors import SmartExtractor
        extractor = SmartExtractor(strategies=strategies, custom_selectors=custom_selectors)

        # Extract
        logger.info(f"Processing {response.url} (Length: {len(response.text)})")
        title_hint = response.css('title::text').get()
        if title_hint:
            logger.info(f"Title tag: {title_hint}")

        # Check if HTML should be included in output
        include_html = self.settings.getbool('INCLUDE_HTML_IN_OUTPUT', False)

        # Get Playwright wait configuration
        wait_for_selector = self.custom_settings.get('PLAYWRIGHT_WAIT_SELECTOR')
        wait_delay = self.custom_settings.get('PLAYWRIGHT_DELAY', 0)

        # Get infinite scroll configuration
        enable_scroll = self.custom_settings.get('INFINITE_SCROLL', False)
        max_scrolls = self.custom_settings.get('MAX_SCROLLS', 5)
        scroll_delay = self.custom_settings.get('SCROLL_DELAY', 1.0)

        # Log configuration
        if wait_for_selector:
            logger.info(f"Playwright will wait for selector: {wait_for_selector}")
        if wait_delay and float(wait_delay) > 0:
            logger.info(f"Playwright will wait additional {wait_delay} seconds")
        if enable_scroll:
            logger.info(f"Infinite scroll enabled: {max_scrolls} scrolls with {scroll_delay}s delay")

        # Use async extraction
        article = await extractor.extract_async(
            response.url,
            response.text,
            title_hint=title_hint,
            include_html=include_html,
            wait_for_selector=wait_for_selector,
            additional_delay=float(wait_delay) if wait_delay else 0,
            enable_scroll=bool(enable_scroll),
            max_scrolls=int(max_scrolls) if max_scrolls else 5,
            scroll_delay=float(scroll_delay) if scroll_delay else 1.0
        )

        if article:
            # Convert Pydantic model to dict
            item = article.dict()

            # Add spider metadata
            item['spider_name'] = self.spider_name
            item['spider_id'] = self.spider_config.id
            item['source'] = 'sitemap_spider'
            # Check item limit for immediate stop
            self._items_scraped += 1
            if self._item_limit and self._items_scraped >= self._item_limit:
                logger.info(f"Reached item limit ({self._item_limit}), stopping spider immediately")
                raise CloseSpider(f'Item limit reached: {self._item_limit}')

            yield item
        else:
            logger.warning(f"Failed to extract article from {response.url}")

    def sitemap_filter(self, entries):
        """
        Filter sitemap entries before processing.
        Can be overridden for custom filtering logic.
        """
        for entry in entries:
            # Log sitemap entry
            logger.debug(f"Sitemap entry: {entry['loc']}")
            yield entry
