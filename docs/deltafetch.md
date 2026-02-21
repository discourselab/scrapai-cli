# DeltaFetch: Incremental Crawling

DeltaFetch enables incremental crawling by skipping pages that haven't changed since the last crawl. This is perfect for monitoring sites for updates without re-scraping unchanged content.

## How It Works

1. **First crawl**: Scrapes all pages, stores content hash for each URL
2. **Subsequent crawls**: Compares current page hash with stored hash
3. **Changed pages**: Re-scrapes and updates
4. **Unchanged pages**: Skips entirely (saves time and bandwidth)

## When to Use

**Good use cases:**
- Monitoring news sites for new articles (crawl daily, only get new content)
- Recurring crawls (weekly/monthly updates)
- Large sites where full re-crawl is expensive
- Update detection ("what changed since yesterday?")

**Not needed for:**
- One-off crawls (just scraping a site once)
- Sites that always have new content on every page
- Very small crawls (<100 pages)

## Configuration

### Enable per Spider

Add to your spider JSON:

```json
{
  "name": "example_spider",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com"],
  "rules": [...],
  "settings": {
    "DELTAFETCH_ENABLED": true
  }
}
```

### Optional Settings

**Customize storage location:**
```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true,
    "DELTAFETCH_DIR": ".scrapy/deltafetch/my_spider"
  }
}
```

**Reset deltafetch on each run (for testing):**
```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true,
    "DELTAFETCH_RESET": true
  }
}
```

**Note:** `DELTAFETCH_RESET: true` clears stored hashes before each crawl, effectively disabling incremental crawling. Only use for testing.

## Storage

DeltaFetch stores page hashes in:
- **Default location**: `.scrapy/deltafetch/`
- **Per spider**: Separate storage for each spider
- **Persistent**: Survives across crawls (until manually deleted)

The stored data is small (just URL + hash), typically a few KB even for thousands of pages.

## Usage Examples

### Example 1: Daily News Monitoring

**Scenario:** Crawl news site daily, only get new articles

```json
{
  "name": "news_monitor",
  "allowed_domains": ["news.example.com"],
  "start_urls": ["https://news.example.com/articles"],
  "rules": [
    {
      "allow": ["/articles/[0-9]{4}/"],
      "callback": "parse_article",
      "follow": false
    },
    {
      "allow": ["/articles"],
      "callback": null,
      "follow": true
    }
  ],
  "settings": {
    "DELTAFETCH_ENABLED": true
  }
}
```

**First run:** Scrapes all articles (let's say 500 articles)
**Second run (next day):** Only scrapes new/changed articles (maybe 20-30 new ones)

**Time saved:** Instead of 500 pages × 2 seconds = 16 minutes, now 30 pages × 2 seconds = 1 minute

### Example 2: Weekly Blog Updates

**Scenario:** Check blog for new posts weekly

```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true,
    "DELTAFETCH_DIR": ".scrapy/deltafetch/weekly_blogs"
  }
}
```

Run weekly via cron/scheduler - automatically skips unchanged blog posts.

## Performance Impact

**Benefits:**
- **Faster crawls**: Skip unchanged pages entirely
- **Reduced bandwidth**: Don't download unchanged content
- **Lower server load**: Fewer requests to target site
- **Cost savings**: Less compute time on cloud infrastructure

**Overhead:**
- **Minimal**: Hash calculation is very fast (~0.001 seconds per page)
- **Storage**: Few KB to few MB depending on site size
- **First crawl**: No change (must crawl everything to build hash database)

## Monitoring Deltafetch

**Check what's being skipped:**

Look for log messages during crawl:
```
[scrapy_deltafetch] DEBUG: Ignoring already fetched: https://example.com/page1
[scrapy_deltafetch] DEBUG: Ignoring already fetched: https://example.com/page2
```

**Check storage:**
```bash
ls -lh .scrapy/deltafetch/
```

Shows stored hash databases per spider.

## Resetting Deltafetch

**To force re-crawl of all pages:**

**Option 1: Delete storage directory**
```bash
rm -rf .scrapy/deltafetch/
```

**Option 2: Enable reset flag (one-time)**
```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true,
    "DELTAFETCH_RESET": true
  }
}
```

**Option 3: Delete specific spider's data**
```bash
rm -rf .scrapy/deltafetch/<spider_name>/
```

## Combining with Other Features

### DeltaFetch + Cloudflare

Works perfectly together:
```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true,
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid"
  }
}
```

DeltaFetch runs after page is fetched (whether via Cloudflare or normal HTTP).

### DeltaFetch + Queue System

Ideal for processing queued sites:
```bash
# Add sites to queue
./scrapai queue add https://site1.com --project news
./scrapai queue add https://site2.com --project news

# Process with deltafetch enabled
# Each site's deltafetch data stored separately
```

### DeltaFetch + Scheduling

When you add scheduling (future feature), deltafetch becomes essential:
- Schedule daily crawls
- Only scrape changed content
- Automatic incremental updates

## Limitations

1. **First crawl is full**: Must crawl everything initially to build hash database
2. **Changed content only**: Detects page content changes, not new pages (new pages are always crawled)
3. **URL-based**: Same content on different URL = separate entries
4. **No cloud sync**: Hash database is local (not shared across machines)

## Troubleshooting

**"Not skipping any pages"**
- Check `DELTAFETCH_ENABLED: true` is in spider settings
- Verify this isn't the first crawl (nothing to compare against yet)
- Check `.scrapy/deltafetch/` directory exists and has data

**"Skipping pages that should be crawled"**
- Delete hash database: `rm -rf .scrapy/deltafetch/`
- Or set `DELTAFETCH_RESET: true` for one run

**"Storage growing too large"**
- Each spider has separate storage - this is intentional
- Delete old spider data: `rm -rf .scrapy/deltafetch/<old_spider>/`

## Technical Details

**How hashing works:**
- Uses MD5 hash of page content
- Stores URL → hash mapping
- On next crawl: fetches page, compares hash, skips if identical

**Storage format:**
- DBM database (Berkeley DB or similar)
- Key: URL fingerprint
- Value: Content hash

**Middleware priority:**
- Runs at priority 100 (after download, before parsing)
- Can be adjusted via `SPIDER_MIDDLEWARES` setting
