# 16 — SmartProxyMiddleware: dead-proxy detection + fail-open to direct

**Requested by:** MirjamOdile (2026-07-10)
**Type:** bugfix (reliability defect — not a feature request)
**Status:** implemented locally (middlewares.py), candidate for upstream PR

## Problem

**The bug:** the middleware escalates blocked domains onto a proxy but is blind
to whether that proxy works — it implements no `process_exception`, so proxied
requests that die at transport level (the only signal a broken proxy gives)
teach it nothing. Its own escalation path can take a crawl from healthy to
zero throughput with no error surfaced and no recovery. The fix adds the
missing failure-detection half of a mechanism that was shipped with only its
happy path.

In auto mode, one 403/429/503 on any page adds the whole domain to
`blocked_domains`, and every subsequent request for that domain is routed
through the escalation proxy. The middleware has no `process_exception`, so it
never learns when the proxy itself is broken (CONNECT refused/403, hangs). With
a dead datacenter proxy the crawl enters a terminal state: each request burns
`DOWNLOAD_TIMEOUT × RETRY_TIMES` through the dead proxy, throughput drops to
zero, and the crawl either wedges indefinitely or silently under-scrapes.

Observed five times in production (news_archive, 2026-07-10):
- `site09_gov_au` / `site11_gov_au` / `site16_gov_au`: the
  crawl-start llms.txt compliance probe 403'd → domain marked blocked → dead
  proxy → 0-item crawls (25 min, 329/103/123 proxy attempts, 0% success).
- `site18_eu`: ONE robots-benign privacy page 403'd at minute 1
  → wedged at 52 pages for 2+ hours (0 pages/min).
- `site39_int`: subdomain pages 403'd in the first seconds → wedged at 96 items.

Two design flaws compound: (a) proxy health is never verified, (b) compliance
witness probes (robots/llms fetches, which many sites 403) can poison the
domain for the whole crawl.

## Change (middlewares.py, auto mode only)

1. **Dead-proxy detection**: new `process_exception` counts CONSECUTIVE
   transport-level failures of proxied requests (any exception reaching the
   middleware after retries); any proxied response that arrives resets the
   counter. At 5 consecutive failures the proxy is declared dead for the crawl.
2. **Fail-open to direct**: once dead — `blocked_domains` is cleared, no new
   escalation happens, scheduled/retried requests carrying the proxy have it
   stripped, and the triggering request is re-issued direct. Blocked pages then
   just fail through the normal retry path (skip-not-poison). A loud one-time
   log explains what happened and suggests `--proxy-type none` (site actually
   fine direct) or `--proxy-type residential` (site truly blocks).
3. **Compliance probes can't poison**: responses for requests carrying the
   `compliance_file` meta (the crawl-time robots/llms witnesses) never mark the
   domain blocked — the witness records the 403 as evidence instead.

Explicit `--proxy-type residential`/`PROXY_FROM_START` crawls are NOT failed
open (the proxy is the user's deliberate choice there); they only get the
loud dead-proxy log.

## Impact

- Healthy-proxy behavior unchanged (counter resets on every proxied response).
- Crawls with a dead/misconfigured proxy now self-heal in seconds-to-minutes
  instead of wedging for hours; sites that serve fine direct crawl fully.
- New stats: `proxy/transport_failure`, `proxy/declared_dead`.
- Workaround before this change was manual: `--proxy-type none` per crawl.

## Possible follow-up (not in this change)

Domain blocking is still triggered by a single 403 (`blocked_domains.add` on
first block). A threshold (e.g. 3 blocks in a window) would avoid escalating a
whole domain over one hard-403 legal page even when the proxy is healthy.
