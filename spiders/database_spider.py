from scrapy import Request
from scrapy.linkextractors import LinkExtractor, IGNORED_EXTENSIONS
from scrapy.spiders import CrawlSpider, Rule
from core.db import get_db
from core.models import Spider
from .base import BaseDBSpiderMixin, _pdf_links
import datetime as _dt
import itertools as _it
import logging
import re

logger = logging.getLogger(__name__)


def _expand_var(v):
    """One GENERATED_URLS variable -> a list of string values.

    `from` is a Python keyword, so the schema stores it under the field name
    `from_` after model_dump; accept either (as-authored "from" or stored
    "from_"), mirroring how FieldExtractDirective is read in base.py.
    """
    frm = v["from"] if "from" in v else v.get("from_")
    if v["type"] == "range":
        step = v.get("step", 1)
        return [str(i) for i in range(frm, v["to"] + 1, step)]
    if v["type"] == "list":
        return [str(x) for x in v["values"]]
    if v["type"] == "date":
        fmt = v.get("format", "%Y-%m-%d")
        step = _dt.timedelta(days=v.get("step_days", 1))
        d = _dt.datetime.strptime(frm, fmt).date()
        end = _dt.datetime.strptime(v["to"], fmt).date()
        out = []
        while d <= end:
            out.append(d.strftime(fmt))
            d += step
        return out
    raise ValueError(f"unknown GENERATED_URLS var type {v.get('type')!r}")


def _generated_urls(cfg):
    """Yield every URL from a GENERATED_URLS entry (cartesian product of vars).

    The product streams lazily; each var's value pool is materialized by
    `_expand_var` (fine at archive scale; chunk a single 10M+ var across runs).
    """
    names = list(cfg["vars"].keys())
    seqs = [_expand_var(cfg["vars"][n]) for n in names]
    template = cfg["template"]
    for combo in _it.product(*seqs):
        url = template
        for n, val in zip(names, combo):
            url = url.replace("{" + n + "}", val)
        yield url


def _generated_requests(spider, cfg):
    """Yield a Request for each generated URL, routed to an EXPLICIT callback.

    A missing/misspelled callback RAISES: a Request(callback=None) on a
    CrawlSpider hits CrawlSpider.parse, which runs the rule engine and FOLLOWS
    links — the opposite of "generate, don't follow", and it fails silently.
    No dont_filter: generated URLs are unique, so the dupefilter dedups within a
    run and (persisted in the checkpoint) lets a resume skip completed URLs.
    """
    cb_name = cfg.get("callback", "parse_article")
    cb = getattr(spider, cb_name, None)
    if cb is None:
        raise ValueError(
            f"GENERATED_URLS callback {cb_name!r} not found on spider "
            "(callback=None would fall back to CrawlSpider.parse and FOLLOW links)"
        )
    for url in _generated_urls(cfg):
        yield Request(url, callback=cb)


