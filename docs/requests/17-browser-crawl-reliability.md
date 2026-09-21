# 17 — Browser crawls: fail loud on a wedged service + dedicated Pueue group

**Requested by:** MirjamOdile (2026-07-15)
**Type:** reliability defect (fail-loud) + feature (browser-crawl concurrency)
**Status:** implemented locally (`extensions/browser_wedge.py`, `cli/crawl.py`,
`settings.py`); the solve-probe liveness check is a documented follow-up.
*(Numbered 18 before the 2026-07-16 renumbering — docs are now grouped
logically, not in order of discovery.)*

## Problem

**The bug:** when many Cloudflare/JS crawls run in parallel they overwhelm the
single shared browser service; it wedges (stops solving) while still reporting
`Running`; and every browser crawl that hits it in that window exits
**"completed successfully" with 0 items**. Nothing surfaces the failure — the
crawl looks done, is not retried, and only a human eyeballing `downloaded 0` in
`crawl-status` catches it. Three separate gaps compound: (a) a browser crawl
whose requests are ~100% browser exceptions still exits success, (b) browser
concurrency can't be capped independently of HTTP concurrency, (c) the
service's liveness check is process-up, not solve-works.

Observed in production (news_batch_1, 2026-07-15): 38 spiders submitted to Pueue
at `parallel 8`. Every plain-HTTP / curl_cffi crawl succeeded (site12
20,128 items; site20 22,266; site42 17,886; site13 11,156; site43
5,869). But **14 of the browser/Cloudflare crawls finished with 0 items** in an
~08:46–09:20 window when 8 CF verifications hit the browser at once —
`site05_org_za, site06_org, site10_org, site14_org,
site20_org, site21_org, site22_co_za, site24_int,
site26_org, site27_org, site34_org_za, site35_org, site36_org, site40_org`.

- `site26_org` log: `robotstxt/exception_count/<class 'Exception'>: 2`,
  `CloudflareDownloadHandler: No browser to close`, 0 responses, 0 items — with
  `CLOUDFLARE_ENABLED` even the robots.txt fetch routes through the (dead)
  browser handler, so nothing loads.
- `browser status` reported `Running (pid …)` the entire time.
- Both a CF crawl *before* the window (`site19_org`, started 08:35, 5,375 items) and
  one *after* (`site01_org`, started 09:03, scraping fine) succeeded — so
  the service self-recovered; the loss was purely the peak-parallelism window.
- Pueue marked all 14 `completed successfully`.

The only lever before this change was global `pueue parallel N` and the browser
`--pool`. `--pool 8` did not prevent the wedge (pool caps concurrent verify
slots, not the service's ability to survive them), and dropping to
`pueue parallel 3` throttles the fast HTTP crawls too — collective punishment
for a browser-only problem.

## Change

1. **Fail loud on an all-exception browser crawl.** New
   `extensions/browser_wedge.py`: for crawls the CLI marks as browser-based
   (via the `BROWSER_WEDGE_MARKER` setting), `spider_closed` checks the crawl's
   stats — **zero downloader responses + at least one downloader exception**
   means nothing loaded and the browser path was throwing, i.e. the wedge
   signature — and writes a small marker JSON. `cli/crawl.py` checks the marker
   after the scrapy subprocess exits and exits **non-zero** with a loud
   explanation, so Pueue shows `failed` instead of banking a 0-item "success".
   `_run_spider` now also propagates the scrapy subprocess's own exit code
   (previously swallowed — any crawl error still exited 0).
2. **Dedicated Pueue group for browser crawls.** Production crawls whose spider
   is browser-based (`CLOUDFLARE_ENABLED` / `BROWSER_ENABLED` / `--browser`)
   are submitted to the `scrapai-browser` Pueue group, created on first use
   with **parallelism 3**; an existing group is left untouched, so a user-tuned
   parallelism survives. HTTP/curl_cffi crawls stay in the default group at
   full width. No global throttle needed.

## Impact

- HTTP/curl_cffi crawls unaffected — they never touch the browser and keep
  running wide.
- Browser crawls self-cap at what the single service can sustain, and if it
  wedges anyway the crawl fails visibly (and is retryable) instead of silently
  empty.
- A legitimately-empty re-crawl (DeltaFetch skips everything) does NOT trigger
  the marker: skipped requests produce no downloader exceptions.
- Workaround before this change (the incident run): `pueue parallel 3` + manual
  re-run of the 14 empty crawls after confirming the service had recovered.

## Follow-up (not in this change)

- **Real liveness + self-heal:** the browser service health check should
  exercise an actual verify (a cheap solve), not just confirm the process is
  up, so the "`Running` but wedged" state is detectable and a crawl finding the
  solver dead can trigger the existing auto-restart. Deferred: it modifies the
  long-running service and cannot be verified without live CF traffic and a
  reproduced wedge.
- A small retry/backoff on transient verify failures inside a single crawl
  (service slow, not dead) would further reduce empties — distinct from the
  hard-wedge case above.
- The wedge signature is deliberately strict (zero responses); a partial wedge
  (some responses, then death) is not detected — upgrade path: an
  exception-ratio threshold.
