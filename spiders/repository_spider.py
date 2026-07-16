"""Repository-harvest spider (JSON:API / paginated-JSON) — added by Ranu.

Requested in docs/requests/21-jsonapi-repository-harvest.md. Digital repositories
(Islandora / DSpace / Fedora / Samvera) put their HTML pages behind Cloudflare
but expose an open, CF-free machine API (Drupal JSON:API, OAI-PMH). Their sitemap
is homepage-only and OAI is frequently broken/partial, so the JSON API is the only
complete, reachable index. This spider treats a paginated JSON collection endpoint
as the record inventory: it walks `links.next`, maps each record's fields to item
fields (dot-paths + `||` fallbacks + `include` relationship resolution + `template`
+ the standard processors), and yields normal pipeline items — no browser, no proxy,
no CF solving. Config lives entirely in `final_spider.json` under the
`REPOSITORY_SOURCE` setting; existing HTML/sitemap spiders are untouched.
"""

import json
import logging

import scrapy
from scrapy import Request

from core.db import get_db
from core.models import Spider
from .base import BaseDBSpiderMixin

logger = logging.getLogger(__name__)


class RepositoryDatabaseSpider(BaseDBSpiderMixin, scrapy.Spider):
    """Harvest a repository via its paginated JSON API (e.g. Drupal JSON:API).

    Driven by the `REPOSITORY_SOURCE` setting:
        {
          "records": "data",              # dot-path to the record list
          "next": "links.next.href",      # dot-path to the next-page URL (stop when absent)
          "included_key": "included",     # where JSON:API related resources live
          "require": "url",               # skip a record if this mapped field is empty
          "map": { <item-field>: <spec>, ... }
        }
    A map <spec> is either a dot-path string (with ` || ` fallbacks resolved
    left-to-right, first non-empty wins), or an object:
        {"path"/"paths", "include", "template", "list", "processors"}
      - path/paths : dot-path(s) into the record (or into the included resource
                     when `include` is set). Supports `.` keys and numeric indices.
      - include    : a relationship name on the record; its data (obj or first of a
                     list) is looked up in `included[]` by (type,id) and `path` is
                     read from THAT resource. Empty when the related resource was
                     omitted (e.g. unpublished) -> field is null.
      - template   : "https://host/node/{}" — {} is replaced by the scalar value.
      - list       : true -> wrap a scalar result in a single-element list.
      - processors : the standard core.processors chain (strip/regex/parse_datetime/...).
    start_urls are the JSON collection endpoint(s).
    """

    name = "repository_database_spider"

    def __init__(self, spider_name=None, *args, **kwargs):
        if not spider_name:
            spider_name = getattr(self.__class__, "_spider_name", None)
        if not spider_name:
            raise ValueError("spider_name argument is required")

        self.spider_name = spider_name
        self.name = spider_name  # per-spider DeltaFetch DB / output / attribution
        self._items_scraped = 0
        self._item_limit = None
        self._sm_total = 0  # keeps the mixin's closed()/audit stats happy
        self._load_config()
        super().__init__(*args, **kwargs)

    def _load_config(self):
        with get_db() as db:
            spider = db.query(Spider).filter(Spider.name == self.spider_name).first()
            if not spider:
                raise ValueError(f"Spider '{self.spider_name}' not found in database")
            if not spider.active:
                raise ValueError(f"Spider '{self.spider_name}' is inactive")

            self.spider_config = spider
            self.allowed_domains = spider.allowed_domains
            self.start_urls = spider.start_urls

            self._load_settings_from_db(spider)
            self._setup_cloudflare_handlers()

            source = self.custom_settings.get("REPOSITORY_SOURCE")
            if isinstance(source, str):
                try:
                    source = json.loads(source)
                except Exception:
                    source = None
            if not isinstance(source, dict):
                raise ValueError(
                    f"Spider '{self.spider_name}' has no valid REPOSITORY_SOURCE setting"
                )
            self._repo = source
            self._records_path = source.get("records", "data")
            self._next_path = source.get("next", "links.next.href")
            self._included_key = source.get("included_key", "included")
            self._require_field = source.get("require", "url")
            self._map = source.get("map") or {}
            if not self._map:
                raise ValueError(
                    f"REPOSITORY_SOURCE for '{self.spider_name}' has an empty 'map'"
                )
            logger.info(
                f"Repository spider configured: {len(self._map)} mapped fields, "
                f"records='{self._records_path}', next='{self._next_path}'"
            )

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(RepositoryDatabaseSpider, cls).from_crawler(
            crawler, *args, **kwargs
        )
        cls._apply_cf_to_crawler(spider, crawler)
        return spider

    async def start(self):
        for url in self.start_urls:
            yield Request(url, callback=self.parse, dont_filter=True)

    async def parse(self, response):
        try:
            doc = json.loads(response.text)
        except Exception as e:
            logger.error(f"Repository page not JSON ({e}): {response.url}")
            return

        included = self._index_included(doc.get(self._included_key))
        records = self._dig(doc, self._records_path)
        if not isinstance(records, list):
            logger.warning(
                f"records path '{self._records_path}' did not yield a list at "
                f"{response.url}"
            )
            records = []

        emitted = 0
        for record in records:
            try:
                item = self._build_item(record, included)
            except Exception as e:
                logger.warning(f"Skipping record ({e}) at {response.url}")
                continue
            if item is None:
                continue
            yield item
            self._items_scraped += 1
            emitted += 1

        logger.info(
            f"Repository page {response.url}: {len(records)} records, {emitted} emitted"
        )

        # Stop paging once the item limit is reached (Scrapy's CloseSpider also
        # enforces it, but not requesting the next page avoids over-fetching).
        if self._item_limit and self._items_scraped >= self._item_limit:
            return

        next_url = self._dig(doc, self._next_path)
        if isinstance(next_url, str) and next_url:
            yield Request(next_url, callback=self.parse)

    # ---- mapping helpers -------------------------------------------------

    def _build_item(self, record, included):
        """Map one JSON record to a pipeline item, or None to skip it."""
        from core.processors import apply_processors

        item = {
            "spider_name": self.spider_name,
            "spider_id": self.spider_config.id,
            "source": "repository_spider",
        }
        for field_name, spec in self._map.items():
            if isinstance(spec, str):
                spec = {"path": spec}
            elif not isinstance(spec, dict):
                continue

            base = record
            include_rel = spec.get("include")
            if include_rel:
                base = self._resolve_include(record, include_rel, included)
                if base is None:
                    item[field_name] = None
                    continue

            value = self._first_path(base, spec.get("paths") or spec.get("path"))

            template = spec.get("template")
            if template and value not in (None, "", []):
                value = template.replace("{}", str(value))

            if spec.get("list") and value not in (None, "", []):
                value = value if isinstance(value, list) else [value]

            processors = spec.get("processors") or []
            if processors:
                try:
                    value = apply_processors(value, processors)
                except Exception as e:
                    logger.warning(
                        f"REPOSITORY_SOURCE processor failed for '{field_name}': {e}"
                    )
            item[field_name] = value

        require = self._require_field
        if require and not item.get(require):
            return None
        return item

    def _resolve_include(self, record, relationship, included):
        """Follow a JSON:API relationship to its resource in `included`."""
        rel = self._dig(record, f"relationships.{relationship}.data")
        if isinstance(rel, list):
            rel = rel[0] if rel else None
        if not isinstance(rel, dict):
            return None
        key = (rel.get("type"), rel.get("id"))
        return included.get(key)

    @staticmethod
    def _index_included(included):
        """Index JSON:API `included[]` by (type, id) for O(1) relationship lookup."""
        index = {}
        if isinstance(included, list):
            for res in included:
                if isinstance(res, dict):
                    index[(res.get("type"), res.get("id"))] = res
        return index

    def _first_path(self, obj, paths):
        """Resolve the first non-empty dot-path. `paths` may be a string
        (optionally with ` || ` alternatives) or a list of strings."""
        if paths is None:
            return None
        if isinstance(paths, str):
            candidates = [p.strip() for p in paths.split("||")]
        else:
            candidates = list(paths)
        for path in candidates:
            value = self._dig(obj, path)
            if value not in (None, "", []):
                return value
        return None

    @staticmethod
    def _dig(obj, path):
        """Walk a dot-path (dict keys + numeric list indices) into `obj`."""
        if not path:
            return obj
        cur = obj
        for key in str(path).split("."):
            if isinstance(cur, dict):
                cur = cur.get(key)
            elif isinstance(cur, list):
                if key.lstrip("-").isdigit() and -len(cur) <= int(key) < len(cur):
                    cur = cur[int(key)]
                else:
                    return None
            else:
                return None
            if cur is None:
                return None
        return cur
