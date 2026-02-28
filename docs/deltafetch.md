# DeltaFetch: Incremental Crawling

Skips pages unchanged since last crawl. First crawl scrapes everything; subsequent crawls only process new/changed pages.

**✓ Enabled by default** in ScrapAI - all crawls automatically use incremental crawling.

## Configuration

**Already enabled!** DeltaFetch is ON by default in `settings.py`. No configuration needed.

**To disable (if needed):**

```json
{
  "settings": {
    "DELTAFETCH_ENABLED": false
  }
}
```

## CLI: Reset DeltaFetch Cache

**Recommended way to clear cache and start fresh:**
```bash
./scrapai crawl myspider --project myproject --reset-deltafetch
```

This clears:
1. DeltaFetch database (URL cache) - `.scrapy/deltafetch/<project>/<spider>.db`
2. Checkpoint (old dupefilter state) - prevents crawling only 1 item

Then starts a completely fresh crawl.

**Custom storage location (advanced):**
```json
{
  "DELTAFETCH_ENABLED": true,
  "DELTAFETCH_DIR": ".scrapy/deltafetch/my_spider"
}
```

**Reset (for testing — clears stored hashes):**
```json
{
  "DELTAFETCH_ENABLED": true,
  "DELTAFETCH_RESET": true
}
```

## Reset Options

**Preferred: Use CLI flag** (clears both DeltaFetch + checkpoint):
```bash
./scrapai crawl spider --project proj --reset-deltafetch
```

**Manual: Delete all hash storage:**
```bash
rm -rf .scrapy/deltafetch/
```

**Manual: Delete specific project/spider:**
```bash
rm -rf .scrapy/deltafetch/<project>/<spider>.db
```

**Deprecated: Config-based reset:** Set `DELTAFETCH_RESET: true` (use CLI flag instead).

## Combining with Other Features

```json
{ "DELTAFETCH_ENABLED": true, "CLOUDFLARE_ENABLED": true, "CLOUDFLARE_STRATEGY": "hybrid" }
```

```json
{ "USE_SITEMAP": true, "DELTAFETCH_ENABLED": true }
```

## Troubleshooting

**"Not skipping any pages":**
- Verify `DELTAFETCH_ENABLED: true` is in spider settings
- First crawl never skips (nothing to compare against)
- Check `.scrapy/deltafetch/` directory exists and has data

**"Skipping pages that should be re-crawled":**
- Delete hash database: `rm -rf .scrapy/deltafetch/`
- Or set `DELTAFETCH_RESET: true` for one run

**Monitoring:** Look for log lines: `[scrapy_deltafetch] DEBUG: Ignoring already fetched: <url>`
Check storage: `ls -lh .scrapy/deltafetch/`

## Limitations

- First crawl is always full (no prior hashes)
- Detects content changes only; new pages are always crawled
- Hash database is local (not synced across machines)
