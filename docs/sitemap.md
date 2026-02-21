# Sitemap Spider

Automatically crawl websites using sitemap.xml files. When you provide a sitemap URL, ScrapAI automatically detects it and uses Scrapy's optimized SitemapSpider.

## Complete Sitemap Workflow

### Step 1: Fetch and Analyze Sitemap

**Inspect the sitemap:**
```bash
./scrapai inspect https://example.com/sitemap.xml --project myproject
```

**Two types of sitemaps:**

**Type A: Regular Sitemap (contains URLs directly)**
```xml
<urlset>
  <url><loc>https://example.com/article-1</loc></url>
  <url><loc>https://example.com/article-2</loc></url>
  <url><loc>https://example.com/about</loc></url>
</urlset>
```

**Type B: Sitemap Index (references other sitemaps)**
```xml
<sitemapindex>
  <sitemap><loc>https://example.com/post-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/page-sitemap.xml</loc></sitemap>
  <sitemap><loc>https://example.com/category-sitemap.xml</loc></sitemap>
</sitemapindex>
```

### Handling Nested Sitemaps (Sitemap Index)

**If sitemap index detected:**

**1. Inspect all sub-sitemaps:**
```bash
# Example: post-sitemap.xml
./scrapai inspect https://example.com/post-sitemap.xml --project myproject

# Look for URLs like:
# https://example.com/2024/01/article-1
# https://example.com/2024/01/article-2
# https://example.com/2024/02/article-3

# Example: page-sitemap.xml
./scrapai inspect https://example.com/page-sitemap.xml --project myproject

# Look for URLs like:
# https://example.com/about
# https://example.com/contact
# https://example.com/privacy
```

**2. Analyze and categorize:**
- **post-sitemap.xml**: Contains article URLs (pattern: `/2024/01/...`) → This is what we want ✓
- **page-sitemap.xml**: Static pages (about, contact) → Skip these ✗
- **category-sitemap.xml**: Category pages → Skip these ✗

**3. Report findings to user:**
```
Sitemap index detected with 3 sub-sitemaps:

1. post-sitemap.xml (450 URLs)
   Sample: /2024/01/article-name, /2024/02/another-article
   → Articles - will extract content ✓

2. page-sitemap.xml (12 URLs)
   Sample: /about, /contact, /privacy
   → Static pages - extraction will fail (expected) ✗

3. category-sitemap.xml (8 URLs)
   Sample: /category/news, /category/sports
   → Category pages - extraction will fail (expected) ✗

Strategy: Spider will crawl ALL URLs, but only articles will extract successfully.
```

### Step 2: Test Extraction on Sample URLs

**Pick 2-3 article URLs from article sub-sitemap:**
```bash
./scrapai inspect https://example.com/2024/01/article-1 --project myproject
./scrapai inspect https://example.com/2024/01/article-2 --project myproject
```

**Check extraction quality:**
- Title extracted? ✓/✗
- Content complete? ✓/✗
- Author present? ✓/✗
- Date extracted? ✓/✗

**Decision:**
- If all good → use `EXTRACTOR_ORDER: ["newspaper", "trafilatura"]`
- If poor → discover custom CSS selectors (see Phase 2 in analysis-workflow.md)

### Step 3: Create Spider JSON

**Can use main sitemap OR specific sub-sitemap URL**

**Note: Sitemap spiders don't need rules** - they automatically crawl all URLs from sitemap.

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

**Or use specific sub-sitemap directly:**
```json
{
  "name": "example_blogs",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/sitemap_blogs_1.xml"],
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

**Why main sitemap URL?**
- Scrapy automatically detects sitemap index
- Automatically fetches all sub-sitemaps
- Crawls ALL URLs from ALL sub-sitemaps
- Simpler configuration

**What happens during crawl:**
- ✓ Articles from post-sitemap.xml → extraction succeeds
- ✗ Pages from page-sitemap.xml → extraction fails (expected, no content)
- ✗ Categories from category-sitemap.xml → extraction fails (expected, no content)

This is normal and okay! Only article URLs need to extract successfully.

### Step 4: Test and Deploy

**Import spider:**
```bash
./scrapai spiders import spider.json --project myproject
```

**Test crawl:**
```bash
./scrapai crawl example_sitemap --limit 5 --project myproject
```

**Verify results:**
```bash
./scrapai show example_sitemap --limit 5 --project myproject
```

**Check:**
- Do extracted items have good titles and content?
- Are there 5 items (or fewer if some failed)?
- Quality acceptable?

**If yes → Deploy to production**
**If no → Go back to Step 2, improve extraction config**

## How It Works

1. **Explicit configuration**: Agent decides if URL is a sitemap and sets `"USE_SITEMAP": true`
2. **Spider selection**: Uses `SitemapDatabaseSpider` instead of regular `DatabaseSpider`
3. **Nested sitemap handling**: Automatically fetches sitemap indexes and all sub-sitemaps
4. **URL extraction**: Automatically extracts all URLs from all sitemaps
5. **Content scraping**: Scrapes each URL with configured extraction strategy

**No auto-detection** - agent must explicitly enable sitemap mode. This allows using any URL pattern (sitemap.xml, sitemap_blogs_1.xml, post-sitemap.xml, etc.)

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
  "settings": {
    "USE_SITEMAP": true,
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
🗺️  Using sitemap spider
🚀 Running DB spider: example_sitemap
```

### Method 2: Via Queue

**Add sitemap URL to queue:**
```bash
./scrapai queue add https://example.com/sitemap.xml --project news
```

**Process queue:**
When the agent processes this URL, it will:
1. Recognize it's a sitemap
2. Create spider JSON with `"USE_SITEMAP": true`
3. Spider extracts all URLs from sitemap automatically
4. Scrapes each URL

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
  "settings": {
    "USE_SITEMAP": true,
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
  "settings": {
    "USE_SITEMAP": true,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

### E-commerce Product Sitemap

```json
{
  "name": "products",
  "allowed_domains": ["shop.example.com"],
  "start_urls": ["https://shop.example.com/product-sitemap.xml"],
  "settings": {
    "USE_SITEMAP": true,
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
    "USE_SITEMAP": true,
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
    "USE_SITEMAP": true,
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
    "USE_SITEMAP": true,
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
