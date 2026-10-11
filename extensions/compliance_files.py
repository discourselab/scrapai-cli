"""Crawl-time capture of /robots.txt and /llms.txt. When a spider opens, this
extension schedules one request per file through the spider's OWN downloader
(so the same Cloudflare / proxy / TLS handling as the crawl applies) and writes
the raw body next to the crawl output, date-stamped, so the compliance snapshot
is synced to the crawl that produced it.

Enable via EXTENSIONS in settings.py:
    "extensions.compliance_files.ComplianceFileCapture": 100
"""
import os
from datetime import datetime
from urllib.parse import urlparse

from scrapy import signals, Request

# Fetched once per crawl at the site root.
COMPLIANCE_FILES = ("robots.txt", "llms.txt")


class ComplianceFileCapture:
    """Capture robots.txt/llms.txt through the spider's own downloader."""

    def __init__(self, crawler):
        self.crawler = crawler
        self.spider = None

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        return ext

    def _base_url(self, spider):
        """Derive the org's real site root (source_url, else first domain)."""
        cfg = getattr(spider, "spider_config", None)
        src = getattr(cfg, "source_url", None)
        if src:
            p = urlparse(src if "://" in src else "https://" + src)
            if p.netloc:
                return f"{p.scheme or 'https'}://{p.netloc}"
        doms = getattr(spider, "allowed_domains", None) or []
        return f"https://{doms[0]}" if doms else None

    def spider_opened(self, spider):
        self.spider = spider
        base = self._base_url(spider)
        if not base:
            spider.logger.warning("[compliance] no source_url/allowed_domains; skipping robots/llms capture")
            return
        for fname in COMPLIANCE_FILES:
            url = base.rstrip("/") + "/" + fname
            req = Request(
                url,
                callback=self._save,
                errback=self._err,
                dont_filter=True,
                priority=10000,
                meta={"compliance_file": fname, "handle_httpstatus_all": True},
            )
            try:
                self.crawler.engine.crawl(req)
            except Exception as e:  # never let compliance capture break a crawl
                spider.logger.warning(f"[compliance] could not schedule {url}: {e}")

    def _save(self, response):
        fname = response.meta.get("compliance_file", "compliance.txt")
        # Follow redirects manually, so robots/llms are captured even when the
        # spider has REDIRECT_ENABLED=False.
        if response.status in (301, 302, 303, 307, 308):
            loc = response.headers.get("Location")
            depth = response.meta.get("compliance_redirects", 0)
            if loc and depth < 4:
                loc = loc.decode("latin1") if isinstance(loc, bytes) else loc
                req = response.request.replace(
                    url=response.urljoin(loc),
                    meta={**response.meta, "compliance_redirects": depth + 1},
                )
                try:
                    self.crawler.engine.crawl(req)
                except Exception as e:
                    self.spider.logger.warning(f"[compliance] redirect for {fname} not scheduled: {e}")
            else:
                self.spider.logger.info(f"[compliance] {fname}: redirect not followed")
            return
        if response.status != 200 or not response.body:
            self.spider.logger.info(f"[compliance] {fname}: HTTP {response.status} — not saved")
            return
        # A real robots.txt/llms.txt is plain text and never starts with '<'.
        # Many sites soft-404 (serve their HTML page with HTTP 200) for a missing
        # file; skip those so we never store an HTML shell as a .txt file.
        if response.body.lstrip(b"\xef\xbb\xbf").lstrip()[:1] == b"<":
            self.spider.logger.info(f"[compliance] {fname}: response is HTML (no real file) — not saved")
            return
        spider = self.spider
        project = getattr(getattr(spider, "spider_config", None), "project", None) or "default"
        name = getattr(spider, "spider_name", None) or spider.name
        # Same base dir as the crawl JSONL export (DATA_DIR is .env-configurable
        # and cwd-independent) — the audit's witness reader looks there.
        from core.config import DATA_DIR
        out_dir = os.path.join(DATA_DIR, project, name, "crawls")
        os.makedirs(out_dir, exist_ok=True)
        stem, ext = os.path.splitext(fname)  # robots.txt -> robots, .txt
        stamp = datetime.now().strftime("%d%m%Y")
        path = os.path.join(out_dir, f"{stem}_{stamp}{ext}")
        try:
            with open(path, "wb") as fh:
                fh.write(response.body)
            spider.logger.info(f"[compliance] saved {fname} -> {path} ({len(response.body)} bytes)")
        except OSError as e:
            spider.logger.warning(f"[compliance] failed writing {path}: {e}")

    def _err(self, failure):
        req = getattr(failure, "request", None)
        fname = (req.meta.get("compliance_file") if req else None) or "compliance file"
        if self.spider:
            self.spider.logger.info(f"[compliance] {fname}: fetch failed ({failure.value!r}) — not saved")
