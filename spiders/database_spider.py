import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from core.db import get_db
from core.models import Spider, SpiderRule
import logging
import json

logger = logging.getLogger(__name__)

class DatabaseSpider(CrawlSpider):
    name = "database_spider"
    
    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            raise ValueError("spider_name argument is required")
            
        self.spider_name = spider_name
        self._load_config()
        super().__init__(*args, **kwargs)
        
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
        
        from core.extractors import SmartExtractor
        extractor = SmartExtractor(strategies=strategies)
        
        # Extract
        logger.info(f"Processing {response.url} (Length: {len(response.text)})")
        title_hint = response.css('title::text').get()
        logger.info(f"Title tag: {title_hint}")
        
        # Use async extraction
        article = await extractor.extract_async(response.url, response.text, title_hint=title_hint)

        if article:
            # Convert Pydantic model to dict
            item = article.dict()
            
            # Add spider metadata
            item['spider_name'] = self.spider_name  # Use the actual spider name (e.g. "desmog")
            item['spider_id'] = self.spider_config.id
            item['source'] = 'database_spider'  # Indicate this came from the generic database spider
            
            yield item
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
