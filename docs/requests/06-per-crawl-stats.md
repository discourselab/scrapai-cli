# Change request: dump per-crawl stats for the audit on clean finish

- **Status:** RE-GRAFTED IN THIS INSTANCE onto upstream's rewritten `base.py` (2026-07-09): `closed()` at spiders/base.py — status histogram filtered by the `downloader/response_status_count/` prefix so upstream's new `proxy/success` stats key can't leak in; path built from `core.config.DATA_DIR`. 11 unit tests incl. a round-trip through the audit's readers (`tests/unit/test_crawl_stats_writer.py`). Feeds the audit's liveness, never-ran-vs-ran-empty, and crawl-recorded coverage denominator.
- **File:** `spiders/base.py` — `BaseDBSpiderMixin.closed(reason)`
- **Type:** framework change (spider lifecycle hook)

## Problem

The audit needs each crawl's page liveness (HTTP status mix) and coverage. The old approach (`--check-liveness`) re-fetched ~1000 sampled URLs per spider and was very slow. But Scrapy already counts every response status during the crawl — that data just wasn't persisted.

## Change

Add a `closed(reason)` hook that, **only on a clean finish** (`reason == "finished"`), writes the crawl's own stats to `data/<project>/_audit/crawl_stats/<spider>.json`:

```json
{
  "spider": "...", "reason": "finished",
  "items": <item_scraped_count>,
  "requests": <downloader/request_count>,
  "status": {"200": 4890, "404": 210, ...},
  "sitemap_total": <n>,   // sitemap spiders only (see request 07)
  "eligible": <n>         // sitemap spiders only
}
```

Test/health runs are **skipped by setting, not close reason**: a crawl launched with `CLOSESPIDER_ITEMCOUNT` (that's how `--limit` and `health` run) never writes — including the sneaky case where it runs out of items *under* its limit and therefore still closes with `reason == "finished"`. Non-`finished` reasons (cancelled, shutdown) are skipped too. All errors are caught (stats-writing must not fail a crawl).

## Notes
- The audit reads these files instead of re-fetching; rule-based (non-sitemap) spiders simply omit `sitemap_total`/`eligible` and the audit falls back to fetching the sitemap for coverage.
- Pairs with request 07 (which produces `_sm_total`/`_sm_eligible`).

## Known limitations
- **Checkpoint pause/resume writes per-leg numbers — guarded, not solved.** Scrapy's stats collector and the sitemap counters are in-memory per process; nothing carries across a JOBDIR resume. The writer therefore DETECTS resumes (the scheduler's own persisted queue state, `JOBDIR/requests.queue/active.json`, is non-empty exactly when a run continues an interrupted crawl — the same file Scrapy reads to resume) and reacts by **withholding** `sitemap_total`/`eligible` and stamping the file `"resumed": true` — wrong-but-plausible coverage is worse than absent, and the audit's sitemap-fetch fallback covers the gap. `items`/`status` are still written (leg-only, marked as such). The full fix — persisting/accumulating counters across legs in the checkpoint dir — remains an upstream follow-up; note it must handle the CLI's dupefilter-clearing corruption recovery, which makes a resumed leg re-parse sitemaps (double-count risk).
- **Incremental (DeltaFetch) re-crawls shrink the sample.** A second production run skips already-seen URLs, so `items` and the status histogram reflect only the new fetches. That is "what the crawl actually faced", but liveness computed from a tiny incremental sample is weak evidence.

---

# Part 2 (merged from request 07): sitemap counters feeding the same file

The sitemap spider counts `_sm_total` (every content `<loc>` seen while parsing)
and `_sm_eligible` (those surviving date/deny filtering and matching the allow
rules) and `closed()` writes them into the SAME `crawl_stats/<spider>.json` —
giving the audit the coverage denominator the crawl actually faced, at the
crawl's own point in time (no sitemap re-fetch, no drift).

- **Status:** PARTIALLY RE-GRAFTED IN THIS INSTANCE (2026-07-09). Upstream independently adopted the deny support + relative-loc fix (different code), so only the audit COUNTERS (`_sm_total`/`_sm_eligible` → crawl_stats) were grafted onto upstream's rewritten `sitemap_filter`. CAVEAT: upstream's own deny logic runs `<sitemapindex>` entries through the filters — the original implementation deliberately did NOT (Drupal `?page=` children); see docs/requests/11-sitemapindex-deny-regression.md.
- **File:** `spiders/sitemap_spider.py` — `SitemapDatabaseSpider._get_sitemap_rules()` and `sitemap_filter()`
- **Type:** framework change (sitemap spider)

## Problem

Three gaps in the sitemap spider:
1. **No coverage denominator** — the audit had no way to know how many page URLs a sitemap declared (and how many were rule-eligible) without re-fetching and re-parsing the sitemap itself.
2. **Scrapy's `SitemapSpider` ignores `deny`** — deny patterns in a spider's rules had no effect on sitemap-driven crawls, so PDFs/images/excluded sections were still requested.
3. **Relative `<loc>`s abort the whole sitemap** — some sitemaps list relative locs (e.g. `/media/blog`). Scrapy builds `Request(loc)` directly and raises "Missing scheme", which aborts iteration of the *entire* sitemap — one bad entry silently dropped hundreds of good URLs (cape_ca got 35 of ~600).

## Change

In `_get_sitemap_rules()`: collect every rule's `deny` patterns (compiled) and compile the `allow` patterns, and record whether any rule is match-all (`/`).

In `sitemap_filter()`, per entry:
- **Count** `_sm_total` (page locs — anything not ending `.xml`/`.xml.gz`) and `_sm_eligible` (survived date + deny filters AND matches an allow rule). These are dumped by `closed()` (request 06) as the audit's coverage denominator.
- **Resolve relative locs** to absolute against `allowed_domains[0]` so one schemeless entry no longer aborts the sitemap.
- **Apply deny patterns** — drop entries whose loc matches any deny (so PDFs/images/excluded URLs are never requested), logging the dropped count.

## Notes
- This is the deny-application that request **03** (`is_index` guard) corrects for the `<sitemapindex>` edge case (Drupal `?page=N` sub-sitemaps must not be deny-filtered).
