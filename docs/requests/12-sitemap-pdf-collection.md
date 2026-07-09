# Change request: PDF link collection for sitemap spiders

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-07-09)
- **File:** `spiders/sitemap_spider.py` — `SitemapDatabaseSpider.parse_article()`
- **Type:** framework change (spider parity fix)

## Problem

`PDF_MODE=links_only` (the default) records every `.pdf` link on a crawled page
as a URL-only item — but the link-scan was wired only into the **rule-based**
spider (`database_spider.py::parse_article`). Sitemap-driven spiders — the
majority of a typical KB fleet — emitted **no PDF items at all**. Any project
relying on the framework's PDF harvest (instead of per-spider extraction
directives) silently collects zero PDFs from its sitemap spiders.

## Change

`sitemap_spider.parse_article()` gains the exact block `database_spider` has:

```python
if self._pdf_mode() == "links_only":
    for purl in _pdf_links(response):
        yield self._url_only_pdf_item(purl, response, "sitemap_spider")
```

(`_pdf_links` imported from `.base`; `source_label="sitemap_spider"`.)

## Verification

- `tests/unit/test_pdf_collection.py::test_sitemap_links_only_yields_url_only_items`
  — item shape incl. `metadata_json.found_on` and `source == "sitemap_spider"`.
- Live: the gscc_batch_0 migration's first test crawl (cdkn_org, USE_SITEMAP)
  produced 21 PDF rows alongside 36 HTML articles with zero per-spider config.

## Follow-up worth considering upstream

The same parity question applies to any future parse path (custom callbacks
don't scan for PDF links either) — a single post-processing hook on yielded
responses would remove the per-spider-type duplication.
