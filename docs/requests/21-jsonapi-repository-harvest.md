# 21 — Repository-harvest spider (JSON:API / paginated-JSON) — port

**Requested by:** Ranu (2026-07-13)
**Type:** feature port (proven in the pre-migration production repo as its request 11)
**Status:** implemented (spiders/repository_spider.py + cli/crawl.py routing), tests green
*(Numbered 17 before the 2026-07-16 renumbering.)*

## Problem

Institutional repositories (Islandora/Fedora, DSpace, Samvera on Drupal fronts) are
often un-crawlable as HTML at any polite rate: Cloudflare Turnstile on every page,
`robots.txt Crawl-delay: 120`, a homepage-only sitemap, and broken/partial OAI-PMH.
Yet the same sites expose a fully open, CF-free machine API (Drupal JSON:API) that
enumerates the complete repository with pagination and inline relationship joins.
scrapai had no way to ingest a paginated JSON collection: `USE_SITEMAP` is XML-only,
rules/callbacks operate on HTML responses, and no processor parses JSON.

Concrete case: repo.site31.edu (large institutional research repository, ~20-30k PDF
documents). HTML crawl ≈ weeks behind Turnstile at 120 s/request; JSON:API harvest
≈ one polite pass.

## Change

1. **`spiders/repository_spider.py`** — new `repository_database_spider`
   (`BaseDBSpiderMixin` + plain `scrapy.Spider`). Walks the JSON collection endpoint
   in `start_urls`, follows the `next` link dot-path until absent, and maps each
   record to a normal pipeline item via the `REPOSITORY_SOURCE` setting:
   `records`/`next`/`included_key`/`require` dot-paths plus a per-item-field `map`
   supporting dot-paths with ` || ` fallbacks, JSON:API `include` relationship
   resolution (indexed `(type,id)` lookup), `template` URL building, `list`
   wrapping, and the standard `core.processors` chain. Records failing the
   `require` field (e.g. unpublished parent node omitted from `included`) are
   skipped, not errored.
2. **`cli/crawl.py`** — the presence of a non-empty `REPOSITORY_SOURCE` spider
   setting routes the crawl to `repository_database_spider` (checked alongside the
   existing `USE_SITEMAP` routing).

No existing spider path is touched; HTML/sitemap spiders behave exactly as before.

## Tests

`tests/unit/test_repository_spider.py` (8 tests, `pytest.mark.unit`): dot-path
walker (dicts, list indices, negatives), `||` fallback resolution, full item
mapping (template + include + list + processors), missing-include → null field,
`require` skip, pagination follow, last-page stop, malformed records path, and
item-limit pagination cutoff. Suite: 494 passed; black + flake8 clean.

## Notes

- The config validator caps `DOWNLOAD_DELAY` at 60, so repository spiders honoring
  a `Crawl-delay: 120` robots directive import with `--skip-validation`
  (politeness must be set manually in the spider JSON; Scrapy does not apply
  robots crawl-delay itself).
- First user: `site31_edu` (news_archive) — see its `analysis/NOTES.md` for
  the full site investigation (broken OAI, Turnstile, JSON:API discovery) and the
  exact `REPOSITORY_SOURCE` mapping.
