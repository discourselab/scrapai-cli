# 20 — `./scrapai show` reads production crawl output, not just the DB

**Requested by:** MirjamOdile (2026-07-16)
**Type:** bug (misleading tool — wrong data source)
**Status:** implemented locally (`cli/show.py`)
*(Numbered 21 before the 2026-07-16 renumbering.)*

## Problem

`./scrapai show` queried only the `scraped_items` DB table, which holds
**test-crawl / DB-pipeline** items — never the production crawl output in
`data/<project>/<spider>/crawls/*.jsonl`. Production crawls (no `--limit`)
write JSONL files, not DB rows. So `show` systematically misrepresented what a
spider actually collected, while `overview` and `audit` read the real JSONL —
the tools disagreed by design.

### Observed (news_batch_1, 2026-07-15)

`site03_org`: `show` returned **272** items (all stamped at the Phase-4 test
crawl time) while the production corpus held **1,600** rows. A reviewer using
`show` to inspect crawl output saw stale test data and drew wrong conclusions.

## Change (`cli/show.py`)

- Default source is now the spider's `crawls/*.jsonl` **when crawl files
  exist**, falling back to the DB otherwise — and the output states which
  source is shown. A fresh spider in Phase 4 (test crawl only, no crawl files
  yet) therefore still shows its DB test items with no flag needed.
- `--source db|crawls|auto` overrides the default — e.g. `--source db` to
  re-verify a test crawl after production files exist.
- The JSONL path reads its own small scanner (newest rows first, same
  `--limit/--url/--title/--text` filters) rather than importing the quality
  tool's corpus module, so this change is independent of the quality-tool PR.

## Impact

- `show` becomes trustworthy for reviewing production crawls (its main use)
  and agrees with `overview`/`audit` on what was collected.
- Removes a footgun that made several audit-review probes distrust `show` and
  fall back to reading JSONL by hand.
