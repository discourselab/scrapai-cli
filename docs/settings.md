# Spider Settings Reference

Settings go into the spider JSON. Project defaults in `settings.py` are conservative; every new spider JSON should explicitly override throughput unless the site actively rate-limits.

## Throughput (include in every new spider JSON)

```json
{
  "DOWNLOAD_DELAY": 0,
  "CONCURRENT_REQUESTS": 32,
  "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
  "AUTOTHROTTLE_ENABLED": false
}
```

## Extractor order

```json
{ "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] }
```

See [extractors.md](extractors.md) for the directive-driven options (`["custom"]` + `FIELD_EXTRACT`).

## Pagination via `<link rel="next">`

```json
{ "allow": ["/page/\\d+/"], "tags": ["a", "area", "link"], "follow": true }
```
Scrapy's LinkExtractor by default only scans `<a>` and `<area>` tags. Many WordPress/Yoast sites expose pagination via `<link rel="next">` in `<head>`. Omit for normal sites.

## Browser mode (JS + Cloudflare)

See [cloudflare.md](cloudflare.md) for the full guide. `--browser` flag triggers hybrid mode automatically (browser once, then HTTP with cookies).

**Cloudflare-protected sites:**
```json
{ "CLOUDFLARE_ENABLED": true }
```

**JS-rendered sites (no Cloudflare):**
```json
{ "BROWSER_ENABLED": true }
```

Both flip on CloakBrowser — use the one that documents intent.

**Proxy type for CF bypass (geo-blocked):**
```json
{ "CLOUDFLARE_ENABLED": true, "PROXY_TYPE": "residential" }
```
Values: `"auto"` (default, escalates direct → dc → residential), `"residential"`, `"datacenter"`.

**Advanced (if hybrid fails — rare):**
```json
{
  "CLOUDFLARE_ENABLED": true,
  "CLOUDFLARE_STRATEGY": "browser_only",
  "CONCURRENT_REQUESTS": 1
}
```

## curl_cffi (TLS fingerprint impersonation)

Use when a site blocks Scrapy/Twisted at the TLS level (e.g. 403/empty despite normal headers) but doesn't need JS rendering. Try this before reaching for `CLOUDFLARE_ENABLED` — lighter, faster, no browser.

```json
{
  "CURL_CFFI_ENABLED": true,
  "EXTRACTOR_ORDER": ["trafilatura", "newspaper"]
}
```

Optional:
```json
{
  "CURL_CFFI_IMPERSONATE": "chrome",
  "CURL_CFFI_TIMEOUT": 30
}
```

## Sitemap spider

See [sitemap.md](sitemap.md). Basic:
```json
{ "USE_SITEMAP": true, "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] }
```

**With callbacks** — rules with `callback` route URLs to named callbacks instead of `parse_article`:
```json
{
  "USE_SITEMAP": true,
  "rules": [{"allow": [".*"], "callback": "parse_post"}],
  "callbacks": {"parse_post": {"extract": {...}}}
}
```

**With date filtering:**
```json
{ "USE_SITEMAP": true, "SITEMAP_SINCE": "2y", "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] }
```
`SITEMAP_SINCE` supports relative (`"2y"`, `"6m"`, `"30d"`) and absolute (`"2024-01-01"`) dates. Entries without `lastmod` are always included.

## DeltaFetch (incremental crawling)

See [deltafetch.md](deltafetch.md). Enabled by default — subsequent crawls skip already-seen URLs.

```json
{ "DELTAFETCH_ENABLED": false }
```

Clear cache and re-crawl:
```bash
./scrapai crawl spider --project proj --reset-deltafetch
```

## Infinite scroll

```json
{ "INFINITE_SCROLL": true, "MAX_SCROLLS": 5, "SCROLL_DELAY": 1.0 }
```

## Paginated listings (JS click-through)

For listing pages whose "Next" button is JS-driven (no URL change, no `<link rel=next>`, article URLs aren't discoverable via LinkExtractor on a single page load). The spider opens the listing in a browser at crawl start, clicks Next through all pages, collects article hrefs, and yields a request for each one into the regular `parse_article` pipeline.

```json
{
  "PAGINATED_LISTINGS": [
    {
      "url": "https://example.com/blog/",
      "link_selector": "a.article-card-link",
      "next_selector": "a.next.page-numbers",
      "wait_selector": "div.article-card",
      "max_pages": 200,
      "click_delay": 1.5
    }
  ]
}
```

- `url` — listing page to paginate
- `link_selector` — CSS for article links inside each rendered page
- `next_selector` — CSS for the Next button (click target)
- `wait_selector` — optional; waited for after each click before collecting
- `max_pages` — safety cap (default 100)
- `click_delay` — seconds after each click before reading URLs (default 1.5)

**When to use:** listing pages with hash/JS pagination (`href="#"`) and no URL-based fallback. For sites that support `?paged=N` or expose `<link rel="next">`, use the standard `tags` rule instead — lighter and faster than spinning up a browser.
