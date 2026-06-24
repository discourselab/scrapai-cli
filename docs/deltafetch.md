# DeltaFetch: Incremental Crawling

Skips pages unchanged since last crawl. First crawl scrapes everything; subsequent crawls only process new/changed pages.

**✓ Enabled by default** in scrapai - all crawls automatically use incremental crawling.

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

**Storage location (not overridable):** The CLI always sets the storage directory per project to `.scrapy/deltafetch/<project>/`, so a spider's hash database lives at `.scrapy/deltafetch/<project>/<spider>.db`. `DELTAFETCH_DIR` in spider JSON is ignored — the CLI overrides it on every crawl.

**Deprecated: `DELTAFETCH_RESET`** is not honored from spider settings. Use the `--reset-deltafetch` CLI flag (below) instead.

## Reset Options

**Use the CLI flag** — it clears both the DeltaFetch hash database and the checkpoint:
```bash
./scrapai crawl spider --project proj --reset-deltafetch
```

This deletes `.scrapy/deltafetch/<project>/<spider>.db` and removes the spider's checkpoint directory, then starts a completely fresh crawl.

## Combining with Other Features

```json
{ "DELTAFETCH_ENABLED": true, "CLOUDFLARE_ENABLED": true, "CLOUDFLARE_STRATEGY": "hybrid" }
```

```json
{ "USE_SITEMAP": true, "DELTAFETCH_ENABLED": true }
```

## Troubleshooting

**"Not skipping any pages":**
- Verify `DELTAFETCH_ENABLED` is not set to `false` in spider settings (it is on by default)
- First crawl never skips (nothing to compare against)

**"Skipping pages that should be re-crawled":**
- Reset the cache: `./scrapai crawl spider --project proj --reset-deltafetch`

**Monitoring:** Look for log lines: `[scrapy_deltafetch] DEBUG: Ignoring already fetched: <url>`

## Limitations

- First crawl is always full (no prior hashes)
- Detects content changes only; new pages are always crawled
- Hash database is local (not synced across machines)
