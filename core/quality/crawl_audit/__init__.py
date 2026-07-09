"""Coverage & extraction audit for every spider in a project.

One tool, three stages:
  1. crawl  — count unique scraped URLs + extraction success from crawls/*.jsonl
  2. fetch  — for USE_SITEMAP spiders, fetch sitemaps via `./scrapai inspect`
              (recurse <sitemapindex> with caps), cache the XML on disk
  3. match  — apply each spider's allow-rules to the cached sitemaps to get the
              real coverage denominator, then join with the scraped counts

All spider metadata (start_urls, USE_SITEMAP, allow rules, browser flags) is read
LIVE from the DB, so the audit auto-includes new sources and never needs editing.

Usage (via the CLI — this module is the engine behind `./scrapai audit`):
  ./scrapai audit --project policy                   # default: fetch only where missing
  ./scrapai audit --project policy --no-fetch        # never fetch; use cache only
  ./scrapai audit --project policy --fetch-all       # re-fetch every sitemap (refresh)
  ./scrapai audit --project thinktanks --only iea_org --only epa_gov

Sitemaps whose counts came from the crawl itself (crawl_stats) are never fetched.

Liveness: only computed when a real crawl recorded its own HTTP-status stats
(data/<project>/_audit/crawl_stats/<spider>.json, written by the spider's closed()
handler). No sampling/probing — if those stats are absent, eligible is the plain
rule-matched sitemap count.

Outputs: data/<project>/_audit/{audit_<project>.md, crawl_audit.csv, coverage.csv}
Sitemap cache:    data/<project>/_audit/sitemap_cache/<spider>_<n>/page.html
Crawl-scan cache: data/<project>/_audit/scan_cache/<spider>.json — per-file crawl
                  COUNTS keyed by (size, mtime); unchanged crawl files reload from
                  it instead of re-reading GBs of JSONL. `--no-cache` ignores it.
Manual config (per-project, optional): data/<project>/_audit/{audit_notes.json,
audit_sitemap_skip.json} — review notes and sitemap-skip entries, keyed by spider
(no project wrapper; each lives in its own project's audit folder).

This package is a facade over the split modules (engine, scoring, sitemaps,
spiders_db, review, report, text). It re-exports only the names external
consumers use (the CLI, the dashboard, the tests); everything else is imported
from its own module. Importing the facade also binds the submodules as
attributes (`crawl_audit.sitemaps`, `crawl_audit.spiders_db`, ...).
"""

import subprocess  # noqa: F401 — kept on the facade: tests patch `crawl_audit.subprocess.run`

from .engine import run
from .review import ensure_review_configs
from .scoring import score_spider  # noqa: F401 — binds the scoring submodule too
from .sitemaps import collect_pages, fetch, fetch_spider_sitemaps
from .spiders_db import (
    crawl_ran,
    crawl_stats_liveness,
    crawl_stats_sitemap,
    project_exists,
)
from .text import LEGEND, STATUS_LEADS, fix_hints

__all__ = [
    "LEGEND",
    "STATUS_LEADS",
    "collect_pages",
    "crawl_ran",
    "crawl_stats_liveness",
    "crawl_stats_sitemap",
    "ensure_review_configs",
    "fetch",
    "fetch_spider_sitemaps",
    "fix_hints",
    "project_exists",
    "run",
    "score_spider",
    "subprocess",
]
