import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.exceptions import CloseSpider
from core.db import get_db
from core.models import Spider, SpiderRule
import logging
import json

logger = logging.getLogger(__name__)

class DatabaseSpider(CrawlSpider):
    name = "database_spider"
    
    def __init__(self, spider_name=None, *args, **kwargs):
        # Support both direct instantiation and dynamic class generation
        if not spider_name:
            # Check if this is a dynamically generated class with _spider_name
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
        self.start_urls = spider.start_urls
        
        # Compile rules
        self.rules = []
        # Sort rules by priority (descending)
        db_rules = sorted(spider.rules, key=lambda r: r.priority, reverse=True)
        
        for r in db_rules:
            # Build LinkExtractor arguments
            le_kwargs = {}
            if r.allow_patterns:
                le_kwargs['allow'] = r.allow_patterns
            if r.deny_patterns:
                le_kwargs['deny'] = r.deny_patterns
            if r.restrict_xpaths:
                le_kwargs['restrict_xpaths'] = r.restrict_xpaths
            if r.restrict_css:
                le_kwargs['restrict_css'] = r.restrict_css
                
            # Get callback method
            callback = None
            if r.callback:
                if hasattr(self, r.callback):
                    callback = r.callback
                else:
                    self.logger.warning(f"Callback '{r.callback}' not found on spider, ignoring rule")
                    continue
            
            self.rules.append(
                Rule(
                    LinkExtractor(**le_kwargs),
                    callback=callback,
                    follow=r.follow
                )
            )
            
        # Apply settings
        if spider.settings:
            if not getattr(self, 'custom_settings', None):
                self.custom_settings = {}

            for s in spider.settings:
                # Convert value to appropriate type if needed
                val = s.value
                try:
                    # Try parsing as JSON (handles lists, dicts, bools, ints, etc.)
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    # Fallback for simple strings that aren't valid JSON
                    if isinstance(val, str): # Ensure val is a string before calling .lower() or .isdigit()
                        if val.lower() == 'true':
                            val = True
                        elif val.lower() == 'false':
                            val = False
                        elif val.isdigit():
                            val = int(val)

                self.custom_settings[s.key] = val

        # Check if Cloudflare mode enabled and set DOWNLOAD_HANDLERS BEFORE Scrapy reads settings
        cf_enabled = self.custom_settings.get('CLOUDFLARE_ENABLED', False)

        if cf_enabled:
            # Enable CF download handler only for this spider
            logger.info(f"Cloudflare bypass mode enabled for {self.spider_name}")
            # CRITICAL: Must set DOWNLOAD_HANDLERS in custom_settings BEFORE spider starts
            self.custom_settings['DOWNLOAD_HANDLERS'] = {
                'http': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
                'https': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
            }
            logger.info(f"Set DOWNLOAD_HANDLERS: {self.custom_settings.get('DOWNLOAD_HANDLERS')}")
        # If not CF enabled, use default Scrapy HTTP handler (no custom_settings needed)

    def parse_start_url(self, response):
        """
        Override CrawlSpider's parse_start_url to process start URLs with parse_article.
        This allows single-page sites (like infinite scroll) to extract from the start URL itself.
        """
        logger.info(f"Processing start URL: {response.url}")
        return self.parse_article(response)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Called by Scrapy to create spider instance from crawler."""
        spider = super(DatabaseSpider, cls).from_crawler(crawler, *args, **kwargs)

        # After spider is initialized, check if Cloudflare mode is enabled
        # and update crawler settings directly (this ensures handlers are applied)
        if hasattr(spider, 'custom_settings'):
            cf_enabled = spider.custom_settings.get('CLOUDFLARE_ENABLED', False)
            if cf_enabled:
                logger.info(f"[from_crawler] Applying Cloudflare handlers to crawler settings")
                crawler.settings.set('DOWNLOAD_HANDLERS', {
                    'http': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
                    'https': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
                }, priority='spider')
                logger.info(f"[from_crawler] DOWNLOAD_HANDLERS applied: {crawler.settings.get('DOWNLOAD_HANDLERS')}")

        # Read CLOSESPIDER_ITEMCOUNT from settings for immediate stop logic
        spider._item_limit = crawler.settings.getint('CLOSESPIDER_ITEMCOUNT', 0)
        if spider._item_limit:
            logger.info(f"Item limit set to {spider._item_limit} (will stop immediately when reached)")
        return spider

    async def parse_article(self, response):
        """
        Parse article page.
        """
        # Initialize SmartExtractor with configured strategies
        # Default strategies if not specified or invalid
        default_strategies = ['newspaper', 'trafilatura', 'playwright']
        
        strategies = self.custom_settings.get('EXTRACTOR_ORDER')
        
        # Handle string representation from DB (e.g. "['newspaper', 'trafilatura']")
        if isinstance(strategies, str):
            try:
                import json
                # Replace single quotes with double quotes for JSON compatibility
                strategies = json.loads(strategies.replace("'", '"'))
            except Exception as e:
                logger.warning(f"Failed to parse EXTRACTOR_ORDER string: {strategies}. Error: {e}")
                strategies = None
                
        if not isinstance(strategies, list):
            logger.warning(f"Invalid or missing EXTRACTOR_ORDER, using default: {default_strategies}")
            strategies = default_strategies
            
        logger.info(f"Using strategies: {strategies}")

        # Get custom selectors if provided
        custom_selectors = self.custom_settings.get('CUSTOM_SELECTORS')
        if isinstance(custom_selectors, str):
            try:
                import json
                custom_selectors = json.loads(custom_selectors.replace("'", '"'))
            except Exception as e:
                logger.warning(f"Failed to parse CUSTOM_SELECTORS string: {custom_selectors}. Error: {e}")
                custom_selectors = None

        if custom_selectors:
            logger.info(f"Using custom selectors: {list(custom_selectors.keys())}")

        from core.extractors import SmartExtractor
        extractor = SmartExtractor(strategies=strategies, custom_selectors=custom_selectors)

        # Extract
        logger.info(f"Processing {response.url} (Length: {len(response.text)})")
        title_hint = response.css('title::text').get()
        logger.info(f"Title tag: {title_hint}")

        # Check if HTML should be included in output (for JSONL exports)
        include_html = self.settings.getbool('INCLUDE_HTML_IN_OUTPUT', False)

        # Get Playwright wait configuration from spider settings
        wait_for_selector = self.custom_settings.get('PLAYWRIGHT_WAIT_SELECTOR')
        wait_delay = self.custom_settings.get('PLAYWRIGHT_DELAY', 0)

        # Get infinite scroll configuration from spider settings
        enable_scroll = self.custom_settings.get('INFINITE_SCROLL', False)
        max_scrolls = self.custom_settings.get('MAX_SCROLLS', 5)
        scroll_delay = self.custom_settings.get('SCROLL_DELAY', 1.0)

        # Log wait configuration if present
        if wait_for_selector:
            logger.info(f"Playwright will wait for selector: {wait_for_selector}")
        if wait_delay and float(wait_delay) > 0:
            logger.info(f"Playwright will wait additional {wait_delay} seconds")
        if enable_scroll:
            logger.info(f"Infinite scroll enabled: {max_scrolls} scrolls with {scroll_delay}s delay")

        # Use async extraction with wait configuration
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
            item['spider_name'] = self.spider_name  # Use the actual spider name (e.g. "desmog")
            item['spider_id'] = self.spider_config.id
            item['source'] = 'database_spider'  # Indicate this came from the generic database spider

            yield item

            # Check item limit and stop immediately if reached
            if self._item_limit:
                self._items_scraped += 1
                if self._items_scraped >= self._item_limit:
                    logger.info(f"Reached item limit ({self._item_limit}), stopping spider immediately")
                    raise CloseSpider(f'closespider_itemcount_immediate')
        else:
            logger.warning(f"Failed to extract article from {response.url}")

    def _is_article_page(self, response):
        """Filter out non-article pages"""
        # Content length check
        body_text = ' '.join(response.css('body ::text').getall())
        if len(body_text.strip()) < 500:
            return False

        # Title check
        title = response.css('title::text').get() or ''
        if len(title.strip()) < 10:
            return False

        return True
