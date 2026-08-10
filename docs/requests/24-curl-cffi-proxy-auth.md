# 24 — curl_cffi handler: proxy credentials dropped (407) and leaked to origin

**Requested by:** Ranu (2026-08-05)
**Type:** bugfix (transport defect — not a feature request)
**Status:** implemented locally (`handlers/curl_cffi_handler.py`), candidate for
upstream PR

## Problem

**`CURL_CFFI_ENABLED: true` and an authenticating proxy cannot be used together
— every request fails 407.** The two settings are individually documented and
individually work; the combination has never worked.

The handoff between three components drops the credentials:

1. `SmartProxyMiddleware` sets `request.meta['proxy']` to the full credentialed
   URL built by `core/proxy.url_for()` (`http://user:pass@host:port`).
2. Scrapy's built-in `HttpProxyMiddleware` then **strips** those credentials out
   of `meta['proxy']` and moves them into a `Proxy-Authorization` header — the
   contract its own downloader honours.
3. `proxies_from_request()` reads `meta['proxy']` only — now credential-free —
   and hands it to curl_cffi, which authenticates from the URL and ignores that
   header. The proxy answers `407 Proxy Authentication Required`.

`inspect` is unaffected because it calls `_fetch_curl_cffi(url, proxy_url)`
directly with the credentialed URL, never entering Scrapy's middleware chain —
so the same site "works in inspect, fails in crawl", which is what makes this
expensive to diagnose.

Observed in production (2026-08-04) on a site that 403s plain HTTP from the
server IP *and* 403s curl_cffi without a proxy — only residential + curl_cffi
succeeds, i.e. exactly the broken combination. The crawl enqueued 486 URLs and
scraped **0 items**, with the crawl-time robots.txt and llms.txt compliance
witnesses also failing:

```
curl_cffi.requests.exceptions.ProxyError: CONNECT tunnel failed, response 407
[compliance] robots.txt: fetch failed (ProxyError ... 407) — not saved
```

**Second defect, same code path:** the handler builds its outgoing header dict
from `request.headers`, which still contains `Proxy-Authorization`. Those
credentials were therefore sent to **every origin server** on curl_cffi crawls.
They belong to the CONNECT tunnel, not the target site.

## Change (`handlers/curl_cffi_handler.py`)

1. **Re-attach credentials** (`proxies_from_request`): when `meta['proxy']`
   carries no credentials but a `Proxy-Authorization` header is present, decode
   the Basic payload and put the credentials back into the URL before handing it
   to curl_cffi. Guarded on `"@" not in proxy`, so a proxy URL that still has its
   credentials (no `HttpProxyMiddleware` in the chain) is left untouched.
2. **Stop leaking them** (`_fetch_sync`): drop `Proxy-Authorization` from the
   headers sent to the origin server.

16 lines, one file. No new settings, no behaviour change when no proxy is in
use (`meta['proxy']` absent → `None`, as before).

## Impact

- `CURL_CFFI_ENABLED` + proxy crawls work. Verified on the affected site: 407
  count 0, robots.txt captured, items extracting, 403 rate 26% (was 42%).
- Proxy credentials are no longer disclosed to crawled sites.
- Affects any spider that combines the two settings; a spider setting
  `CURL_CFFI_ENABLED` without a proxy was never affected.
