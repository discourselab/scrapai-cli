# Sitemap Spider

Agent must explicitly set `"USE_SITEMAP": true` — no auto-detection.

> **A sitemap is a URL source, not a substitute for analysis.** It changes only how URLs are *enumerated* — it tells you nothing about the site's sections, content types, or selectors. Even when you use a sitemap, still run the **full Phase 1 structure mapping** (homepage + each section `inspect --project <p> --screenshot`, read the `page.png`, record every section in `sections.md`) and **Phase 2 selector discovery on real content pages**. Do NOT jump straight to sitemap mode and skip inspection — the sitemap is a poor place to understand patterns. The steps below cover only the sitemap-specific URL enumeration and filtering; they assume that analysis is done.

## Workflow

### Step 1: Inspect Sitemap

```bash
./scrapai inspect https://example.com/sitemap.xml --project proj
```

**Regular sitemap:** Contains article URLs directly.
**Sitemap index:** References sub-sitemaps. Inspect each sub-sitemap to map what each one holds (articles, plus peripheral content pages like about/contact). Collect every sub-sitemap that holds content — only leave out infinite non-content traps.

```bash
./scrapai inspect https://example.com/post-sitemap.xml --project proj
./scrapai inspect https://example.com/page-sitemap.xml --project proj
```

### Step 2: Test Extraction

Pick 2-3 article URLs from sitemap:
```bash
./scrapai inspect https://example.com/article-1 --project proj
./scrapai inspect https://example.com/article-2 --project proj
```

If generic extractors work (core schema: title/content/author/published_date) → `EXTRACTOR_ORDER: ["trafilatura", "newspaper"]`
If the schema has any non-core field, or generic extraction is wrong → pure-CSS mode: `EXTRACTOR_ORDER: ["custom"]` + one `FIELDS` directive per field (see [extractors.md](extractors.md))

### Step 3: Create Spider JSON

**Recommended — a `sections` config with `USE_SITEMAP`.** Author the spider exactly as you would without a sitemap (one `section` per content type), and just add `"USE_SITEMAP": true` to `settings`. The sitemap enumerates the URLs; your sections do the extraction — so you keep the generic article reader *and* custom fields while getting sitemap completeness. (No follow-only navigation sections are needed in sitemap mode; the sitemap provides the URLs directly.)

```json
{
  "name": "example_sitemap",
  "source_url": "https://example.com",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap.xml"],
  "settings": { "USE_SITEMAP": true },
  "sections": [
    { "match": ["/blog/.*"], "extract": "auto" },
    { "match": ["/report/.*"], "extract": { "title": "auto", "pdf_url": { "css": "a.download::attr(href)" } } }
  ]
}
```

**Legacy form** (still supported — what `sections` compiles to):

```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap.xml"],
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["trafilatura", "newspaper"]
  }
}
```

**With `FIELDS` (pure-CSS mode):**
```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/post-sitemap.xml"],
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["custom"],
    "FIELDS": {
      "title": {"css": "h1.article-title::text"},
      "content": {"css": "div.article-body", "to_text": true},
      "author": {"css": "span.author-name::text"},
      "published_date": {"css": "time.publish-date::attr(datetime)"}
    }
  }
}
```

Use `EXTRACTOR_ORDER: ["custom"]` whenever the project schema declares any non-core field, and give every schema field its own `FIELDS` directive. Import **rejects** mixing generic extractors (`trafilatura`/`newspaper`) with a non-core schema — `["custom", "trafilatura", "newspaper"]` alongside non-core fields will fail validation.

Can use main sitemap URL or specific sub-sitemap URL.

**Sitemap with callbacks:** When rules with callbacks are defined, sitemap URLs are routed to the callback instead of `parse_article`. This enables custom field extraction (e.g., video metadata, comments) on sitemap-discovered pages.

```json
{
  "name": "example_sitemap",
  "start_urls": ["https://example.com/post-sitemap.xml"],
  "settings": {"USE_SITEMAP": true},
  "rules": [{"allow": [".*"], "callback": "parse_post"}],
  "callbacks": {
    "parse_post": {
      "extract": {
        "title": {"css": "h1::text"},
        "video_url": {"css": "source::attr(src)"}
      }
    }
  }
}
```

### Step 4: Test & Deploy

```bash
./scrapai spiders import spider.json --project proj
./scrapai crawl example_sitemap --limit 5 --project proj
./scrapai show example_sitemap --limit 5 --project proj
```

If good → production. If bad → go back to Step 2.

## Date Filtering with `SITEMAP_SINCE`

Filter sitemap entries by their `<lastmod>` date to only crawl recent content. This saves time when you only need articles from a specific time period.

