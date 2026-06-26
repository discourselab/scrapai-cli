# Spider Settings Reference

Settings go into the spider JSON. Project defaults in `settings.py` are conservative; every new spider JSON should explicitly override throughput unless the site actively rate-limits.

## Authoring format: `sections` (recommended)

Write a spider as a top-level `sections` list — one section per kind of page. Each section says *which URLs to match* and *how to extract them*. At import, `sections` is desugared into the classic `rules` + `callbacks` + `settings.FIELDS` shape (see `core/sections.py:expand_sections`), so the runtime is unchanged — `sections` is purely the authoring surface. The old format still imports and runs identically (documented below under [Legacy format](#legacy-format-rules--callbacks--fields)); `sections` is what it compiles to.

A section:

```json
{
  "match": ["/articles/.*"],
  "extract": { "title": "auto", "content": "auto", "author": "auto", "published_date": "auto" },
  "follow": true,
  "priority": 100
}
```

Section keys:
- `match` — list of URL regex patterns. Absent means match all.
- `extract` — exactly one of:
  - **absent** → follow-only navigation (no extraction; just discover links).
  - **`"auto"`** → the built-in article reader (fills `title`, `content`, `author`, `published_date`).
  - **a per-field dict** `{ field: value }`, where each value is either:
    - `"auto"` — valid **only** for the four core fields (`title`, `content`, `author`, `published_date`).
    - a directive `{ "css" | "xpath": "...", "get_all"?, "to_text"?, "to_markdown"?, "processors"? }`.
- `follow` — whether to follow matched links (default `true`).
- `priority` — optional int, 0-1000 (higher rule wins when several match).
- `deny`, `restrict_xpaths`, `restrict_css`, `tags` — optional per-rule LinkExtractor knobs, passed straight through.

**One repeating concept: one section per kind of page.** `extract: "auto"` is article-only; non-article pages (products, jobs, listings) need one selector per field.

**Mixing `"auto"` with an override.** A section may set core fields to `"auto"` and override just one or two with a selector — useful when the article reader guesses `author`/`published_date` wrong:

```json
{ "match": ["/articles/.*"],
  "extract": { "title": "auto", "content": "auto", "author": { "css": ".byline a::text" } } }
```

Constraint: at most **one** section per spider may mix `"auto"` with selector overrides. That override compiles to a single spider-wide `FIELDS` dict, so it is global. Other sections must give explicit selectors for every field.

**Validation at import:**
- `"auto"` on a non-core field is rejected — give it a selector.
- Every `required: true` field in the project schema must be sourced by some section.

### Canonical example

```json
{
  "sections": [
    { "match": ["/articles/.*"], "extract": { "title": "auto", "content": "auto", "author": { "css": ".byline a::text" } } },
    { "match": ["/products/.*"], "extract": { "name": { "css": "h1::text" }, "price": { "css": ".price::text" } } },
    { "match": [".*"], "follow": true }
  ]
}
```

The first section reads articles (with an `author` override), the second extracts products field-by-field, and the third is follow-only navigation that crawls everything else to discover links.

### Settings still live at the top level (NOT per-section)

`sections` covers URL matching and extraction. Everything else — transport, throughput, PDF handling, DeltaFetch, sitemap — stays in a top-level `settings` block, exactly as below. These are spider-wide and have no per-section form:

```json
{
  "sections": [ ... ],
  "settings": {
    "CONCURRENT_REQUESTS": 32,
    "CURL_CFFI_ENABLED": true,
    "PDF_MODE": "links_only"
  }
}
```

### Still authored the legacy way (not yet in `sections`)

A few capabilities are not expressible as sections yet — author these with the legacy `rules` + `callbacks` + `settings` format (below):
- Listing → detail (`iterate`)
- AJAX nested lists (`ajax_nested_list`)
- JS click-through pagination (`PAGINATED_LISTINGS`)

Sitemap mode is **not** on this list — `"USE_SITEMAP": true` works in a `sections` config (it just enumerates URLs; your sections still extract).

---

## Throughput (include in every new spider JSON)

```json
{
  "DOWNLOAD_DELAY": 0,
  "CONCURRENT_REQUESTS": 32,
  "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
  "AUTOTHROTTLE_ENABLED": false
}
```

## Legacy format (rules + callbacks + FIELDS)

The format below is still fully supported — it is exactly what `sections` compiles to. Prefer `sections` for new spiders (above); reach for the legacy format directly only for the deferred cases (`iterate`, `ajax_nested_list`, `PAGINATED_LISTINGS`) or when editing existing legacy spiders.

With `sections`, `EXTRACTOR_ORDER` and `FIELDS` are usually no longer hand-written — `extract: "auto"` selects the article reader and per-field directives generate `FIELDS` for you. The settings below still apply to legacy configs and to the deferred cases.

## Extractor order

```json
{ "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] }
```

See [extractors.md](extractors.md) for the directive-driven options (`["custom"]` + `FIELDS`). Authoring with `sections`? You normally don't set this by hand — a section's `extract` chooses the path.

## Pagination via `<link rel="next">`

```json
{ "allow": ["/page/\\d+/"], "tags": ["a", "area", "link"], "follow": true }
```
Scrapy's LinkExtractor by default only scans `<a>` and `<area>` tags. Many WordPress/Yoast sites expose pagination via `<link rel="next">` in `<head>`. Omit for normal sites.

In `sections`, set `tags` on the section instead: `{ "match": ["/page/\\d+/"], "tags": ["a", "area", "link"], "follow": true }`.

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
Values: `"auto"` (default, escalates direct → dc → residential), `"none"` to disable proxying, or **any proxy name configured in `.env`** — `"datacenter"`, `"residential"`, plus any extra tiers you've added (`"isp"`, `"mobile"`, `"residential_us"`, …). An unknown name (no matching `<NAME>_PROXY_URL`/`<NAME>_PROXY_*` in `.env`) errors out.

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

Sitemap mode works with **either** format: add `"USE_SITEMAP": true` to a `sections` config's `settings` (recommended), or to a legacy `rules` + `callbacks` config. The sitemap enumerates URLs; your sections/rules still do the extraction. See [sitemap.md](sitemap.md). Basic (legacy form shown):
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

## PDFs (`PDF_MODE`)

Controls what happens when the crawl encounters a `.pdf` link. Default is `links_only`.

```json
{ "PDF_MODE": "links_only" }
```
`links_only` (default) records each linked PDF URL as a URL-only item (title from the filename, empty content, `metadata_json.content_type = "pdf"`) without downloading the file.

```json
{ "PDF_MODE": "extract" }
```
`extract` follows each `.pdf` link, downloads it, and extracts its text via `pypdfium2`. Born-digital PDFs only — there is no OCR, so a scanned/image-only PDF (no text layer) gracefully falls back to a URL-only item with empty content, as do unparseable bytes or a missing `pypdfium2`.

## Infinite scroll

```json
{ "INFINITE_SCROLL": true, "MAX_SCROLLS": 5, "SCROLL_DELAY": 1.0 }
```

## Paginated listings (JS click-through)

`PAGINATED_LISTINGS` is a deferred case — keep it in the top-level `settings` block, not `sections`. For listing pages whose "Next" button is JS-driven (no URL change, no `<link rel=next>`, article URLs aren't discoverable via LinkExtractor on a single page load). The spider opens the listing in a browser at crawl start, clicks Next through all pages, collects article hrefs, and yields a request for each one into the regular `parse_article` pipeline.

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
