# 23 — Sitemap crawl-recorded denominator: unique pages only, media excluded

**Requested by:** MirjamOdile (2026-07-16)
**Type:** bug (measurement — audit coverage denominator)
**Status:** implemented locally (`spiders/sitemap_spider.py`); ships as a patch
commit on the open **per-crawl-stats PR (PR 3)**, whose code it corrects.
*(Lineage: originally the "Fix C-companion" of the audit bundle (22), briefly
merged into 19; split out 2026-07-19 because it belongs to PR 3, not to a
standalone PR.)*

## Problem

For `USE_SITEMAP` spiders the audit's coverage denominator comes from a counter
recorded at crawl time in `sitemap_filter()` (introduced by the per-crawl-stats
change), which (a) counted image/attachment `<loc>`s (WP image/attachment
sitemaps) as content pages and (b) summed raw locs across sub-sitemap files
with no cross-file dedup. This is why `site12_org` showed 3,742 phantom
"missing" pages (attachment images) and `site10_org`-class
spiders reported `eligible` above their true unique-URL count.

(The audit's own *fetched*-sitemap path got the equivalent media filter in
request 22, Fix C; this counter takes precedence over the fetched path when
present, so it must apply the same rules.)

## Change (`spiders/sitemap_spider.py`)

`_sm_total` / `_sm_eligible` now count **unique** page locs (a set-guard dedups
across sub-sitemap files) and **exclude media extensions** (the same list the
audit's fetched path uses — duplicated locally because the spider must not
import the quality tool). Measurement-only: the counter feeds `crawl_stats/`,
it does not gate crawling. Takes effect on future crawls.

Also updates the stale liveness expectation in
`tests/unit/test_crawl_stats_writer.py` (the audit-side 5xx fix — request 22,
Fix A — changed the expected rate; the test file belongs to this PR's area and
skips cleanly when the quality tool is absent).

## Impact

- `site12_org`-class phantom "missing" pages and inflated `eligible`
  counts disappear from the audit once the spider re-crawls.
- Reported numbers only — no crawl or data behaviour changes.
