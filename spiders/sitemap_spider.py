from scrapy.spiders import SitemapSpider
from core.db import get_db
from core.models import Spider
from .base import BaseDBSpiderMixin
from dateutil import parser as dateutil_parser
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger(__name__)


class SitemapDatabaseSpider(BaseDBSpiderMixin, SitemapSpider):
    """Spider for crawling sites via sitemap.xml files."""

    name = "sitemap_database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            spider_name = getattr(self.__class__, "_spider_name", None)
        if not spider_name:
            raise ValueError("spider_name argument is required")

        self.spider_name = spider_name
        # Override the class-level Scrapy name so DeltaFetch cache, JSONL output
        # paths, and pipeline source attribution use the actual spider name
        # instead of "sitemap_database_spider" being shared by every sitemap crawl.
        self.name = spider_name
        self._items_scraped = 0
        self._item_limit = None
        self._load_config()
        super().__init__(*args, **kwargs)

    def _load_config(self):
        """Load spider configuration from database"""
        with get_db() as db:
            spider = db.query(Spider).filter(Spider.name == self.spider_name).first()

            if not spider:
                raise ValueError(f"Spider '{self.spider_name}' not found in database")
            if not spider.active:
                raise ValueError(f"Spider '{self.spider_name}' is inactive")

            self.spider_config = spider
            self.allowed_domains = spider.allowed_domains
            self.sitemap_urls = spider.start_urls

            logger.info(
                f"Sitemap spider configured with sitemap URLs: {self.sitemap_urls}"
            )

            # Load settings and CF handlers via mixin
            self._load_settings_from_db(spider)
            self._setup_cloudflare_handlers()

            # Load and register callbacks
            callbacks_config = getattr(spider, "callbacks_config", None) or {}
            if callbacks_config:
                logger.info(
                    f"Loading {len(callbacks_config)} callbacks: {list(callbacks_config.keys())}"
                )
                for callback_name, callback_config in callbacks_config.items():
                    callback_method = self._make_callback(
                        callback_name, callback_config
                    )
                    setattr(self, callback_name, callback_method)
                    logger.info(f"Registered callback: {callback_name}")
            else:
                logger.info("No callbacks defined for this spider")

            # Build sitemap_rules from DB rules when callbacks are defined
            self.sitemap_rules = self._build_sitemap_rules(spider)
            logger.info(f"Sitemap rules: {self.sitemap_rules}")

    def _build_sitemap_rules(self, spider):
        """Build sitemap_rules from DB rules when callbacks are defined.

        Each DB rule with allow_patterns and a callback becomes a sitemap rule.
        Falls back to [("/", "parse_article")] if no callback rules exist.
        """
        from core.models import SpiderRule

        with get_db() as db:
            rules = (
                db.query(SpiderRule)
                .filter(SpiderRule.spider_id == spider.id)
                .order_by(SpiderRule.priority.desc())
                .all()
            )

            sitemap_rules = []
            for rule in rules:
                callback = rule.callback or "parse_article"
                if rule.allow_patterns:
                    for pattern in rule.allow_patterns:
                        sitemap_rules.append((pattern, callback))
                elif rule.deny_patterns:
                    # Deny-only rules: match everything except denied patterns
                    # Scrapy SitemapSpider doesn't support deny, so we use a
                    # catch-all that the callback handles
                    continue
                else:
                    # No allow/deny patterns — catch-all rule
                    sitemap_rules.append(("/", callback))

        if not sitemap_rules:
            # No rules with callbacks — default to parse_article for all URLs
            sitemap_rules = [("/", "parse_article")]

        return sitemap_rules

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SitemapDatabaseSpider, cls).from_crawler(
            crawler, *args, **kwargs
        )
        cls._apply_cf_to_crawler(spider, crawler)
        return spider

    async def parse_article(self, response):
        async for item in self._extract_article(
            response, source_label="sitemap_spider"
        ):
            yield item

    def _parse_since_date(self):
        """Parse SITEMAP_SINCE setting into a datetime.

        Supports:
        - Relative: "2y" (2 years ago), "6m" (6 months ago), "30d" (30 days ago)
        - Absolute: "2024-01-01", "2024-06-15T00:00:00"
        """
        since_str = self.custom_settings.get("SITEMAP_SINCE")
        if not since_str:
            return None

        since_str = str(since_str).strip().lower()

        # Try relative format: "2y", "6m", "30d"
        match = re.match(r"^(\d+)([ymd])$", since_str)
        if match:
            amount, unit = int(match.group(1)), match.group(2)
            now = datetime.now()
            if unit == "y":
                return now.replace(year=now.year - amount)
            elif unit == "m":
                month = now.month - amount
                year = now.year
                while month <= 0:
                    month += 12
                    year -= 1
                return now.replace(year=year, month=month)
            elif unit == "d":
                return now - timedelta(days=amount)

        # Try absolute date
        try:
            parsed = dateutil_parser.parse(since_str)
            if parsed.tzinfo:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except (ValueError, TypeError) as e:
            logger.warning(f"Cannot parse SITEMAP_SINCE '{since_str}': {e}")
            return None

    def sitemap_filter(self, entries):
        """Filter sitemap entries by lastmod date if SITEMAP_SINCE is set."""
        since = self._parse_since_date()

        total = 0
        filtered = 0
        no_lastmod = 0

        for entry in entries:
            total += 1
            if since and entry.get("lastmod"):
                try:
                    entry_date = dateutil_parser.parse(entry["lastmod"])
                    if entry_date.tzinfo:
                        entry_date = entry_date.replace(tzinfo=None)
                    if entry_date < since:
                        filtered += 1
                        continue
                except (ValueError, TypeError):
                    pass  # Can't parse date, include the entry
            elif since and not entry.get("lastmod"):
                no_lastmod += 1

            logger.debug(f"Sitemap entry: {entry['loc']}")
            yield entry

        if since:
            logger.info(
                f"Sitemap filter: {total} total, {filtered} filtered (before {since.date()}), "
                f"{no_lastmod} without lastmod, {total - filtered} scheduled"
            )
