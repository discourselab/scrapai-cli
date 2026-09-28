# Change request: dump per-crawl stats for the audit on clean finish

- **Status:** RE-GRAFTED IN THIS INSTANCE onto upstream's rewritten `base.py` (2026-07-09): `closed()` at spiders/base.py — status histogram filtered by the `downloader/response_status_count/` prefix so upstream's new `proxy/success` stats key can't leak in; path built from `core.config.DATA_DIR`; Scrapy's raw final-outcome counters (`responses`, `final_status`, `exceptions`, `retries`) written alongside, and the sitemaps Scrapy rejected (`sitemap_rejected`). Unit tests incl. a round-trip through the audit's readers (`tests/unit/test_crawl_stats_writer.py`, `tests/unit/test_crawl_stats_outcomes.py`). Feeds the audit's dead / blocked / failed request outcomes, never-ran-vs-ran-empty, the crawl-recorded coverage denominator and the `sitemap rejected (N)` flag.
- **File:** `spiders/base.py` — `BaseDBSpiderMixin.closed(reason)`
- **Type:** framework change (spider lifecycle hook)

## Problem

The audit needs each crawl's status counts, how its requests finally ended, and its coverage denominator. The old approach (`--check-liveness`) re-fetched ~1000 sampled URLs per spider and was very slow. But Scrapy already counts every response status during the crawl — that data just wasn't persisted.

## Change

Add a `closed(reason)` hook that, **only on a clean finish** (`reason == "finished"`), writes the crawl's own stats to `data/<project>/_audit/crawl_stats/<spider>.json`:

```json
{
  "spider": "...", "reason": "finished",
  "items": <item_scraped_count>,
  "requests": <downloader/request_count>,
  "status": {"200": 4890, "404": 210, ...},
  "responses": <response_received_count>,
  "final_status": {"404": 180, "403": 12, ...},
  "exceptions": {"twisted.internet.error.TimeoutError": 9, ...},
  "retries": {"twisted.internet.error.TimeoutError": 6, "503 Service Unavailable": 4, ...},
  "sitemap_rejected": ["https://example.org/sitemap.xml", ...],   // [] when none
  "sitemap_total": <n>,   // sitemap spiders only (see request 07)
  "eligible": <n>         // sitemap spiders only
}
```

`status` counts every download attempt, retried ones included. The other four keys are Scrapy's own counters, written uninterpreted so the audit can derive final outcomes (and change its formula) without a re-crawl: `responses` = final responses only; `final_status` = final non-2xx responses after retry and proxy handling (`httperror/response_ignored_status_count/`; the compliance witness fetches never land there); `exceptions` = `downloader/exception_type_count/` per class (attempt-level, IgnoreRequest included); `retries` = `retry/reason_count/` (exception class names, or `"<code> <Reason>"` for HTTP-code retries). All four are always present (`{}` / `0` when empty), so a new-format file is distinguishable from an older one. The audit reads them in `crawl_stats_outcomes()`: dead = 404/410 and blocked = 403/429/401 from `final_status`; failed = exceptions minus the retried ones, IgnoreRequest skipped.

