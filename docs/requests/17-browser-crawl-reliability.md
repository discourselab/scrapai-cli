# 17 — Browser crawls: fail loud on a wedged service + dedicated Pueue group

**Requested by:** @MirjamOdile (2026-07-15)
**Type:** reliability defect (fail-loud) + feature (browser-crawl concurrency)
**Status:** implemented locally (`extensions/browser_wedge.py`, `cli/crawl.py`,
`settings.py`, `handlers/cloudflare_handler.py`, `utils/browser_service.py`,
`utils/cf_browser.py`); the solve-probe liveness check is a documented follow-up.
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

1. **Fail loud on a wedged browser crawl.** New
   `extensions/browser_wedge.py`, a downloader middleware at order 950 (above
   `RetryMiddleware`, so retried attempts count), active only for crawls the
   CLI marks as browser-based via the `BROWSER_WEDGE_MARKER` setting. It counts
   **browser-service errors** only (see the addendum for what that means) and
   has two signatures:
   - **Partial wedge, mid-crawl:** 20 of the last 100 downloader attempts
     failed in the browser service. The spider is closed once, requests already
     waiting in the downloader are dropped, and in-flight downloads finish.
   - **Total wedge, at close:** zero downloader responses and at least one
     browser-service error — for crawls too small to reach the window.

   Either writes a small marker JSON. `cli/crawl.py` checks the marker after
   the scrapy subprocess exits, deletes the crawl's checkpoint, and exits **3**
   with a loud explanation, so Pueue shows `failed` instead of banking an empty
   or partial "success". `_run_spider` now also propagates the scrapy
   subprocess's own exit code (previously swallowed — any crawl error still
   exited 0).
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
- A navigation timeout inside the browser counts as a service error: the
  service cannot yet tell a hung browser from a slow or tarpitting site. A
  real liveness probe (above) would let it.

## Addendum (2026-09-28): partial wedges, mid-crawl stop

**Problem.** The zero-response signature missed a service that fails part-way through a crawl. Four browser crawls in the local production logs show it: 126, 529, 1,003 and 2,999 browser-service errors. Three were banked as successful; the fourth, the longest, was killed by hand after days. Separately, the zero-response rule counted any downloader exception, so a small crawl the site blocked outright was reported as a wedge.

Two of the four are corroborated as service-side: other browser crawls on the same service failed the same way at the same time. The other two ran alone, so the local evidence cannot rule out the site. One of those was preceded by pages the site blocked; the long one failed almost entirely on 60-second navigation timeouts.

**"verify failed" was ambiguous.** The browser service answered every failed verify with `verify failed`, including when the browser gave up on a challenge it could not pass — the site beating the browser, not a wedge. The lane now records why (`utils/cf_browser.py`, `last_error`): `challenge not passed …` for an unsolved challenge, a geo-block or access denied; `navigation error: <reason>` for a navigation that raised. The service returns it (`utils/browser_service.py`), and the handler raises a site-side reason — a challenge not passed, or a DNS, refused/reset connection, TLS, empty-response or redirect-loop error — as `Site refused the browser for <url>: <reason>`, which does not count. Everything else, including navigation timeouts and a closed or crashed page, stays `Browser service failed to verify CF for <url>: <reason>` and counts.

**Change.**
- `extensions/browser_wedge.py` is a downloader middleware (order 950, `DOWNLOADER_MIDDLEWARES`; `NotConfigured` without `BROWSER_WEDGE_MARKER`). A rolling window over the last 100 downloader attempts, ticked by `request_left_downloader`, which stamps each attempt's index into `request.meta` so an exception that arrives late counts where its attempt was. At 20 browser-service errors it closes the spider once (`close_spider_async(reason="browser_wedge")`, hence `scrapy>=2.14`), drops requests queued in the downloader, and lets in-flight downloads finish.
- Browser-service error: the message contains "browser service" (case-insensitive), or the exception is exactly the `TimeoutError` (or, before Python 3.11, `concurrent.futures.TimeoutError`) that `CloudflareDownloadHandler._run_async` re-raises after 300 s. Pages still challenged after a re-verify, transport errors on the HTTP fetch and site-side verify failures never match.
- Zero-response rule kept for small crawls, limited to browser-service errors.
- `cli/crawl.py`: exit 3 for both kinds with distinct messages. The partial crawl file is uploaded to S3 exactly as a finished crawl's would be (when S3 is configured; the upload code moves unchanged into `_upload_crawl_file`), then the crawl's checkpoint (JOBDIR) is deleted — a resume would skip every failed URL. DeltaFetch is untouched. Trade-off: a link that exists only on an already-captured item page, and was still queued at the stop, is not rediscovered by a plain re-run — only by `--reset-deltafetch`.

**Thresholds.** Replayed over all 269 local crawl logs. The replay counts outcomes rather than true downloader attempts, so attempt numbers are approximate. Three of the four wedges trip 50–65 attempts after their first service error (under 2.5 minutes). The fourth had an isolated early error and trips much later, at about attempt 3,200 of 17,000, still skipping about 14,000 attempts. The real wedges peak at 34–80 service errors per 100; the busiest healthy browser crawl at 8. With every verify failure that could have been an unpassed challenge excluded (any that took 115 s or more), all four still trip and the healthy peak drops to 6. The crawl logs do not record the service's reasons for the old failures, so this cannot rule out site-side navigation errors among the fast failures.

**Tracked docs this made wrong.** `CLAUDE.md` §6.3 (said an unreachable service fails the request and Scrapy retries; now also: a failed verify drops the page, and 20/100 stops the crawl with exit 3), `docs/checkpoint.md` (said every failed crawl keeps its checkpoint) and `docs/s3.md` (said only an exit-0 crawl is uploaded) — all corrected. `docs/browser-service.md`: none.

**Verified.** `tests/unit/test_browser_wedge.py` and `tests/unit/test_verify_failure_reason.py`, including real Scrapy crawls with fake download handlers (no network): the stop sends nothing queued, retried attempts count, errors 100 attempts back are forgotten.
