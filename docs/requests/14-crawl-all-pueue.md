# Change request: `crawl-all` should enqueue via Pueue, not run inline

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-07-09)
- **File:** `cli/crawl.py` — `crawl_all()`
- **Type:** framework change (CLI behaviour)

## Problem

Since production crawls auto-detach into Pueue, a single `scrapai crawl` is
parallel-safe and disconnect-safe — but `crawl-all` deliberately bypassed that
(`detached=True` forced every spider inline), so "run the whole project" meant:
strictly sequential, one spider at a time, bound to the terminal, and the whole
batch dies on Ctrl+C or an SSH drop. Found live during the gscc_batch_0
migration: a 15-spider project would have blocked a terminal for hours with no
resumability.

## Change

`crawl_all` now calls each spider through the SAME path as a single `crawl`
(`detached=False`): a full run submits itself to Pueue and returns, so the whole
project is queued in seconds, runs 5-parallel (the Pueue group default), and
survives disconnects. `--limit N` keeps the old inline sequential behaviour
(test crawls are foreground by design). A closing hint points at
`./scrapai crawl-status`.

## Verification

`tests/unit/test_crawl_pueue.py::test_crawl_all_enqueues_each_spider` (every
spider goes through the detach path; the queue hint prints) and
`::test_crawl_all_with_limit_stays_inline` (limit runs stay inline). Full suite
green.

## Trade-offs

- Pueue becomes required for `crawl-all` full runs (it already was for any
  single full crawl; the error message is the same).
- Sequential-inline behaviour, if ever wanted, is one `pueue parallel 1` away.
