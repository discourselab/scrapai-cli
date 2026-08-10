# Change request: crawl-time capture of robots.txt + llms.txt

- **Status:** IMPLEMENTED IN THIS INSTANCE (carried over from the old repo unchanged; verified live 2026-07-09 — the extension wrote `crawls/robots_09072026.txt` on the first migrated-spider test crawl). The audit's compliance cross-check reads these witnesses (`core/quality/compliance_capture/store.py::latest_crawl_file`).
- **Files:** `extensions/compliance_files.py` (new module), `extensions/__init__.py`, `settings.py` (`EXTENSIONS` wiring)
- **Type:** framework addition (new Scrapy extension)

## Problem

For compliance we want a snapshot of each site's `/robots.txt` and `/llms.txt` taken **at crawl time, through the spider's own downloader** — so the same Cloudflare / proxy / TLS handling as the crawl applies — and stored next to the crawl output, synced to the crawl that produced it. Fetching these out-of-band (plain requests) would miss sites that block non-browser/non-proxy fetches.

## Change

`ComplianceFileCapture` (enabled via `EXTENSIONS = {"extensions.compliance_files.ComplianceFileCapture": 100}` in `settings.py`):

- On `spider_opened`, derive the site root from `spider_config.source_url` (fallback: `allowed_domains[0]`) and schedule one high-priority `Request` per file (`robots.txt`, `llms.txt`) through `crawler.engine.crawl(...)`, with `handle_httpstatus_all` so non-200s are seen.
- **Manual redirect following** (≤4 hops) so it still captures the files when the spider runs `REDIRECT_ENABLED=False`.
- **Soft-404 guard:** skip when the body starts with `<` (sites that serve their HTML page with HTTP 200 for a missing file) — never store an HTML shell as a `.txt`.
- Writes the raw body to `data/<project>/<spider>/crawls/<stem>_<DDMMYYYY><ext>` (e.g. `robots_29062026.txt`).
- Every failure path is caught and logged — compliance capture must never break a crawl.

## Notes
- Files captured are configurable via the module-level `COMPLIANCE_FILES` tuple.
- No spider-config change needed; it applies to every spider once wired in `settings.py`.
