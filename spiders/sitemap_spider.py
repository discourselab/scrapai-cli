from scrapy.spiders import SitemapSpider
from scrapy.utils.sitemap import Sitemap
from core.db import get_db
from core.models import Spider
from .base import BaseDBSpiderMixin
from dateutil import parser as dateutil_parser
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import json
import logging
import os
import re
import shutil

logger = logging.getLogger(__name__)

# Media URLs sometimes appear as plain <loc>s (WP image/attachment sitemaps):
# media, not content pages — they must not inflate the audit's coverage
# denominator (docs/requests/19). Mirrors the audit's fetched-path list
# (core/quality/crawl_audit/sitemaps.py); duplicated because this file must
# not import the quality tool.
_MEDIA_EXT = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
    ".ico",
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".wmv",
    ".webm",
    ".mp3",
    ".wav",
    ".ogg",
)


def _is_media_loc(url):
    u = url.lower().split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return u.endswith(_MEDIA_EXT)


# Bodies of rejected sitemaps kept per crawl, so they can never pile up.
REJECTS_MAX_FILES = 20
REJECTS_MAX_BYTES = 256 * 1024


def _has_no_root(body):
    """True when a sitemap body has no root element at all (plain text such
    as "Forbidden"): Scrapy's Sitemap() then raises instead of typing it."""
    try:
        Sitemap(body)
    except Exception:
        return True
    return False


def _scrapy_rejects(body):
    """True when Scrapy's SitemapSpider._parse_sitemap (2.17) ignores a sitemap
    with this body as "Ignoring invalid sitemap": _get_sitemap_body() gave it
    nothing, or the root element is neither <urlset> nor <sitemapindex>. A body
    with no root at all is rejected too (see _parse_sitemap)."""
    if not body:
        return True
    try:
        return Sitemap(body).type not in ("urlset", "sitemapindex")
    except Exception:
        return True


def _reject_file_number(name):
    """The NN of a kept body named NN_<slug>.txt, else 0."""
    m = re.match(r"^(\d+)_", name)
    return int(m.group(1)) if m else 0


