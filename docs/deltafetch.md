# DeltaFetch: Incremental Crawling

Skips pages unchanged since last crawl. First crawl scrapes everything; subsequent crawls only process new/changed pages.

## Configuration

```json
{
  "settings": {
    "DELTAFETCH_ENABLED": true
  }
}
```

**Custom storage location:**
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

**Delete all hash storage:**
```bash
rm -rf .scrapy/deltafetch/
```

**Delete specific spider's data:**
```bash
rm -rf .scrapy/deltafetch/<spider_name>/
```

**One-time reset via config:** Set `DELTAFETCH_RESET: true` (re-crawls everything once).

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
