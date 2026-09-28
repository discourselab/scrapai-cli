# Change request: stop a crawl the site is blocking

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-09-28)
- **File:** `handlers/cloudflare_handler.py` — new `SiteBlockedError`, `HttpTransportError`; new `extensions/site_block.py` — `SiteBlockGuard`; `settings.py`; `cli/crawl.py` — exit 4, `_upload_crawl_file`; `requirements.txt`
- **Type:** framework change (politeness + reliability defect)
- **Requested by:** @MirjamOdile

## Problem

Getting blocked is the one crawl failure that cannot be recovered: a site that has started refusing us refuses harder the more we ask. The framework had no reaction to a block at all.

**A still-challenged page vanished silently.** In the Cloudflare handler, a page that still came back as a challenge or block page right after a fresh browser re-verify raised a bare `Exception("Still blocked after reverify: …")`. A bare `Exception` is not in Scrapy's `RETRY_EXCEPTIONS`, so the page was dropped after one attempt, counted only as a generic `builtins.Exception` in the downloader stats, and the crawl went on. `docs/cloudflare.md` said the opposite: "System auto-retries with fresh cookies, then falls back to browser if still blocked."

**A blocked crawl kept going.** Two crawls in the local production logs hit a partial block and ran to the end: 1,015 still-blocked pages in 2,079 downloader attempts on one site, 763 in 1,379 on another — every request after the block set in went to a site that was refusing us, and both crawls were banked as successful.