**Relative dates:**
```json
{
  "USE_SITEMAP": true,
  "SITEMAP_SINCE": "2y",
  "EXTRACTOR_ORDER": ["trafilatura", "newspaper"]
}
```

Supported relative formats:
- `"2y"` — last 2 years
- `"6m"` — last 6 months
- `"30d"` — last 30 days

**Absolute dates:**
```json
{
  "USE_SITEMAP": true,
  "SITEMAP_SINCE": "2024-01-01",
  "EXTRACTOR_ORDER": ["trafilatura", "newspaper"]
}
```

**Behavior:**
- Entries with `lastmod` before the cutoff date are skipped
- Entries **without** `lastmod` are always included (safe default — better to crawl extra than miss content)
- Log output shows how many entries were filtered vs scheduled
- Works with all other settings (Cloudflare, DeltaFetch, `FIELDS`, etc.)

## PDFs in sitemaps

By default PDFs are **collected**, not skipped. With `PDF_MODE: "links_only"` (the default), any `.pdf` URLs in the sitemap are recorded as URL-only items — no download. Set `PDF_MODE: "extract"` to follow each PDF, download it, and extract its text (born-digital only; scanned/image PDFs stay URL-only). Only add a `deny` pattern if you genuinely want to drop them.

## Excluding URLs with `deny`

Sitemap spiders honor `deny` patterns on rules, the same way rule-based crawls do. Use this to drop any URL pattern you don't want sent to the parser (e.g. a `/tag/` index, or PDFs if you don't want them collected at all).

```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap.xml"],
  "settings": { "USE_SITEMAP": true, "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] },
  "rules": [
    { "allow": ["/article/.*"], "deny": ["/tag/"] }
  ]
}
```

**Behavior:**
- `deny` patterns are collected from **all** rules (allow+deny or deny-only) and matched against each sitemap URL before a request is built.
- A deny-only rule (no `allow`) still applies — denied URLs are dropped, everything else is crawled.
- Matching runs on the **absolute** URL, so it works even when the sitemap uses relative `<loc>` values (see below).
- Log output shows how many entries were dropped by deny patterns.
- Invalid regex patterns are logged and skipped, not fatal.

## Relative `<loc>` URLs

Some sitemaps use non-conformant root-relative (`<loc>/blog/post-1</loc>`) or protocol-relative (`<loc>//cdn.example.com/x</loc>`) URLs. These are automatically resolved to absolute URLs (against `https://<first allowed_domain>/`) before requests are built. Without this, a single relative `<loc>` would abort iteration of the rest of the sitemap and silently drop every URL after it. Each rewrite is logged.

> Note: resolution uses the first entry in `allowed_domains` as the base, which is correct for root/protocol-relative locs. Path-relative locs on multi-subdomain sitemaps may not resolve exactly — keep `allowed_domains` accurate.

## Combining with Other Features

**Sitemap + Cloudflare:**
```json
{ "USE_SITEMAP": true, "CLOUDFLARE_ENABLED": true, "CLOUDFLARE_STRATEGY": "hybrid" }
```

**Sitemap + DeltaFetch:**
```json
{ "USE_SITEMAP": true, "DELTAFETCH_ENABLED": true }
```

**Sitemap + Custom Extractors (pure-CSS):**
```json
{ "USE_SITEMAP": true, "EXTRACTOR_ORDER": ["custom"], "FIELDS": { "title": {"css": "h1::text"} } }
```

## Common Sitemap Locations

- `https://example.com/sitemap.xml`
- `https://example.com/sitemap_index.xml`
- `https://example.com/post-sitemap.xml`
- Check `https://example.com/robots.txt` for `Sitemap:` directive

## Nested Sitemap Analysis

When sitemap index detected, inspect each sub-sitemap individually. Categorize what each one holds (articles, plus peripheral content pages like about/contact — include those where they hold content). Report URL counts and sample patterns to user before creating spider.

Collect every sub-sitemap that holds content; only leave out infinite non-content traps. A peripheral page that extracts thinly is fine — it's intentionally included where it carries content, and unwanted items are dropped later in post-processing.

## Troubleshooting

**"No URLs extracted from sitemap":**
- Verify sitemap URL is accessible (inspect it first)
- Verify it's valid XML
- Check `allowed_domains` includes the sitemap's domain

**"Sitemap not detected":**
- Ensure `"USE_SITEMAP": true` is in settings
- URL should contain a sitemap pattern (sitemap.xml, post-sitemap.xml, etc.)

**"Too slow":**
- Do NOT set `CONCURRENT_REQUESTS: 1` for sitemap spiders
- Default 16 concurrent is correct
- Add `DELTAFETCH_ENABLED: true` for subsequent runs
