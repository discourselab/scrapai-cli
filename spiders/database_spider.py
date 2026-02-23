import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from core.db import get_db
from core.models import Spider, SpiderRule
from .base import BaseDBSpiderMixin
import logging

logger = logging.getLogger(__name__)


class DatabaseSpider(BaseDBSpiderMixin, CrawlSpider):
    name = "database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            spider_name = getattr(self.__class__, "_spider_name", None)
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
        self.start_urls = spider.start_urls

        # Compile rules
        self.rules = []
        db_rules = sorted(spider.rules, key=lambda r: r.priority, reverse=True)

        for r in db_rules:
            le_kwargs = {}
            if r.allow_patterns:
                le_kwargs["allow"] = r.allow_patterns
            if r.deny_patterns:
                le_kwargs["deny"] = r.deny_patterns
            if r.restrict_xpaths:
                le_kwargs["restrict_xpaths"] = r.restrict_xpaths
            if r.restrict_css:
                le_kwargs["restrict_css"] = r.restrict_css

            callback = None
            if r.callback:
                if hasattr(self, r.callback):
                    callback = r.callback
                else:
                    self.logger.warning(
                        f"Callback '{r.callback}' not found on spider, ignoring rule"
                    )
                    continue

            self.rules.append(
                Rule(LinkExtractor(**le_kwargs), callback=callback, follow=r.follow)
            )

        # Load settings and CF handlers via mixin
        self._load_settings_from_db(spider)
        self._setup_cloudflare_handlers()

    def parse_start_url(self, response):
        """Process start URLs with parse_article."""
        logger.info(f"Processing start URL: {response.url}")
        return self.parse_article(response)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(DatabaseSpider, cls).from_crawler(crawler, *args, **kwargs)
        cls._apply_cf_to_crawler(spider, crawler)
        return spider

    async def parse_article(self, response):
        async for item in self._extract_article(
            response, source_label="database_spider"
        ):
            yield item
