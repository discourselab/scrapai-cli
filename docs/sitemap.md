# Sitemap Spider

Agent must explicitly set `"USE_SITEMAP": true` — no auto-detection.

## Workflow

### Step 1: Inspect Sitemap

```bash
./scrapai inspect https://example.com/sitemap.xml --project proj
```

**Regular sitemap:** Contains article URLs directly.
**Sitemap index:** References sub-sitemaps. Inspect each sub-sitemap to identify which contain articles vs static pages.

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

If generic extractors work → `EXTRACTOR_ORDER: ["newspaper", "trafilatura"]`
If they fail → discover custom selectors (see [extractors.md](extractors.md))

### Step 3: Create Spider JSON

```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap.xml"],
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

**With custom selectors:**
```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/post-sitemap.xml"],
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["custom", "newspaper"],
    "CUSTOM_SELECTORS": {
      "title": "h1.article-title",
      "content": "div.article-body",
      "author": "span.author-name",
      "date": "time.publish-date"
    }
  }
}
```

Can use main sitemap URL or specific sub-sitemap URL. Sitemap spiders don't need rules.

### Step 4: Test & Deploy

```bash
./scrapai spiders import spider.json --project proj
./scrapai crawl example_sitemap --limit 5 --project proj
./scrapai show example_sitemap --limit 5 --project proj
```

If good → production. If bad → go back to Step 2.

## Combining with Other Features

**Sitemap + Cloudflare:**
```json
{ "USE_SITEMAP": true, "CLOUDFLARE_ENABLED": true, "CLOUDFLARE_STRATEGY": "hybrid" }
```

**Sitemap + DeltaFetch:**
```json
{ "USE_SITEMAP": true, "DELTAFETCH_ENABLED": true }
```

**Sitemap + Custom Extractors:**
```json
{ "USE_SITEMAP": true, "EXTRACTOR_ORDER": ["custom", "newspaper"], "CUSTOM_SELECTORS": { ... } }
```

## Common Sitemap Locations

- `https://example.com/sitemap.xml`
- `https://example.com/sitemap_index.xml`
- `https://example.com/post-sitemap.xml`
- Check `https://example.com/robots.txt` for `Sitemap:` directive

## Nested Sitemap Analysis

When sitemap index detected, inspect each sub-sitemap individually. Categorize which contain articles (extract) vs static pages (will fail extraction — this is expected and normal). Report URL counts and sample patterns to user before creating spider.

Non-article URLs failing extraction is expected. Only article URLs need to extract successfully.

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
