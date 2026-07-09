"""Shared mixin for database-driven spiders."""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


def _apply_meta_fallback(item, html):
    """Fill published_date/author from structured metadata (extruct) when the
    config's selectors didn't source them. The generic ('auto') path already
    runs extruct via SmartExtractor; this covers the pure-CSS path, which skips
    the generic extractor — so structured date/author works in both. Explicit
    selector values are never overridden.
    """
    from core.extractors import extract_meta_date, extract_meta_author

    if not item.get("published_date"):
        item["published_date"] = extract_meta_date(html)
    if not item.get("author"):
        item["author"] = extract_meta_author(html)


def with_scroll_fallback(strategies, custom_settings):
    """Ensure the playwright strategy is present when INFINITE_SCROLL is set.

    The legacy ``playwright`` extractor strategy was removed from the default
    order (it re-fetched each page in a cold browser — wasteful at scale; use
    BROWSER_ENABLED instead). Infinite-scroll still rides on it, so re-add it
    only when the spider explicitly asks for scrolling.
    """
    if custom_settings.get("INFINITE_SCROLL") and "playwright" not in strategies:
        return strategies + ["playwright"]
    return strategies


def _clean_pdf_text(text):
    """Tidy raw PDF text: de-hyphenate and join mid-sentence line wraps.

    PDF text comes line-wrapped at the page's column width, often with
    hyphenated words split across lines. We join those so the stored text reads
    as paragraphs, while preserving sentence/heading breaks. Conservative on
    purpose — aggressive reflow is left to post-processing.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # pypdfium2 emits \r / \r\n
    text = re.sub(
        r"\xad[ \t]*\n?[ \t]*", "", text
    )  # soft-hyphen (U+00AD) de-hyphenation
    text = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", text)  # ascii hyphen at line end
    # join a wrapped line into the next when it's a mid-sentence continuation
    # (line doesn't end in sentence punctuation; next line starts lowercase)
    text = re.sub(r"([^\n.!?:;])[ \t]*\n[ \t]*([a-z])", r"\1 \2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(pdf_bytes):
    """Full text from PDF bytes via pypdfium2, cleaned.

    Graceful: returns "" (so the caller keeps the URL-only item) when pypdfium2
    isn't installed, the bytes aren't a parseable PDF, or the PDF has no text
    layer (e.g. a scanned/image-only PDF — we don't OCR).
    """
    if not pdf_bytes:
        return ""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return ""
    pdf = None
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        parts = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            parts.append(tp.get_text_range())
            tp.close()
            page.close()
        return _clean_pdf_text("\n".join(parts))
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def _pdf_links(response):
    """Absolute PDF URLs linked on an HTML page. [] for non-HTML responses."""
    try:
        hrefs = response.css("a::attr(href)").getall()
    except Exception:
        return []  # non-HTML response (a PDF, etc.) has no .css
    out, seen = [], set()
    for h in hrefs:
        if h and h.lower().split("?")[0].split("#")[0].endswith(".pdf"):
            u = response.urljoin(h)
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


class BaseDBSpiderMixin:
    """Mixin providing shared logic for DatabaseSpider and SitemapDatabaseSpider."""

    def _load_settings_from_db(self, spider_record):
        """Deserialize settings from DB spider record into custom_settings."""
        from core.models import deserialize_spider_settings

        if not getattr(self, "custom_settings", None):
            self.custom_settings = {}

        if not spider_record.settings:
            return

        self.custom_settings.update(deserialize_spider_settings(spider_record.settings))

    def _setup_cloudflare_handlers(self):
        """Configure Cloudflare or curl_cffi download handlers if enabled."""
        cf_enabled = self.custom_settings.get(
            "CLOUDFLARE_ENABLED", False
        ) or self.custom_settings.get("BROWSER_ENABLED", False)
        curl_cffi_enabled = self.custom_settings.get("CURL_CFFI_ENABLED", False)

        if curl_cffi_enabled:
            logger.info(f"curl_cffi TLS impersonation enabled for {self.spider_name}")
            self.custom_settings["DOWNLOAD_HANDLERS"] = {
                "http": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                "https": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
            }
        elif cf_enabled:
            logger.info(f"Cloudflare bypass mode enabled for {self.spider_name}")
            self.custom_settings["DOWNLOAD_HANDLERS"] = {
                "http": "handlers.cloudflare_handler.CloudflareDownloadHandler",
                "https": "handlers.cloudflare_handler.CloudflareDownloadHandler",
            }

    def closed(self, reason):
        """Persist each completed crawl's own stats so the audit can read EXACT
        page liveness for free, instead of the slow sampled --check-liveness
        pass (which fetches ~1000 URLs and took forever). Scrapy already counts
        every response status; we just write them out. Only full production
        crawls write: an item-capped run (--limit / health) is skipped by
        SETTING, not close reason — a test crawl that runs out of items UNDER
        its limit still ends "finished" and must not overwrite a real crawl's
        numbers."""
        if reason != "finished":
            return
        try:
            if self.crawler.settings.getint("CLOSESPIDER_ITEMCOUNT"):
                return
            from core.config import DATA_DIR

            stats = self.crawler.stats.get_stats()
            project = (
                getattr(getattr(self, "spider_config", None), "project", None)
                or "default"
            )
            status = {
                k.rsplit("/", 1)[-1]: v
                for k, v in stats.items()
                if "downloader/response_status_count/" in k
            }
            data = {
                "spider": self.spider_name,
                "reason": reason,
                "items": stats.get("item_scraped_count", 0),
                "requests": stats.get("downloader/request_count", 0),
                "status": status,  # {"200": 4890, "404": 210, ...}
            }
            # A resumed crawl (checkpoint) restores its request queue from disk
            # but every in-memory counter restarts at zero, so this leg's
            # numbers aren't the whole crawl's. Record the fact and withhold
            # the sitemap denominator below — wrong-but-plausible coverage is
            # worse than absent (the audit falls back to fetching the sitemap).
            resumed = getattr(self, "_resumed", False)
            if resumed:
                data["resumed"] = True
            # For the audit: sitemap spiders count their own sitemap size +
            # rule-eligible URLs while parsing (sitemap_spider.py); record them
            # so the audit reads the coverage denominator from the crawl instead
            # of re-fetching the sitemap. Absent on rule-based spiders -> the
            # audit falls back to fetching the sitemap for those.
            sm_total = getattr(self, "_sm_total", 0)
            if sm_total and not resumed:
                data["sitemap_total"] = sm_total
                data["eligible"] = getattr(self, "_sm_eligible", 0)
            out_dir = os.path.join(DATA_DIR, project, "_audit", "crawl_stats")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"{self.spider_name}.json"), "w") as fh:
                json.dump(data, fh, indent=2)
            logger.info(f"Wrote crawl stats → {out_dir}/{self.spider_name}.json")
        except Exception as e:
            logger.warning(f"Could not write crawl stats: {e}")

    @staticmethod
    def _resumed_from_checkpoint(crawler):
        """True when this run continues an interrupted crawl. Scrapy's scheduler
        persists its pending-queue state to JOBDIR/requests.queue/active.json on
        close: a cleanly finished crawl leaves an empty list, an interrupted one
        the non-empty priority state it will resume from — the same file Scrapy
        itself reads to resume. Must be checked BEFORE the scheduler opens (the
        queue is consumed during the run); callers do this from from_crawler."""
        jobdir = crawler.settings.get("JOBDIR")
        if not jobdir:
            return False
        try:
            with open(os.path.join(jobdir, "requests.queue", "active.json")) as fh:
                return bool(json.load(fh))
        except (OSError, ValueError):
            return False

    @classmethod
    def _apply_cf_to_crawler(cls, spider, crawler):
        """Apply spider settings + Cloudflare/curl_cffi handlers to crawler after init.

        Spider `custom_settings` is populated from the DB in __init__, *after*
        Scrapy has already frozen `crawler.settings` via `Spider.update_settings`
        (which reads the class attribute, not the instance one). Without this
        propagation step, JSON-declared settings like CONCURRENT_REQUESTS,
        DOWNLOAD_DELAY, and AUTOTHROTTLE_ENABLED are silently ignored.
        """
        # Runs from from_crawler, before the scheduler opens — the last moment
        # the persisted queue state is still readable (see the helper).
        spider._resumed = cls._resumed_from_checkpoint(crawler)
        if hasattr(spider, "custom_settings"):
            for key, value in spider.custom_settings.items():
                crawler.settings.set(key, value, priority="spider")

            cf_enabled = spider.custom_settings.get(
                "CLOUDFLARE_ENABLED", False
            ) or spider.custom_settings.get("BROWSER_ENABLED", False)
            curl_cffi_enabled = spider.custom_settings.get("CURL_CFFI_ENABLED", False)

            if curl_cffi_enabled:
                logger.info(
                    "[from_crawler] Applying curl_cffi handlers to crawler settings"
                )
                crawler.settings.set(
                    "DOWNLOAD_HANDLERS",
                    {
                        "http": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                        "https": "handlers.curl_cffi_handler.CurlCffiDownloadHandler",
                    },
                    priority="spider",
                )
            elif cf_enabled:
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

    @staticmethod
    def _is_pdf_response(response):
        """A PDF by URL suffix or Content-Type. PDFs aren't HTML."""
        path = response.url.lower().split("?")[0].split("#")[0]
        if path.endswith(".pdf"):
            return True
        ctype = response.headers.get("Content-Type", b"")
        if isinstance(ctype, (bytes, bytearray)):
            ctype = ctype.decode("latin-1", "ignore")
        return "application/pdf" in ctype.lower()

    def _pdf_mode(self):
        """'extract' (follow + extract text) or 'links_only' (default)."""
        mode = self.custom_settings.get("PDF_MODE") or "links_only"
        return str(mode).strip().strip('"').lower()

    def _build_pdf_item(self, response, source_label):
        """Item for a PDF response. Text extracted only in PDF_MODE=extract."""
        import os
        from datetime import datetime, timezone
        from urllib.parse import urlparse, unquote

        name = unquote(os.path.basename(urlparse(response.url).path)) or response.url
        content = (
            _extract_pdf_text(response.body) if self._pdf_mode() == "extract" else ""
        )
        return {
            "url": response.url,
            "title": name,
            "content": content,
            "spider_name": self.spider_name,
            "spider_id": self.spider_config.id,
            "source": source_label,
            "extracted_at": datetime.now(timezone.utc),
            "metadata_json": {"content_type": "pdf"},
        }

    def _url_only_pdf_item(self, url, found_on, source_label):
        """Lightweight item recording a discovered PDF link (links_only mode)."""
        import os
        from datetime import datetime, timezone
        from urllib.parse import urlparse, unquote

        name = unquote(os.path.basename(urlparse(url).path)) or url
        return {
            "url": url,
            "title": name,
            "content": "",
            "spider_name": self.spider_name,
            "spider_id": self.spider_config.id,
            "source": source_label,
            "extracted_at": datetime.now(timezone.utc),
            "metadata_json": {"content_type": "pdf", "found_on": found_on.url},
        }

    async def _extract_article(self, response, source_label="database_spider"):
        """Shared article extraction logic."""
        # PDFs (and similar binaries) aren't HTML: the extractors can't read them
        # and response.text/.css would raise. We follow .pdf links on purpose
        # (see database_spider), so collect the URL as a minimal item here.
        if self._is_pdf_response(response):
            yield self._build_pdf_item(response, source_label)
            self._items_scraped += 1
            return

        default_strategies = ["trafilatura", "newspaper"]

        strategies = self.custom_settings.get("EXTRACTOR_ORDER")
        if isinstance(strategies, str):
            try:
                strategies = json.loads(strategies.replace("'", '"'))
            except Exception:
                strategies = None
        if not isinstance(strategies, list):
            strategies = default_strategies

        strategies = with_scroll_fallback(strategies, self.custom_settings)

        # Pure-CSS mode: skip the generic extractor entirely when the spider
        # signals "custom-only" (EXTRACTOR_ORDER == ["custom"]) and provides
        # FIELDS (or legacy FIELD_EXTRACT / CUSTOM_SELECTORS). The schema's FIELDS
        # directives are the sole source of truth.
        field_extract_set = (
            bool(self.custom_settings.get("FIELDS"))
            or bool(self.custom_settings.get("FIELD_EXTRACT"))
            or bool(self.custom_settings.get("CUSTOM_SELECTORS"))
        )
        if strategies == ["custom"] and field_extract_set:
            item = self._build_item_pure_css(response, source_label)
            if item:
                yield item
                self._items_scraped += 1
            else:
                logger.warning(f"Pure-CSS extraction failed for {response.url}")
            return

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

            self._apply_field_extract(item, response)

            # Yield item first, let Scrapy's CLOSESPIDER_ITEMCOUNT handle the limit
            yield item

            # Increment counter after yielding (so item can be processed)
            self._items_scraped += 1
        else:
            logger.warning(f"Failed to extract article from {response.url}")

    _CORE_SCHEMA_FIELDS = {
        "url",
        "title",
        "content",
        "author",
        "published_date",
    }

    def _build_item_pure_css(self, response, source_label):
        """Build an item using only FIELDS directives, no generic extractor.

        No length-based rejection: a page with only a video embed, a hero
        image, or a PDF link is still a valid item if its schema fields are
        populated. The project schema's `required` contract is enforced in
        Phase 4 of the agent workflow, not here.
        """
        from datetime import datetime, timezone

        item = {
            "url": response.url,
            "spider_name": self.spider_name,
            "spider_id": self.spider_config.id,
            "source": source_label,
            "extracted_at": datetime.now(timezone.utc),
        }
        self._apply_field_extract(item, response)
        # Pure-CSS mode skips the generic extractor (where extruct runs), so
        # source date/author from structured metadata if selectors didn't.
        _apply_meta_fallback(item, response.text)
        return item

    def _resolve_field_extract_config(self):
        """Return the FIELDS dict (legacy FIELD_EXTRACT honored), translating
        legacy CUSTOM_SELECTORS if needed."""
        directives = (
            self.custom_settings.get("FIELDS")
            or self.custom_settings.get("FIELD_EXTRACT")
            or {}
        )
        if isinstance(directives, str):
            try:
                directives = json.loads(directives)
            except Exception:
                directives = {}

        # Back-compat: a flat {field: "selector"} CUSTOM_SELECTORS dict gets
        # translated to FIELDS directive shape. Explicit FIELDS/FIELD_EXTRACT
        # entries always win — translation only fills the gaps.
        legacy = self.custom_settings.get("CUSTOM_SELECTORS") or {}
        if isinstance(legacy, str):
            try:
                legacy = json.loads(legacy)
            except Exception:
                legacy = {}
        if isinstance(legacy, dict):
            for field_name, selector in legacy.items():
                if field_name in directives:
                    continue
                if not isinstance(selector, str):
                    continue
                directives[field_name] = {
                    "css": selector,
                    "to_text": True,
                }
        return directives

    def _apply_field_extract(self, item, response):
        """Populate every project-schema field on the item.

        Reads `data/<project>/project.json` for the field whitelist and the
        spider's FIELDS setting for how to populate each non-core field.
        Fields without a directive (or whose directive returns no value) are
        explicitly set to `None`, so every schema field is guaranteed to appear
        in the output.
        """
        project = getattr(self.spider_config, "project", None)
        if not project:
            return

        schema_fields = self._load_project_schema_fields(project)
        if schema_fields is None:
            return

        directives = self._resolve_field_extract_config()

        from core.processors import apply_processors

        for field_name in schema_fields:
            directive = (
                directives.get(field_name) if isinstance(directives, dict) else None
            )

            if not directive:
                if field_name in self._CORE_SCHEMA_FIELDS:
                    # Core fields are already on the item via the extractor.
                    continue
                # Whitelist the field even if no directive — explicit null
                # makes the contract auditable in exports.
                item.setdefault(field_name, None)
                continue

            # Directive present: override whatever the extractor produced
            # (so the agent can fix a wrong newspaper author/title/etc. with
            # a precise CSS selector).

            value = None
            from_field = directive.get("from") or directive.get("from_field")
            css = directive.get("css")
            xpath = directive.get("xpath")
            get_all = directive.get("get_all", False)
            to_text = directive.get("to_text", False)
            to_markdown = directive.get("to_markdown", False)
            processors = directive.get("processors") or []

            if from_field:
                value = item.get(from_field)
            elif css or xpath:
                if css:
                    sel = response.css(css)
                else:
                    sel = response.xpath(xpath)

                if to_text:
                    # Joined descendant text of the first matched element.
                    # If the selector already targets text/attr nodes, `sel`
                    # is already textual; otherwise expand it to descendants.
                    if css:
                        if "::text" in css or "::attr" in css:
                            parts = sel.getall()
                        else:
                            parts = response.css(css + " *::text").getall()
                    else:
                        parts = response.xpath(xpath + "//text()").getall()
                    value = (
                        " ".join(p.strip() for p in parts if p and p.strip()) or None
                    )
                elif to_markdown:
                    html_block = sel.get()
                    if html_block:
                        from markdownify import markdownify as _md

                        value = _md(html_block, heading_style="ATX")
                else:
                    value = sel.getall() if get_all else sel.get()

            if processors:
                try:
                    value = apply_processors(value, processors)
                except Exception as e:
                    logger.warning(f"FIELDS processor failed for '{field_name}': {e}")

            # The selector is primary; the reader is the backup. A selector that
            # comes back null must NOT wipe what the reader already produced for a
            # core field (a broken selector can never destroy content). Non-core
            # fields have nothing to fall back to, so they stay null.
            if value is not None:
                item[field_name] = value
            elif field_name not in self._CORE_SCHEMA_FIELDS:
                item.setdefault(field_name, None)

        # Prune intermediate extractor state. The project schema is the
        # whitelist — anything not in it (e.g. extractor-side `markdown`,
        # `top_image`, `images`, `videos`, newspaper's `metadata` dict) gets
        # dropped before the pipeline so the output contains only schema
        # fields plus pipeline bookkeeping.
        bookkeeping = {
            "url",  # primary key + dedup key — must survive even when a
            # project schema does not list 'url' as one of its fields
            "spider_id",
            "spider_name",
            "source",
            "extracted_at",
            "scraped_at",
            "html",
            "_callback",
        }
        allowed = set(schema_fields) | bookkeeping
        for key in list(item.keys()):
            if key not in allowed:
                del item[key]

    _project_schema_cache: dict = {}

    def _load_project_schema_fields(self, project):
        """Return the list of schema field names for a project, or None if no schema."""
        if project in self._project_schema_cache:
            return self._project_schema_cache[project]

        from pathlib import Path
        from core.config import DATA_DIR

        path = Path(DATA_DIR) / project / "project.json"
        if not path.exists():
            self._project_schema_cache[project] = None
            return None

        try:
            with open(path) as f:
                doc = json.load(f)
            fields = [f["name"] for f in doc.get("schema", {}).get("fields", [])]
        except Exception as e:
            logger.warning(f"Failed to load project schema {path}: {e}")
            fields = None

        self._project_schema_cache[project] = fields
        return fields

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
        to_text = config.get("to_text", False)
        to_markdown = config.get("to_markdown", False)

        if css:
            result = selector.css(css)
        elif xpath:
            result = selector.xpath(xpath)
        else:
            return None

        if to_text:
            # Joined whitespace-stripped descendant text of the first match.
            # If the selector already targets text/attr nodes, it's already
            # textual; otherwise expand it to descendants.
            if css:
                if "::text" in css or "::attr" in css:
                    parts = result.getall()
                else:
                    parts = selector.css(css + " *::text").getall()
            else:
                parts = selector.xpath(xpath + "//text()").getall()
            return " ".join(p.strip() for p in parts if p and p.strip()) or None

        if to_markdown:
            html_block = result.get()
            if not html_block:
                return None
            from markdownify import markdownify as _md

            return _md(html_block, heading_style="ATX")

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

        from core.processors import apply_processors

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
                    value = self._extract_field(item_node, field_config)
                    processors = field_config.get("processors", [])
                    if processors:
                        value = apply_processors(value, processors)
                    item[field_name] = value
            items.append(item)

        return items

    async def _extract_ajax_nested_list(self, response, config):
        """Extract nested list from an AJAX endpoint.

        Makes an HTTP POST request to an AJAX URL, parses the HTML response,
        and extracts fields using the same selector system as nested_list.

        Config format:
        {
            "type": "ajax_nested_list",
            "ajax_url": "/wp-admin/admin-ajax.php",  (relative or absolute)
            "ajax_data": {"action": "wpdLoadMoreComments", ...},
            "post_id_css": "video-js::attr(data-parent-post-id)",  (selector to get post ID)
            "response_json_field": "data.comment_list",  (dot-path to HTML in JSON response)
            "selector": "div.wpd-comment",  (CSS selector for each item in response HTML)
            "extract": { ... field configs ... }
        }
        """
        import json as json_module
        from scrapy import Selector
        from core.processors import apply_processors

        ajax_url = config.get("ajax_url", "")
        ajax_data = dict(config.get("ajax_data", {}))
        post_id_css = config.get("post_id_css")
        response_json_field = config.get("response_json_field")
        item_selector = config.get("selector")
        extract_config = config.get("extract", {})

        if not ajax_url or not item_selector or not extract_config:
            logger.warning("ajax_nested_list requires ajax_url, selector, and extract")
            return []

        # Resolve relative URL
        if ajax_url.startswith("/"):
            from urllib.parse import urljoin

            ajax_url = urljoin(response.url, ajax_url)

        # Get post ID if needed
        post_id_regex = config.get("post_id_regex")
        if post_id_css:
            raw_id = response.css(post_id_css).get()
            if raw_id and post_id_regex:
                import re as re_module

                match = re_module.search(post_id_regex, raw_id)
                post_id = match.group(1) if match else raw_id
            else:
                post_id = raw_id
            if post_id:
                # Replace {post_id} placeholder in ajax_url and ajax_data values
                if "{post_id}" in ajax_url:
                    ajax_url = ajax_url.replace("{post_id}", post_id)
                for key, val in ajax_data.items():
                    if isinstance(val, str) and "{post_id}" in val:
                        ajax_data[key] = val.replace("{post_id}", post_id)

        ajax_method = config.get("ajax_method", "POST").upper()
        response_type = config.get("response_type", "json_html")
        ajax_per_page = config.get("ajax_per_page", 0)

        try:
            import curl_cffi.requests as curl_requests
            import asyncio

            loop = asyncio.get_running_loop()

            all_items = []
            page = 1
            while True:
                # Build request params
                request_data = dict(ajax_data)
                if ajax_per_page and ajax_per_page > 0:
                    request_data["per_page"] = str(ajax_per_page)
                    request_data["page"] = str(page)

                # Build the actual URL with query params for GET
                request_url = ajax_url
                if ajax_method == "GET" and request_data:
                    from urllib.parse import urlencode

                    request_url = f"{ajax_url}?{urlencode(request_data)}"

                if ajax_method == "GET":
                    resp = await loop.run_in_executor(
                        None,
                        lambda url=request_url: curl_requests.get(
                            url,
                            impersonate="chrome",
                            timeout=30,
                        ),
                    )
                else:
                    resp = await loop.run_in_executor(
                        None,
                        lambda: curl_requests.post(
                            ajax_url,
                            data=request_data,
                            impersonate="chrome",
                            timeout=30,
                        ),
                    )

                if resp.status_code != 200:
                    if page > 1:
                        break  # Pagination exhausted
                    logger.warning(
                        f"AJAX request failed: {resp.status_code} for {request_url}"
                    )
                    return all_items

                # Handle response based on type
                if response_type == "json_array":
                    # Response is a JSON array of objects (e.g., WP REST API)
                    try:
                        json_data = json_module.loads(resp.text)
                        # Navigate to nested array if response_json_field specified
                        if response_json_field and isinstance(json_data, dict):
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                        json_items = json_data
                        if not isinstance(json_items, list) or len(json_items) == 0:
                            break
                    except (json_module.JSONDecodeError, KeyError, TypeError):
                        break

                    for json_obj in json_items:
                        item = {}
                        for field_name, field_config in extract_config.items():
                            json_path = field_config.get("json_path")
                            if json_path:
                                # Navigate dot-path in JSON object
                                value = json_obj
                                for key in json_path.split("."):
                                    if isinstance(value, dict):
                                        value = value.get(key)
                                    else:
                                        value = None
                                        break
                                # Strip HTML tags if present
                                if isinstance(value, str) and "<" in value:
                                    import re as re_mod

                                    value = re_mod.sub(r"<[^>]+>", "", value).strip()
                                procs = field_config.get("processors", [])
                                if procs:
                                    value = apply_processors(value, procs)
                                item[field_name] = value
                        all_items.append(item)

                    # Check if we need to paginate
                    if (
                        ajax_per_page
                        and ajax_per_page > 0
                        and len(json_items) >= ajax_per_page
                    ):
                        page += 1
                        continue
                    else:
                        break

                elif response_type == "json_object":
                    # Response is a single JSON object — extract fields and return as dict
                    try:
                        json_data = json_module.loads(resp.text)
                        if response_json_field and isinstance(json_data, dict):
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                        if not isinstance(json_data, dict):
                            break
                    except (json_module.JSONDecodeError, KeyError, TypeError):
                        break

                    item = {}
                    for field_name, field_config in extract_config.items():
                        json_path = field_config.get("json_path")
                        if json_path:
                            value = json_data
                            for key in json_path.split("."):
                                if isinstance(value, dict):
                                    value = value.get(key)
                                elif isinstance(value, list) and key.isdigit():
                                    value = (
                                        value[int(key)]
                                        if int(key) < len(value)
                                        else None
                                    )
                                else:
                                    value = None
                                    break
                            if isinstance(value, str) and "<" in value:
                                import re as re_mod

                                value = re_mod.sub(r"<[^>]+>", "", value).strip()
                            procs = field_config.get("processors", [])
                            if procs:
                                value = apply_processors(value, procs)
                            item[field_name] = value
                    # Return as dict, not list — caller stores directly as field value
                    return item

                else:
                    # response_type == "json_html" (default)
                    html_content = resp.text
                    if response_json_field:
                        try:
                            json_data = json_module.loads(resp.text)
                            for key in response_json_field.split("."):
                                json_data = json_data[key]
                            html_content = json_data
                        except (json_module.JSONDecodeError, KeyError, TypeError) as e:
                            logger.warning(f"Failed to parse AJAX JSON response: {e}")
                            return all_items

                    sel = Selector(text=html_content)
                    for item_node in sel.css(item_selector):
                        item = {}
                        for field_name, field_config in extract_config.items():
                            if field_config.get("type") == "nested_list":
                                item[field_name] = self._extract_nested_list(
                                    item_node, field_config
                                )
                            else:
                                value = self._extract_field(item_node, field_config)
                                procs = field_config.get("processors", [])
                                if procs:
                                    value = apply_processors(value, procs)
                                item[field_name] = value
                        all_items.append(item)
                    break  # No pagination for HTML responses

            # Nest replies under parent comments if configured
            nest_replies = config.get("nest_replies", False)
            if nest_replies and all_items:
                id_field = config.get("comment_id_field") or "comment_id"
                parent_field = config.get("parent_id_field") or "parent_id"
                replies_field = config.get("replies_field") or "replies"

                # Build lookup by comment_id
                by_id = {}
                for item in all_items:
                    cid = item.get(id_field)
                    if cid is not None:
                        by_id[cid] = item
                        item[replies_field] = []

                if not by_id and all_items:
                    logger.debug(
                        f"nest_replies: no '{id_field}' found in items. "
                        f"Available keys: {list(all_items[0].keys())}"
                    )

                # Nest children under parents
                roots = []
                for item in all_items:
                    pid = item.get(parent_field)
                    if pid and pid != 0 and pid in by_id:
                        by_id[pid][replies_field].append(item)
                    else:
                        roots.append(item)

                all_items = roots
                logger.info(
                    f"Nested {len(all_items)} top-level comments "
                    f"(from {len(by_id)} total) from {ajax_url}"
                )
            else:
                logger.info(f"AJAX extracted {len(all_items)} items from {ajax_url}")

            return all_items

        except Exception as e:
            # Re-raise so the spider fails loudly instead of silently returning
            # an empty list. Previously a bare except hid ImportError for
            # curl_cffi and any genuine extraction bug looked like "no items".
            logger.error(f"AJAX extraction failed: {e}")
            raise

    def _get_callback(self, callback_name):
        """Look up a registered callback method by name.

        Args:
            callback_name: Name of the callback (must be registered via setattr)

        Returns:
            The callback method

        Raises:
            AttributeError: If callback is not registered
        """
        callback = getattr(self, callback_name, None)
        if callback is None:
            raise AttributeError(
                f"Callback '{callback_name}' not registered on spider. "
                "Ensure it is defined in the callbacks config."
            )
        return callback

    def _extract_url_context(self, url, url_context_config):
        """Extract fields from a URL using regex patterns.

        Args:
            url: The URL string to extract from
            url_context_config: Dict of {field_name: {"regex": pattern}}

        Returns:
            Dict of extracted field values
        """
        context = {}
        for field_name, field_config in url_context_config.items():
            pattern = field_config.get("regex", "")
            match = re.search(pattern, url)
            if match:
                context[field_name] = match.group(1)
            else:
                context[field_name] = None
        return context

    def _make_callback(self, callback_name, callback_config):
        """Generate a dynamic callback method for custom field extraction.

        Args:
            callback_name: Name of the callback (e.g., 'parse_product')
            callback_config: Dict with 'extract' key containing field definitions,
                           or 'iterate' key for listing→detail page workflows

        Returns:
            Async generator function for Scrapy callback
        """
        iterate_config = callback_config.get("iterate")

        if iterate_config:
            return self._make_iterate_callback(callback_name, callback_config)
        else:
            return self._make_standard_callback(callback_name, callback_config)

    def _make_iterate_callback(self, callback_name, callback_config):
        """Generate a callback that iterates over listing rows and follows detail pages."""

        async def iterate_callback(response):
            from core.processors import apply_processors

            iterate_config = callback_config["iterate"]
            row_selector = iterate_config["selector"]
            follow_config = iterate_config["follow"]
            url_context_config = iterate_config.get("url_context")
            extract_config = callback_config.get("extract") or {}

            # Extract url_context once per page
            url_context = {}
            if url_context_config:
                url_context = self._extract_url_context(
                    response.url, url_context_config
                )

            rows = response.css(row_selector)
            logger.info(
                f"Iterate {callback_name}: found {len(rows)} rows on {response.url}"
            )

            for row in rows:
                # Extract per-row fields
                row_data = {}
                for field_name, field_config in extract_config.items():
                    if field_config.get("type") == "nested_list":
                        value = self._extract_nested_list(row, field_config)
                    else:
                        value = self._extract_field(row, field_config)

                    processors = field_config.get("processors", [])
                    if processors:
                        value = apply_processors(value, processors)

                    row_data[field_name] = value

                # Extract follow URL from row
                follow_url = self._extract_field(row, follow_config["url"])
                if not follow_url:
                    logger.debug(f"Iterate {callback_name}: skipping row without URL")
                    continue

                # Combine row_data + url_context into listing_data
                listing_data = {**row_data, **url_context}

                yield response.follow(
                    follow_url,
                    callback=self._get_callback(follow_config["callback"]),
                    meta={"listing_data": listing_data},
                )

        return iterate_callback

    def _make_standard_callback(self, callback_name, callback_config):
        """Generate a standard callback that extracts fields from a single page."""

        async def standard_callback(response):
            """Generated callback that extracts custom fields and applies processors."""
            from core.processors import apply_processors

            extract_config = callback_config.get("extract") or {}
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

            # Merge listing_data from iterate parent (if any)
            try:
                listing_data = response.meta.get("listing_data", {})
            except AttributeError:
                listing_data = {}
            item.update(listing_data)

            # Extract all custom fields
            for field_name, field_config in extract_config.items():
                # Handle nested_list type
                if field_config.get("type") == "nested_list":
                    value = self._extract_nested_list(response, field_config)
                elif field_config.get("type") == "ajax_nested_list":
                    value = await self._extract_ajax_nested_list(response, field_config)
                    # json_object returns a dict — merge flat into item
                    if isinstance(value, dict):
                        item.update(value)
                        continue
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

        return standard_callback