def _reject_file_name(n, url):
    tail = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", tail)[:60] or "sitemap"
    return f"{n:02d}_{slug}.txt"


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
        # Audit accounting, counted in sitemap_filter() and dumped by closed()
        # into crawl_stats/: total = UNIQUE page URLs in the sitemap (media
        # locs excluded, deduped across sub-sitemap files — docs/requests/19);
        # eligible = those that pass date/deny filters AND match an allow rule
        # — the coverage denominator, captured at crawl time so nothing
        # re-fetches the sitemap.
        self._sm_total = 0
        self._sm_eligible = 0
        self._sm_seen = set()
        # Sitemaps Scrapy rejected (see _parse_sitemap); their URLs never reach
        # sitemap_filter, so a non-empty list means _sm_total is short.
        self._sm_rejected = []
        self._sm_rejects_dir = None  # set by _open_sitemap_rejects; None = keep none
        self._sm_rejects_index = []
        self._sm_rejects_next = 1  # number of the next kept body file
        self._sm_last_body = None
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
        rules = sorted(spider.rules, key=lambda r: r.priority, reverse=True)

        sitemap_rules = []
        deny_res = []
        for rule in rules:
            callback = rule.callback or "parse_article"
            if rule.allow_patterns:
                for pattern in rule.allow_patterns:
                    sitemap_rules.append((pattern, callback))
            elif not rule.deny_patterns:
                sitemap_rules.append(("/", callback))

            # Scrapy SitemapSpider has no native deny support, so collect deny
            # patterns from every rule (allow+deny or deny-only) and enforce them
            # ourselves in sitemap_filter().
            for pattern in rule.deny_patterns or []:
                try:
                    deny_res.append(re.compile(pattern))
                except re.error as e:
                    logger.warning(f"Skipping invalid deny pattern '{pattern}': {e}")

        self._deny_res = deny_res
        if deny_res:
            logger.info(f"Sitemap deny patterns active: {len(deny_res)}")

        if not sitemap_rules:
            sitemap_rules = [("/", "parse_article")]

        # Compile allow patterns for the eligibility count in sitemap_filter();
        # "/" = match-all.
        self._sm_match_all = any(p == "/" for p, _ in sitemap_rules)
        self._sm_allow_res = []
        for p, _ in sitemap_rules:
            if p == "/":
                continue
            try:
                self._sm_allow_res.append(re.compile(p))
            except re.error:
                pass

        return sitemap_rules

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SitemapDatabaseSpider, cls).from_crawler(
            crawler, *args, **kwargs
        )
        cls._apply_cf_to_crawler(spider, crawler)
        spider._open_sitemap_rejects(crawler)
        return spider

    def _open_sitemap_rejects(self, crawler):
        """Prepare data/<project>/_audit/sitemap_rejects/<spider>/ for this
        crawl's rejected-sitemap bodies. A capped run (--limit) keeps nothing
        and leaves the folder alone. A fresh production crawl starts it empty;
        a resumed leg keeps the earlier legs' files and continues their index,
        so the per-crawl cap spans every leg, and takes the URLs that index
        lists into sitemap_rejected: an earlier leg that died before handing
        its counters on still has its rejections reported. Runs after
        _apply_cf_to_crawler, which sets _resumed.

        The folder is only used (and cleared) when it is a direct child of
        sitemap_rejects/: a spider name such as "" or ".." would otherwise
        point the rmtree at the audit folder itself."""
        self._sm_rejects_dir = None
        self._sm_rejects_index = []
        self._sm_rejects_next = 1
        try:
            if crawler.settings.getint("CLOSESPIDER_ITEMCOUNT"):
                return
            base = self._audit_dir("sitemap_rejects")
            name = str(self.spider_name or "")
            folder = os.path.join(base, name)
            if name in ("", ".", "..") or os.path.dirname(
                os.path.realpath(folder)
            ) != os.path.realpath(base):
                logger.warning(
                    f"Not keeping rejected-sitemap bodies: spider name {name!r} "
                    f"does not give a folder directly under {base}"
                )
                return
            if getattr(self, "_resumed", False):
                try:
                    with open(os.path.join(folder, "index.json")) as fh:
                        index = json.load(fh)
                    if isinstance(index, list):
                        self._sm_rejects_index = index
                except (OSError, ValueError):
                    pass
                for entry in self._sm_rejects_index:
                    url = entry.get("url") if isinstance(entry, dict) else None
                    if url and url not in self._sm_rejected:
                        self._sm_rejected.append(url)
                # Continue after the highest body already kept, so an index
                # that could not be read never leads to overwriting one.
                try:
                    kept = os.listdir(folder)
                except OSError:
                    kept = []
                self._sm_rejects_next = 1 + max(
                    [len(self._sm_rejects_index)]
                    + [_reject_file_number(n) for n in kept]
                )
            else:
                shutil.rmtree(folder, ignore_errors=True)
            self._sm_rejects_dir = folder
        except Exception as e:
            logger.warning(f"Could not prepare the rejected-sitemap folder: {e}")

    def _get_sitemap_body(self, response):
        # Unchanged Scrapy behaviour; the body is only noted for _parse_sitemap.
        body = super()._get_sitemap_body(response)
        self._sm_last_body = body
        return body

    def _parse_sitemap(self, response):
        """Scrapy's own parse, then note a sitemap it rejected.

        Scrapy logs "Ignoring invalid sitemap" and drops every URL in a
        sitemap whose body is not a urlset or sitemapindex (an HTML view of
        the sitemap, a block page served as 200). Nothing counts that, and
        sitemap_filter() never sees those URLs, so sitemap_total undercounts
        silently. The one change to Scrapy's handling: a body with no root
        element at all, on which Scrapy raises, is ignored as a rejection
        instead of surfacing as a spider error. Valid sitemaps yield exactly
        what Scrapy yields, and robots.txt goes through its path untouched."""
        self._sm_last_body = None
        robots = response.url.endswith("/robots.txt")
        try:
            # Materialised here: older Scrapy versions return a generator, and
            # the body is only fetched (and noted) once it is iterated.
            result = list(super()._parse_sitemap(response))
        except Exception:
            # A body with no root element (plain text such as "Forbidden" at
            # a .xml URL) makes Scrapy's Sitemap() raise StopIteration, which
            # surfaced as a spider error. It is dropped either way; treat it
            # as the rejection it is. Anything else is re-raised unchanged.
            body, self._sm_last_body = self._sm_last_body, None
            if robots or not body or not _has_no_root(body):
                raise
            logger.warning(f"Ignoring invalid sitemap: {response} (no root element)")
            self._note_rejected_sitemap(response)
            return ()
        if not robots:
            body, self._sm_last_body = self._sm_last_body, None
            try:
                if _scrapy_rejects(body):
                    self._note_rejected_sitemap(response)
            except Exception as e:
                logger.warning(f"Could not record rejected sitemap: {e}")
        self._sm_last_body = None
        return result

    def _note_rejected_sitemap(self, response):
        size = len(response.body or b"")
        if response.url not in self._sm_rejected:
            self._sm_rejected.append(response.url)
        crawler = getattr(self, "crawler", None)
        if crawler is not None:
            crawler.stats.inc_value("sitemap/rejected")
        logger.warning(
            f"Sitemap rejected: {response.url} (status {response.status}, "
            f"{size} bytes) is not a urlset or sitemapindex, so Scrapy drops "
            "every URL in it and sitemap_total is short"
        )
        self._keep_rejected_body(response, size)

    def _keep_rejected_body(self, response, size):
        """Keep the body for the audit: at most REJECTS_MAX_FILES per crawl,
        each cut at REJECTS_MAX_BYTES, listed in index.json."""
        folder = self._sm_rejects_dir
        if not folder or self._sm_rejects_next > REJECTS_MAX_FILES:
            return
        try:
            os.makedirs(folder, exist_ok=True)
            name = _reject_file_name(self._sm_rejects_next, response.url)
            self._sm_rejects_next += 1
            with open(os.path.join(folder, name), "wb") as fh:
                fh.write((response.body or b"")[:REJECTS_MAX_BYTES])
            ctype = response.headers.get(b"Content-Type") or b""
            self._sm_rejects_index.append(
                {
                    "file": name,
                    "url": response.url,
                    "status": response.status,
                    "bytes": size,
                    "content_type": ctype.decode("latin-1"),
                }
            )
            with open(os.path.join(folder, "index.json"), "w") as fh:
                json.dump(self._sm_rejects_index, fh, indent=2)
        except Exception as e:
            logger.warning(f"Could not keep rejected sitemap body: {e}")

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
        """Filter sitemap entries before requests are built.

        Resolves relative ``<loc>`` values to absolute URLs (a relative loc
        otherwise raises "Missing scheme" downstream and aborts iteration of the
        rest of the sitemap), drops entries matching any deny pattern, and filters
        by lastmod date if SITEMAP_SINCE is set.
        """
        since = self._parse_since_date()
        deny_res = getattr(self, "_deny_res", [])
        base = f"https://{self.allowed_domains[0]}/" if self.allowed_domains else None

        # <sitemapindex> entries are sub-sitemap refs, not content pages — they
        # pass through the filters below but must never be counted as pages.
        is_index = getattr(entries, "type", None) == "sitemapindex"

        total = 0
        rewritten = 0
        filtered = 0
        no_lastmod = 0
        denied = 0
        yielded = 0

        for entry in entries:
            total += 1

            # Decided on the raw loc, before date/deny filtering, so _sm_total
            # reflects the whole sitemap. Media attachment locs are not content
            # pages, and the same loc repeated across sub-sitemap files counts
            # once (docs/requests/19).
            loc0 = entry.get("loc", "")
            new_page = (
                not is_index
                and bool(loc0)
                and not loc0.lower().endswith((".xml", ".xml.gz"))
                and not _is_media_loc(loc0)
                and loc0 not in self._sm_seen
            )
            if new_page:
                self._sm_seen.add(loc0)
                self._sm_total += 1

            # Resolve relative <loc> to absolute before anything downstream reads
            # it. Covers root-relative ("/path") and protocol-relative ("//host").
            loc = entry.get("loc", "")
            if loc and not urlparse(loc).scheme:
                if not base:
                    logger.warning(
                        f"Cannot resolve relative loc '{loc}': no allowed_domains; "
                        "skipping"
                    )
                    continue
                entry["loc"] = urljoin(base, loc)
                rewritten += 1
                logger.info(f"Rewrote relative sitemap loc: {loc} -> {entry['loc']}")

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

            # Enforce deny patterns on the now-absolute loc.
            if deny_res and any(r.search(entry["loc"]) for r in deny_res):
                denied += 1
                continue

            # Survived date + deny filters and matches an allow rule → eligible.
            if new_page and (
                getattr(self, "_sm_match_all", False)
                or any(
                    rx.search(entry["loc"]) for rx in getattr(self, "_sm_allow_res", [])
                )
            ):
                self._sm_eligible += 1

            logger.debug(f"Sitemap entry: {entry['loc']}")
            yielded += 1
            yield entry

        if since or denied or rewritten:
            logger.info(
                f"Sitemap filter: {total} total, {rewritten} relative locs rewritten, "
                f"{filtered} filtered (date), {no_lastmod} without lastmod, "
                f"{denied} denied, {yielded} scheduled"
            )
