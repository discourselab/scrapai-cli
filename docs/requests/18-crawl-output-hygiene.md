# 18 — Crawl-output hygiene: test crawls side-effect-free + same-day resets supersede

**Requested by:** Ranu (2026-07-16)
**Type:** bug ×2 (silent content loss + duplicate rows), one theme: a crawl run
must not corrupt another run's state or output
**Status:** implemented locally (`cli/crawl.py`)
*(Merges the former 20-deltafetch-test-crawl-poisoning and
22-crawl-file-append-duplicates.)*

## Problem A — `--limit` test crawls poison the production DeltaFetch cache

A `--limit` test crawl and the real production crawl share **one** DeltaFetch
database. The test crawl marks its URLs "seen"; the later production crawl then
skips those URLs, so they never reach `crawls/*.jsonl`.

`cli/crawl.py` sets `DELTAFETCH_DIR=deltafetch/<project>` unconditionally,
*before* the `--limit` test-mode branch (which only adds
`CLOSESPIDER_ITEMCOUNT` and does not isolate the cache). So the Phase-4A
`--limit 5` verification crawl writes into the same
`.scrapy/deltafetch/<project>/<spider>.db` the production crawl reads — a
throwaway test run permanently suppresses those URLs from production output
until someone runs `--reset-deltafetch`.

### Observed (news_batch_1, 2026-07-15/16)

Consistent signature on 4+ spiders: `crawl_stats.requests < eligible`, all-200
status, zero errors, and the missing URLs present in the `scraped_items` DB with
`scraped_at` timestamps *earlier* than the production run.

- `site23_org`: `/national-hubs/`, `/progress-and-projects/`,
  `/governance/`, `/our-purpose/` came back at **exactly 0 items** in production
  — every one of those URLs had been captured by the prior evening's test crawl
  and was live/extracting fine when re-probed.
- `site02_org` (13 URLs), `site08_org` (6 URLs): the
  entire coverage shortfall was test-suppressed URLs.

## Problem B — a same-day reset re-run appends a duplicate copy into today's file

The output file is named by date and opened in **append** mode (Scrapy's
lowercase `-o`) — intentional design: nothing ever collected is discarded, and
`--reset-deltafetch` on a *later* day is the versioning workflow (deliberate
re-capture of updated pages as new rows). The one degenerate case is the
**same-day** reset re-run — a repair of a broken run — which appends a full
second copy of everything it re-fetches into the *same* date file (the
documented cause of the audit's duplicate-rows table, e.g. `site13_org`
11,156 rows → 10,418 unique).

## Change (`cli/crawl.py`)

- **A:** `--limit` runs get `-s DELTAFETCH_ENABLED=False` — a throwaway
  verification crawl neither reads nor writes the production cache. (It also
  shouldn't *skip* anything: a re-test after a production crawl must still
  fetch its 5 items.) Production behaviour unchanged.
- **B:** `--reset-deltafetch` supersedes **today's file only** — renamed
  `crawl_DDMMYYYY.jsonl.superseded` (dedupe's reversible pattern; every
  quality lens globs `*.jsonl`, so it drops out automatically) before the
  re-crawl starts. **Older days' files are never touched**: they are the
  version history, and — since a reset re-crawl only fetches what is
  *currently reachable* — old rows may be the only copy of since-removed
  pages. Filenames stay date-based; ordinary same-day re-runs (no reset) still
  append only new items via DeltaFetch.

## Impact

- Removes a silent, hard-to-diagnose content-loss path that previously required
  a `--reset-deltafetch` re-crawl to recover from; test crawls become truly
  side-effect-free (they already write DB-only, not JSONL — this closes the
  remaining shared-state leak).
- Same-day repair re-runs stop stacking duplicate copies into today's file,
  while the versioning workflow (reset on a later day) and the
  never-discard-history property are preserved exactly as designed.

## Rejected alternatives (review, 2026-07-18)

- **Per-run filenames** (`crawl_DDMMYYYY_HHMMSS.jsonl`): solves a case that
  shouldn't exist (one production run per spider) at the cost of changing the
  file-naming contract.
- **Supersede ALL files on reset**: assumed a reset re-fetches the entire
  corpus — it doesn't (only what's currently reachable, and partial runs fetch
  less), so it would have hidden the only copy of removed pages from every
  quality lens, and it broke the later-day versioning use of reset.