class DatabaseSpider(BaseDBSpiderMixin, CrawlSpider):
    name = "database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            spider_name = getattr(self.__class__, "_spider_name", None)
        if not spider_name:
            raise ValueError("spider_name argument is required")

        self.spider_name = spider_name
        self.name = spider_name  # Set Scrapy's spider.name for DeltaFetch per-spider DB
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
            self.start_urls = spider.start_urls

            # Load and register callbacks FIRST (before compiling rules)
            callbacks_config = getattr(spider, "callbacks_config", None) or {}
            if callbacks_config:
                logger.info(
                    f"Loading {len(callbacks_config)} callbacks: {list(callbacks_config.keys())}"
                )
                for callback_name, callback_config in callbacks_config.items():
                    # Create dynamic method and register it on the spider instance
                    callback_method = self._make_callback(
                        callback_name, callback_config
                    )
                    setattr(self, callback_name, callback_method)
                    logger.info(f"Registered callback: {callback_name}")
            else:
                logger.info("No callbacks defined for this spider")

            # Compile rules AFTER callbacks are registered
            self.rules = []
            # (allow_patterns, callback) for each content rule (priority order),
            # used to decide whether a start URL is itself content. Captured here,
            # inside the DB session, to avoid touching detached ORM objects later.
            self._start_match_rules = []
            db_rules = sorted(spider.rules, key=lambda r: r.priority, reverse=True)

            # PDF_MODE governs whether .pdf links are followed. "extract" follows
            # and downloads them; "links_only" (default) leaves them to be
            # recorded as URL-only items without a download.
            pdf_mode = "links_only"
            for s in spider.settings or []:
                if getattr(s, "key", None) == "PDF_MODE":
                    pdf_mode = str(s.value or "links_only").strip().strip('"').lower()

            for r in db_rules:
                le_kwargs = {}
                # Scrapy's LinkExtractor denies .pdf by default (pdf in
                # IGNORED_EXTENSIONS). In extract mode, allow it through (keep
                # every other default exclusion) so PDF links are followed.
                if pdf_mode == "extract":
                    le_kwargs["deny_extensions"] = [
                        e for e in IGNORED_EXTENSIONS if e != "pdf"
                    ]
                if r.allow_patterns:
                    le_kwargs["allow"] = r.allow_patterns
                if r.deny_patterns:
                    le_kwargs["deny"] = r.deny_patterns
                if r.restrict_xpaths:
                    le_kwargs["restrict_xpaths"] = r.restrict_xpaths
                if r.restrict_css:
                    le_kwargs["restrict_css"] = r.restrict_css
                if r.tags:
                    le_kwargs["tags"] = r.tags

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
                # Only rules with a real callback parse content; follow-only
                # rules (callback=None) just extract links and never apply here.
                if callback:
                    self._start_match_rules.append((r.allow_patterns or [], callback))

            # Load settings and CF handlers via mixin
            self._load_settings_from_db(spider)
            self._setup_cloudflare_handlers()

    async def start(self):
        """Yield start requests, expanding PAGINATED_LISTINGS via browser.

        Original start_urls are yielded first (default CrawlSpider behaviour).
        Then, for each entry in the PAGINATED_LISTINGS setting, a browser
        paginator walks the listing's Next button and yields a Request for
        each discovered article URL routed directly to parse_article.
        """
        for url in self.start_urls:
            yield Request(url, dont_filter=True)

        # Generated start URLs from enumerable vars (date/page/id ranges).
        for cfg in self.custom_settings.get("GENERATED_URLS") or []:
            for req in _generated_requests(self, cfg):
                yield req

        listings = self.custom_settings.get("PAGINATED_LISTINGS") or []
        if not listings:
            return

        from utils.browser_paginator import BrowserPaginator

        for cfg in listings:
            logger.info(f"[paginator] Expanding listing: {cfg.get('url')}")
            paginator = BrowserPaginator(
                url=cfg["url"],
                link_selector=cfg["link_selector"],
                next_selector=cfg["next_selector"],
                wait_selector=cfg.get("wait_selector"),
                max_pages=cfg.get("max_pages", 100),
                click_delay=cfg.get("click_delay", 1.5),
            )
            try:
                async for url in paginator.stream():
                    yield Request(url, callback=self.parse_article)
            except Exception as e:
                logger.error(f"[paginator] Failed to paginate {cfg.get('url')}: {e}")
                continue

    async def parse_start_url(self, response):
        """Parse a start URL only when it is itself content.

        Start URLs are crawl entry points; their links are followed by the
        rules regardless. We parse the start URL as content only when it matches
        a content rule (it's both an entry point and a content page), or when the
        spider has no rules at all (a single-page spider whose start URL *is* the
        content). A listing/section start URL that matches no content rule is NOT
        parsed - that previously produced junk rows.
        """
        url = response.url

        # Parse with the first content rule whose pattern the start URL matches.
        # A content rule with no allow patterns is a deliberate match-all.
        for allow_patterns, callback in self._start_match_rules:
            if not allow_patterns or any(re.search(p, url) for p in allow_patterns):
                logger.info(f"Start URL is content, using callback: {callback}")
                callback_method = getattr(self, callback, None)
                if callback_method:
                    async for item in callback_method(response):
                        yield item
                return

        # No content rule matched. If the spider has crawl rules, this start URL
        # is a listing/entry point - don't parse it (links are still followed).
        if self.rules:
            logger.info(f"Start URL {url} is a listing entry point, not parsed")
            return

        # No rules at all: single-page spider, the start URL is the content.
        logger.info("Single-page spider, parsing start URL as article")
        async for item in self.parse_article(response):
            yield item

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
        # links_only: record PDF links found on this page as URL-only items
        # (no download). In extract mode, PDFs are followed via the rules instead.
        if self._pdf_mode() == "links_only":
            for purl in _pdf_links(response):
                yield self._url_only_pdf_item(purl, response, "database_spider")