**A transport failure was reported as a block.** When the cookie-carrying HTTP fetch got no response at all (for example curl's TLS error "unable to get local issuer certificate"), `_fetch_with_http` returned `None` and `_is_blocked(None)` is true, so the handler took the block path: it re-verified, which renders exactly that URL in the browser, and used that render. That fallback is valuable — replaying the logs, 794 of 1,883 transport-failed URLs were captured by it, 627 pages in one crawl alone. But when it did not produce the page, the failure was reported as "Still blocked after reverify", a local fault presented as the site refusing us; any count of blocks would have included it.

## Change

1. **`SiteBlockedError`** (`handlers/cloudflare_handler.py`) replaces the bare `Exception` for a page still challenged after the re-verify. The message keeps its prefix and adds the size of the page returned. It is deliberately not an `OSError`, so Scrapy does not retry it (see *Rejected alternatives*).
2. **`HttpTransportError`**: `_fetch_with_http` raises it, carrying curl's own error text, instead of returning `None`. The handler catches it and falls back to the browser's render of that URL exactly as before (via the re-verify), so pages that fallback captured are still captured. It is raised only when the fallback yields nothing either, and it never counts as a block. Not retried in-crawl, as before. If the browser's render is itself a challenge page, that is a block and raises `SiteBlockedError`.
3. **`SiteBlockGuard`** (`extensions/site_block.py`), a downloader middleware at order 960, next to the downloader, enabled for every crawl. It keeps a rolling window over the last 100 downloader attempts (ticked by the `request_left_downloader` signal) and counts:
   - every `SiteBlockedError`;
   - every HTTP 429 **attempt**, retried or not — the middleware sits above `RetryMiddleware` (550) and `SmartProxyMiddleware` (350), so it sees each one — **except** a direct 429 while `SmartProxyMiddleware` has a proxy available (`proxy_available`) and the request did not go through it (`request.meta["proxy"]`). A 429 reaches `SmartProxyMiddleware` only after `RetryMiddleware` has given up, so counting direct 429s would stop the crawl before the proxy was ever tried: in a fake-handler simulation of a site that limits direct requests only (300 links from one listing page), counting them tripped the guard after 65 attempts with 0 proxied requests; not counting them, all 300 pages went through the proxy. The guard reads `SmartProxyMiddleware`'s state and never changes it.

   In a browser crawl the Cloudflare handler reports every page it returns as 200, so 429s never show there; only pages `_is_blocked` recognises (as `SiteBlockedError`) count.

   It does not count 403, transport failures, or browser-service errors (a local fault, request 17). Every counted page is logged as `[site-block] <url>: <reason>` and counted in the stats as `blocked/site_blocked` or `blocked/http_429`, so blocks below the threshold are never silent.
4. **At 60 of the last 100** the guard stops the crawl once: `close_spider_async(reason="site_blocked")`, requests already waiting in the downloader's slot queues are dropped rather than sent, any request reaching the middleware afterwards is refused, and downloads in flight finish.
5. **Exit 4.** The CLI passes `SITE_BLOCK_MARKER` (a temp-file path); the guard writes the marker at close, and `cli/crawl.py` prints

   ```
   🛑 SITE IS BLOCKING THE CRAWL — stopped to protect access
      60 of the last 100 downloads were blocked: 58 still challenged after a browser re-verify, 2 HTTP 429.
      Whole crawl: 140 still-challenged pages, 2 HTTP 429 responses; 900 items saved before the stop.
      Checkpoint deleted: the next run starts fresh.
      What to do:
      1. Wait before crawling this site again.
      2. Then re-run the same command. Pages that produced an item are
         skipped; start, listing and navigation pages are requested
         again, as are pages that failed.
      3. Use --reset-deltafetch only if pages are still missing after
         that re-run.
      4. If blocks recur, slow the spider (DOWNLOAD_DELAY,
         CONCURRENT_REQUESTS) or add a proxy (--proxy-type).
      Exiting 4 so this shows as FAILED, not done.
   ```

   uploads the partial crawl file to S3 as a finished crawl would (only when S3 is configured; the upload code moves into `_upload_crawl_file`), but keeps the local file: a same-day re-run appends to it (one file per day) and its own upload, to the same key, then holds both runs' rows — deleting it would let that upload overwrite the stopped run's pages in S3. Then it deletes the checkpoint and exits 4. `crawl` now exits with `_run_spider`'s return code (the same two-line change request 17 makes). Without the marker setting — a plain `scrapy crawl` — the crawl still stops; only the exit code is missing.
6. **`scrapy>=2.14.0`** in `requirements.txt`: `close_spider_async` first shipped in 2.14. The same line request 17 sets.
7. **Checkpoint deleted on exit 4**, never resumed. A resume from the checkpoint skips every URL that failed (they are already in `RFPDupeFilter`'s `requests.seen` and nothing re-schedules them) and then reports success. A fresh run, with DeltaFetch kept, re-requests exactly the pages that produced no item and skips everything already captured. DeltaFetch is not touched.

## Thresholds

Replayed over every local crawl log (269 crawls), counting per downloader attempt:

| | window max | trips at attempt | attempts after first block | later attempts not sent |
|---|---|---|---|---|
| partial block, site A | 76 | 337 of 1,379 | 92 (5 min) | 1,042 (703 of them blocks) |
| partial block, site B | 70 | 551 of 2,079 | 547 (17 min) | 1,528 (865 of them blocks) |
| busiest healthy crawl | 47 | — | — | — |

**The 429 evidence is thin.** No local crawl was ever rate-limited to a stop; 429s appear in one healthy crawl only: 43 of its 325 responses, 42 of which succeeded on retry. Even if all 43 fell inside one 100-attempt window, that is under 60. With an offline fake handler answering 429 to everything under default retry settings, the guard trips at attempt 60 and sends nothing after; the same crawl without it would fire three attempts per URL (3,000 for 1,000 URLs).

## Behavior changes

- A crawl with 60 blocks in its last 100 downloader attempts stops and exits 4 instead of running to the end. In a browser crawl the blocks are still-challenged pages; in a plain HTTP crawl, 429s once no untried proxy is left.
- A still-challenged page raises `SiteBlockedError`, is logged and counted (`blocked/site_blocked`). It was already not retried; now it says so.
- A transport failure on the Cloudflare HTTP fetch still falls back to the browser's render; when that fails too it raises `HttpTransportError` instead of "Still blocked", and it never counts as a block.
- Exit 4 uploads the partial crawl file (when S3 is configured) and keeps it locally for a same-day re-run to append to, then deletes the checkpoint; the next run starts fresh.

**Unchanged:** no page is retried in-crawl that was not before; the browser fallback on a transport failure; 403 handling, `SmartProxyMiddleware`'s proxy escalation, Scrapy's retry of 429, DeltaFetch, the S3 upload of a finished crawl, and the checkpoint behaviour of every other exit.

**Known limitations:**
- A crawl with fewer than 60 blocked attempts in any window — a small site blocked outright — is not stopped. Its blocked pages are logged and counted, so the shortfall is visible in the stats, not silent.
- The window is global to the crawl, not per host. A spider that crawls several hosts can be stopped by one host blocking it (the others stop too), and a host whose blocks are diluted by healthy traffic to other hosts may never reach 60.

**The checkpoint trade-off, stated plainly:** deleting it means a link that exists only on an already-captured item page, and was still queued when the crawl stopped, is not rediscovered by a plain re-run (DeltaFetch skips that item page, so its links are never seen again). Only `--reset-deltafetch` finds it. That is why the advice keeps `--reset-deltafetch` for a re-run that still shows a gap, rather than removing it.

## Follow-ups (separate framework issues, not fixed here)

- **A site that beats the browser.** A verify the browser cannot get past (the challenge never clears) is not counted by this window, which counts `SiteBlockedError` and 429 only. With request 17 merged, that error is reported as the site's doing, so the wedge window does not count it either: a site that beats the browser on every page is counted by neither detector. This request could count it as a block.

- **Pre-escalation hammering.** In auto mode a site answering 429 gets every direct request retried twice by `RetryMiddleware` before `SmartProxyMiddleware` sees it and switches the domain to the proxy — in the fake-handler simulation (300 links from one listing page), 609 direct 429 attempts before the first proxied request. That is existing framework behaviour (middleware order and retry priority); this request deliberately does not count those 429s so the escalation still happens, and leaves the order alone.

## Rejected alternatives

- **Retry blocked pages in-crawl.** Two measured reasons. (1) Counted by final outcome, retries dilute the window: the two real blocks peak at about 45–57 per 100 instead of 70–76, and neither would ever trip 60. (2) Scrapy queues retries behind every page not yet fetched (`RETRY_PRIORITY_ADJUST=-1`), so under a total block about twice the pages would be requested before the first retry gave up — more requests at a refusing site than today.
- **Count only the 429s left after retries.** In a window of attempts this can never trip: each final 429 costs three attempts under the default two retries, so a total 429 block peaks at 36 per 100 (measured with the fake handler). Hence every 429 attempt counts.
- **Count 403.** Healthy crawls hit dense runs of 403 on login-only sections — up to 98 of 100 — so any threshold that caught a block would stop healthy crawls.
- **Replay failed URLs from the checkpoint instead of deleting it.** Nothing in Scrapy re-schedules a request its dupefilter has seen; replaying would mean editing `requests.seen` by hand. A fresh run with DeltaFetch already requests exactly the missing pages, with the trade-off above.

## Tracked docs this makes wrong

- `docs/cloudflare.md`, *Blocked Despite Cookies*: claimed a still-blocked page is auto-retried and then falls back to the browser, and quoted a log line the handler no longer writes. Rewritten to what happens now, including exit 4 and the transport case. Its *If repeated* list is left as it is.
- `docs/s3.md`, *Upload Process*: said the upload follows a successful (exit 0) crawl; an exit-4 crawl's partial file is uploaded too.
- `docs/proxies.md`: stays true — the escalation, its order and the expert-in-the-loop prompt are unchanged; the guard only reads the proxy state.
- `docs/checkpoint.md`, *Smart cleanup*: "exit code != 0 → keep checkpoint" now has an exception for exit 4, with the trade-off; the troubleshooting line on a missing checkpoint names it.
- `docs/deltafetch.md`: none made wrong by this change.

## Verification

- `tests/unit/test_site_block.py`, 34 tests:
  - window: trips at 60 not 59; exactly 100 attempts wide; a direct 429 counts unless a live proxy is still to be tried (a proxy declared dead counts as none); ignores 403, transport, browser-service errors and `IgnoreRequest`; forgets blocks older than 100 attempts; every block counted in stats; trip closes once, drops queued requests and refuses new ones; marker written only when tripped, with the window as it stood at the stop; stale marker removed.
  - handler: `SiteBlockedError` and `HttpTransportError` are not retryable and never say "browser service"; still blocked after re-verify raises `SiteBlockedError`; when curl fails and the browser renders the URL, the page is returned and nothing is counted; `HttpTransportError` only when the browser yields nothing too; a utility file skips the browser; `_fetch_with_http` carries curl's error.
  - real Scrapy crawls with a fake download handler and the project's middleware order (guard 960, `SmartProxyMiddleware` 350, default retries), no network. Every URL is linked from one listing page, so all are scheduled at once:
    - a total 429 block with no proxy stops on the 60th 429 and sends nothing after;
    - retried 429s count (30 URLs trip it);
    - with a proxy and a site that limits direct requests only, the crawl finishes with all 300 pages through the proxy and no 429 counted. Counting direct 429s instead trips after 65 attempts with 0 proxied;
    - 429s through the proxy count and stop the crawl;
    - `SiteBlockedError` through the real chain trips it, is never retried, and with download latency and a delay the requests waiting in the downloader at the stop are not sent;
    - 59 blocks, 100 good pages and 59 more blocks never trip it (the window forgets, and its attempt counter is wired to the downloader);
    - a total 403 crawl and a healthy crawl both finish.
  - the project's `settings.py` loads the guard above `RetryMiddleware` and `SmartProxyMiddleware`.
  - CLI: exit 4 with the message and the checkpoint deleted; the partial crawl file uploaded, and kept, before the checkpoint is deleted; with a fake S3, a stop plus a same-day re-run leaves both runs' rows in the one object; a clean crawl uploads as before; a failed crawl without a block keeps its checkpoint; a clean crawl exits 0; `crawl` exits with the code.
- Full unit suite: 522 passed. black clean; flake8 (CI settings) no new findings.
