import scrapy
from scrapy.spiders import SitemapSpider
from core.db import get_db
from core.models import Spider
from .base import BaseDBSpiderMixin
import logging

logger = logging.getLogger(__name__)

class SitemapDatabaseSpider(BaseDBSpiderMixin, SitemapSpider):
    """Spider for crawling sites via sitemap.xml files."""
    name = "sitemap_database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            spider_name = getattr(self.__class__, '_spider_name', None)
        if not spider_name:
            raise ValueError("spider_name argument is required")

        self.spider_name = spider_name
        self._items_scraped = 0
        self._item_limit = None
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
        self.sitemap_urls = spider.start_urls

        logger.info(f"Sitemap spider configured with sitemap URLs: {self.sitemap_urls}")

        self.sitemap_rules = [
            ('/', 'parse_article'),
        ]

        # Load settings and CF handlers via mixin
        self._load_settings_from_db(spider)
        self._setup_cloudflare_handlers()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SitemapDatabaseSpider, cls).from_crawler(crawler, *args, **kwargs)
        cls._apply_cf_to_crawler(spider, crawler)
        return spider

    async def parse_article(self, response):
        async for item in self._extract_article(response, source_label='sitemap_spider'):
            yield item

    def sitemap_filter(self, entries):
        """Filter sitemap entries before processing."""
        for entry in entries:
            logger.debug(f"Sitemap entry: {entry['loc']}")
            yield entry
