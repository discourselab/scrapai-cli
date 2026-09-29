# Change request: one site's failed verify must not close the shared browser

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-09-29)
- **File:** `utils/cf_browser.py` — `CloudflareBrowserClient(shared=)`, `_ensure_page`, `_escalate`, `_proxy_label`, `attach_lane`; `utils/browser_service.py` — `_run`; `handlers/cloudflare_handler.py` — `_SITE_NET_ERRORS`
- **Type:** framework change (reliability defect)
- **Requested by:** @MirjamOdile
- **Docs made wrong:** `docs/browser-service.md` (the "Caveat" section and the `--proxy-type` line), corrected here.

## Problem

The browser service runs one browser; each site is a tab (a "lane"). Lane 0 is the parent client and every other lane is made by `attach_lane()`, which hands it the parent's `browser` and `context`.

When a lane's Cloudflare verify failed, `fetch()` called `_escalate()`, which closes the client's browser and launches a new one through the next proxy in the chain. On a lane that browser is the shared one. Every other tab died, the pool kept handing out lanes bound to the dead browser, and every request answered "Target page, context or browser has been closed" until the service was restarted. `browser status` still said Running, because `ping` never touches a lane. The parent escalating did the same.

`verify_cloudflare` returns False for any navigation error, so a dead host was enough: in the local service log a dead short-link host (`net::ERR_NAME_NOT_RESOLVED`) closed the browser, and every browser crawl on the machine failed for about 20 hours.

Two more routes reached the same place. `verify_cloudflare` and `_fetch_via_browser_request` call `start()` when the client has no page; the pool clears a lane's page when it evicts the lane, and eviction can happen while a request is still using it. On a lane that launched a private browser nobody ever closed; on the parent it replaced the browser under every other tab.

The escalation itself did not work: both proxied retries in that log failed at once with `net::ERR_INVALID_AUTH_CREDENTIALS`, while the same proxies answer through curl. And the log lines for it wrote the proxy URLs, credentials included.

## Change

- `CloudflareBrowserClient(shared=True)` marks a client whose browser other clients use. The service's parent is built with it; `attach_lane()` sets it on every lane.
- `_escalate()` on a shared client logs and returns False without touching the browser or the chain, so only that request fails. The next request for the site verifies again on the same tab.
- `_ensure_page()` replaces the two `if not self.page: await self.start()` calls. A shared client never launches: no page means the pool closed the lane, and the request fails with "navigation error: browser lane was closed"; a crashed tab is reopened in the same context. Unshared clients behave as before.
- `parent.close()` at shutdown still closes the browser: `shared` guards escalation and relaunch, not ownership.
- Proxy URLs in log lines go through `_proxy_label()` (scheme, host, port; no credentials).
- `_SITE_NET_ERRORS` gains `net::ERR_NAME_RESOLUTION_FAILED`, so that DNS failure is reported as the site's doing and not counted toward the request-17 wedge stop.

## Trade-offs

- The service no longer switches proxy per site. With `--proxy-type auto` it runs direct, as `none` does; a site that needs a proxy needs the service started with that proxy named (`--proxy-type residential`). Crawls' HTTP requests keep their own proxy handling (`SmartProxyMiddleware`, the Cloudflare handler's proxied HTTP fetch); only the browser verify is affected.
- Rejected for now: escalating through a per-lane context with its own proxy (`browser.new_context(proxy=...)`). It keeps proxy fallback without touching other tabs, but the browser's proxy authentication failure has to be understood first, and a context-level proxy loses CloakBrowser's launch-time `geoip` matching.
- Rejected: skipping escalation for errors a proxy cannot fix (DNS, certificate). With the service no longer escalating, only a standalone `inspect` without the service would benefit.

## Known gaps

- `LanePool` can still evict a lane a request is using; that request now fails cleanly instead of wedging the service. Counting users per lane would prevent it.
- If the shared browser dies for another reason (a crash, out of memory), the service does not restart it.

## Verification

- `tests/unit/test_shared_browser_escalation.py` (8, fake browser whose pages and contexts really go closed): a lane's or the parent's failed verify leaves the browser open and a new lane works; through `handle_request` and a real `LanePool`, a dead host fails, another site then succeeds, the dead host fails again without closing anything; a lane closed mid-request fails without launching; a crashed tab is reopened; an unshared client still escalates; shutdown still closes the browser; no proxy credentials in the log. 6 of the 8 fail on the code before this change.
- `tests/unit/test_verify_failure_reason.py`: two new `_site_refused` cases.