`sitemap_rejected` lists the sitemaps Scrapy's `SitemapSpider` refused to parse ("Ignoring invalid sitemap"): a response whose body `_get_sitemap_body()` can't produce, or whose root element is neither `urlset` nor `sitemapindex` — typically an HTML view of the sitemap or a block page served as 200. A body with no root element at all (plain text such as `Forbidden` at a `.xml` URL), on which Scrapy's `Sitemap()` raises a spider error, is ignored and counted the same way. Scrapy drops every URL in such a sitemap, and `sitemap_filter()` never sees them, so `sitemap_total` / `eligible` are short whenever the list is non-empty; they are still written, and the list is what tells the audit so (`sitemap rejected (N)` flag, manual review). Always present (`[]` when none, and on rule-based spiders); summed legs take the union, and a resumed leg also takes the URLs in the kept `index.json`, so a rejection in a leg that died before handing its counters on is still reported. The check runs on Scrapy's materialised result, since older Scrapy versions return a generator that reads the body only when iterated. Each rejection also increments the Scrapy stat `sitemap/rejected` and logs a WARNING with the URL, status and body size. The bodies are kept in `data/<project>/_audit/sitemap_rejects/<spider>/` with an `index.json` (`file`, `url`, `status`, `bytes`, `content_type`): at most 20 files per crawl, each cut at 256 KB; a fresh production crawl clears the folder, a resumed leg continues after the highest file number already there (so nothing is overwritten even when `index.json` can't be read), and `--limit` runs keep nothing. The folder is only used and cleared when it is a direct child of `sitemap_rejects/`; a spider name such as `..` gets a warning and keeps nothing. Scrapy's handling of valid sitemaps is unchanged; why these sitemaps come back unparseable is a separate question.

Test/health runs are **skipped by setting, not close reason**: a crawl launched with `CLOSESPIDER_ITEMCOUNT` (that's how `--limit` and `health` run) never writes — including the sneaky case where it runs out of items *under* its limit and therefore still closes with `reason == "finished"`. Non-`finished` reasons (cancelled, shutdown) are skipped too. All errors are caught (stats-writing must not fail a crawl).

## Notes
- The audit reads these files instead of re-fetching; rule-based (non-sitemap) spiders simply omit `sitemap_total`/`eligible` and the audit falls back to fetching the sitemap for coverage.
- Pairs with request 07 (which produces `_sm_total`/`_sm_eligible`).

## Known limitations
- **Checkpoint pause/resume: legs are summed; the sitemap denominator stays withheld.** Scrapy's stats collector and the sitemap counters are in-memory per process; nothing carries across a JOBDIR resume on its own. The writer DETECTS resumes (the scheduler's own persisted queue state, `JOBDIR/requests.queue/active.json`, is non-empty exactly when a run continues an interrupted crawl — the same file Scrapy reads to resume) and stamps the file `"resumed": true`. A checkpointed leg that stops early keeps its counters in its own JOBDIR (`crawl_stats_leg.json`); the leg that resumes takes them, adds its own and writes whole-crawl `items` / `status` / outcome counters stamped `"summed": true` (the leg file is removed as soon as it is taken, and goes with the checkpoint when the CLI removes it). A leg that died without closing leaves nothing to take, so the next leg writes its own numbers only — `resumed` without `summed`. `sitemap_total`/`eligible` stay **withheld** on every resumed crawl — wrong-but-plausible coverage is worse than absent (the CLI's dupefilter-clearing corruption recovery makes a resumed leg re-parse sitemaps, a double-count risk), and the audit's sitemap-fetch fallback covers the gap. The audit reads a summed file as a whole crawl; an unsummed one shows its dead / blocked / failed with a `last leg` suffix and still flags blocked / failed over the threshold, with the `last leg` caveat in the flag.
- **Incremental (DeltaFetch) re-crawls shrink the sample.** A second production run skips already-seen URLs, so `items`, the status histogram and the outcome counters reflect only the new fetches. That is "what the crawl actually faced", but outcome shares computed from a tiny incremental sample are weak evidence.

---

# Part 2 (merged from request 07): sitemap counters feeding the same file

The sitemap spider counts `_sm_total` (every content `<loc>` seen while parsing)
and `_sm_eligible` (those surviving date/deny filtering and matching the allow
rules) and `closed()` writes them into the SAME `crawl_stats/<spider>.json` —
giving the audit the coverage denominator the crawl actually faced, at the
crawl's own point in time (no sitemap re-fetch, no drift).

- **Status:** PARTIALLY RE-GRAFTED IN THIS INSTANCE (2026-07-09). Upstream independently adopted the deny support + relative-loc fix (different code), so only the audit COUNTERS (`_sm_total`/`_sm_eligible` → crawl_stats) were grafted onto upstream's rewritten `sitemap_filter`.
- **File:** `spiders/sitemap_spider.py` — `SitemapDatabaseSpider._get_sitemap_rules()` and `sitemap_filter()`
- **Type:** framework change (sitemap spider)

## Problem

Three gaps in the sitemap spider:
1. **No coverage denominator** — the audit had no way to know how many page URLs a sitemap declared (and how many were rule-eligible) without re-fetching and re-parsing the sitemap itself.
2. **Scrapy's `SitemapSpider` ignores `deny`** — deny patterns in a spider's rules had no effect on sitemap-driven crawls, so PDFs/images/excluded sections were still requested.
3. **Relative `<loc>`s abort the whole sitemap** — some sitemaps list relative locs (e.g. `/media/blog`). Scrapy builds `Request(loc)` directly and raises "Missing scheme", which aborts iteration of the *entire* sitemap — one bad entry silently dropped hundreds of good URLs (site01_org got 35 of ~600).

## Change

In `_get_sitemap_rules()`: collect every rule's `deny` patterns (compiled) and compile the `allow` patterns, and record whether any rule is match-all (`/`).

In `sitemap_filter()`, per entry:
- **Count** `_sm_total` (page locs — anything not ending `.xml`/`.xml.gz`) and `_sm_eligible` (survived date + deny filters AND matches an allow rule). These are dumped by `closed()` (request 06) as the audit's coverage denominator.
- **Resolve relative locs** to absolute against `allowed_domains[0]` so one schemeless entry no longer aborts the sitemap.
- **Apply deny patterns** — drop entries whose loc matches any deny (so PDFs/images/excluded URLs are never requested), logging the dropped count.

## Notes
- This is the deny-application that request **03** (`is_index` guard) corrects for the `<sitemapindex>` edge case (Drupal `?page=N` sub-sitemaps must not be deny-filtered).
