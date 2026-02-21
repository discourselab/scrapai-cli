# Sitemap Spider

Automatically crawl websites using sitemap.xml files. When you provide a sitemap URL, ScrapAI automatically detects it and uses Scrapy's optimized SitemapSpider.

## How It Works

1. **Auto-detection**: When you add a URL ending in `sitemap.xml` or similar patterns
2. **Automatic spider selection**: Uses `SitemapDatabaseSpider` instead of regular `DatabaseSpider`
3. **URL extraction**: Automatically extracts all URLs from the sitemap
4. **Content scraping**: Scrapes each URL with same extraction logic as regular spiders

## Supported Sitemap Formats

**Auto-detected patterns:**
- `sitemap.xml`
- `sitemap_index.xml` or `sitemap-index.xml`
- `post-sitemap.xml`, `page-sitemap.xml`
- `sitemap1.xml`, `sitemap2.xml`, etc.
- URLs containing `/sitemap/`
- `sitemaps.xml`

## Usage

### Method 1: Direct Spider Creation

**Create spider with sitemap URL:**
```json
{
  "name": "example_sitemap",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap.xml"],
  "rules": [
    {
      "allow": ["/articles/"],
      "callback": "parse_article",
      "follow": false
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

**Import:**
```bash
./scrapai spiders import sitemap_spider.json --project news
```

**Run:**
```bash
./scrapai crawl example_sitemap --project news
```

**Output:**
```
🗺️  Sitemap detected - using sitemap spider
🚀 Running DB spider: example_sitemap
```

### Method 2: Via Queue

**Add sitemap URL to queue:**
```bash
./scrapai queue add https://example.com/sitemap.xml --project news
```

**Process queue:**
When the agent processes this URL, it will:
1. Detect it's a sitemap
2. Create a sitemap spider automatically
3. Extract all URLs from sitemap
4. Scrape each URL

## Sitemap Rules

Rules work slightly differently with sitemap spiders:

**Regular spider rules:**
- `allow` patterns determine which links to **follow** from scraped pages
- `follow: true` means "follow links on this page"

**Sitemap spider rules:**
- `allow` patterns filter which URLs from the **sitemap** to scrape
- All URLs matching `allow` patterns are scraped directly
- `follow` is ignored (sitemap already contains all URLs)

### Example: Filter Sitemap URLs

**Only scrape blog posts from sitemap:**
```json
{
  "rules": [
    {
      "allow": ["/blog/[0-9]{4}/"],
      "callback": "parse_article"
    }
  ]
}
```

This will only scrape URLs like:
- `https://example.com/blog/2024/article-1`
- `https://example.com/blog/2023/article-2`

And skip URLs like:
- `https://example.com/about`
- `https://example.com/contact`

**Scrape all URLs from sitemap (default):**
```json
{
  "rules": [
    {
      "allow": ["/"],
      "callback": "parse_article"
    }
  ]
}
```

## Sitemap Index Support

**Sitemap indexes** (sitemaps that reference other sitemaps) are supported automatically.

**Example sitemap_index.xml:**
```xml
<sitemapindex>
  <sitemap>
    <loc>https://example.com/post-sitemap.xml</loc>
  </sitemap>
  <sitemap>
    <loc>https://example.com/page-sitemap.xml</loc>
  </sitemap>
</sitemapindex>
```

Scrapy will automatically:
1. Fetch sitemap_index.xml
2. Find all referenced sitemaps
3. Fetch each sitemap
4. Extract and scrape all URLs

## Common Sitemap Locations

If site doesn't advertise their sitemap, try these common locations:
- `https://example.com/sitemap.xml`
- `https://example.com/sitemap_index.xml`
- `https://example.com/post-sitemap.xml`
- `https://example.com/sitemap1.xml`
- Check `https://example.com/robots.txt` for `Sitemap:` directive

## Advantages Over Regular Crawl

**Sitemap spider benefits:**
1. **Faster**: No need to crawl navigation pages
2. **Complete**: Get all URLs immediately from sitemap
3. **Reliable**: No broken links, pagination issues, or navigation bugs
4. **Efficient**: Only scrape content pages, skip navigation

**When to use sitemap:**
- Site has a sitemap.xml file
- You want to scrape all content pages
- Site has complex navigation
- You want fastest possible crawl

**When to use regular crawl:**
- No sitemap available
- Need to follow specific navigation paths
- Need to scrape pages not in sitemap
- Need to respect site's crawl rate limits via pagination

## Example Configurations

### News Site with Sitemap

```json
{
  "name": "news_site",
  "allowed_domains": ["news.example.com"],
  "start_urls": ["https://news.example.com/post-sitemap.xml"],
  "rules": [
    {
      "allow": ["/[0-9]{4}/[0-9]{2}/"],
      "callback": "parse_article"
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

### Blog with Sitemap Index

```json
{
  "name": "blog_sitemap",
  "allowed_domains": ["blog.example.com"],
  "start_urls": ["https://blog.example.com/sitemap_index.xml"],
  "rules": [
    {
      "allow": ["/"],
      "callback": "parse_article"
    }
  ]
}
```

### E-commerce Product Sitemap

```json
{
  "name": "products",
  "allowed_domains": ["shop.example.com"],
  "start_urls": ["https://shop.example.com/product-sitemap.xml"],
  "rules": [
    {
      "allow": ["/products/"],
      "deny": ["/products/category/"],
      "callback": "parse_article"
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["custom"],
    "CUSTOM_SELECTORS": {
      "title": "h1.product-name",
      "content": "div.product-description",
      "price": "span.price::text"
    }
  }
}
```

## Combining with Other Features

### Sitemap + Cloudflare

```json
{
  "start_urls": ["https://protected-site.com/sitemap.xml"],
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid"
  }
}
```

### Sitemap + DeltaFetch

Perfect for monitoring sites:
```json
{
  "start_urls": ["https://news.com/sitemap.xml"],
  "settings": {
    "DELTAFETCH_ENABLED": true
  }
}
```

**First run**: Scrapes all URLs from sitemap
**Subsequent runs**: Only re-scrapes changed articles

### Sitemap + Custom Extractors

```json
{
  "start_urls": ["https://site.com/sitemap.xml"],
  "settings": {
    "EXTRACTOR_ORDER": ["custom", "newspaper"],
    "CUSTOM_SELECTORS": {
      "title": "h1.article-title",
      "content": "div.article-body"
    }
  }
}
```

## Troubleshooting

**"No URLs extracted from sitemap"**
- Check sitemap URL is accessible: `curl https://example.com/sitemap.xml`
- Verify sitemap format is valid XML
- Check allowed_domains includes sitemap domain

**"Sitemap not detected"**
- URL must contain `sitemap.xml` or similar pattern
- Check start_urls: `["https://example.com/sitemap.xml"]`

**"Scraping wrong pages"**
- Check rules `allow` patterns
- Add `deny` patterns to exclude unwanted URLs

**"Too slow"**
- Remove `CONCURRENT_REQUESTS: 1` if present
- Default (16 concurrent requests) works great with sitemaps
- Consider using DeltaFetch for subsequent runs

## Performance

**Typical performance:**
- 1000 URLs in sitemap
- 16 concurrent requests
- ~2 seconds per page
- **Total time: ~2-3 minutes**

**Compare to regular crawl:**
- Navigate through index pages
- Follow pagination links
- Extract article links
- **Could take 10-20 minutes for same 1000 pages**

**Sitemap spider is typically 5-10x faster for large sites.**
