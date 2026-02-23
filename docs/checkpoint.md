# Checkpoint Pause/Resume

ScrapAI automatically enables checkpoint support for production crawls, allowing you to pause long-running crawls and resume them later without losing progress.

## How It Works

**Automatic for Production Crawls:**
- Checkpoint is **automatically enabled** when running production crawls (no `--limit` flag)
- Press **Ctrl+C** to pause → checkpoint saved automatically
- Run the **same command** again → automatically resumes from checkpoint
- On **successful completion** → checkpoint cleaned up automatically

**Test crawls** (with `--limit`) do **not** use checkpoints since they're short-running.

## What Gets Saved

Scrapy's JOBDIR feature saves:
1. **Pending requests** - All URLs waiting to be crawled
2. **Duplicates filter** - URLs already visited (prevents re-crawling)
3. **Spider state** - Any custom state stored in `spider.state` dict

## Usage

### Production Crawl with Checkpoint

```bash
# Start production crawl (checkpoint auto-enabled)
./scrapai crawl myspider --project myproject

# Output shows:
# 💾 Checkpoint enabled: ./data/myproject/myspider/checkpoint
# Press Ctrl+C to pause, run same command to resume

# Press Ctrl+C to pause
^C

# Resume later - run same command
./scrapai crawl myspider --project myproject
# Automatically detects checkpoint and resumes
```

### Test Crawl (No Checkpoint)

```bash
# Test mode - no checkpoint needed (short run)
./scrapai crawl myspider --project myproject --limit 10

# Output shows:
# 🧪 Test mode: Saving to database (limit: 10 items)
```

## Checkpoint Storage

Checkpoints are stored in your DATA_DIR:
```
DATA_DIR/<project>/<spider>/checkpoint/
```

Example:
```
./data/myproject/myspider/
├── analysis/        # Phase 1-3 files
├── crawls/          # Production outputs
├── exports/         # Database exports
└── checkpoint/      # Checkpoint state (auto-cleaned on success)
```

## Cleanup

**Automatic cleanup on successful completion:**
- When spider completes successfully (no Ctrl+C), checkpoint directory is automatically deleted
- Saves disk space
- Only failed/interrupted crawls keep checkpoints

**Manual cleanup:**
```bash
# If you want to discard a checkpoint and start fresh
rm -rf ./data/myproject/myspider/checkpoint/
```

## Limitations

⚠️ **Request callbacks must be spider methods** (Scrapy limitation):
```python
# ✅ Works (spider method)
Request(url, callback=self.parse_article)

# ❌ Won't work (external function)
Request(url, callback=some_external_function)
```

✅ **ScrapAI spiders already compatible**: Our database spiders use spider methods (`self.parse`), so checkpoints work out of the box!

⚠️ **Cookie expiration**: If you wait too long to resume (days/weeks), cookies may expire and requests may fail. Resume within a reasonable timeframe (hours/days, not weeks).

⚠️ **Multiple runs**: Each spider should have only one checkpoint at a time. Don't run the same spider concurrently while a checkpoint exists.

⚠️ **Proxy type changes**: If you change `--proxy-type` when resuming (e.g., auto → residential), the checkpoint is automatically cleared and crawl starts fresh. This ensures all URLs are retried with the new proxy type.

## When Checkpoints Are Useful

✅ **Long-running crawls** (hours/days) - Resume if interrupted
✅ **Unstable connections** - Resume after network failures
✅ **System maintenance** - Pause before server restart, resume after
✅ **Resource management** - Pause during high-load periods, resume later

❌ **Short test crawls** (minutes) - Not needed, checkpoints disabled
❌ **Quick prototyping** - Use `--limit` flag, no checkpoints

## Technical Details

**Built on Scrapy's JOBDIR:**
- Uses Scrapy's native pause/resume feature (not custom implementation)
- Checkpoint files are pickle-serialized Scrapy objects
- Atomic writes prevent checkpoint corruption
- Compatible with all Scrapy spiders

**Directory per spider:**
- Each spider gets its own checkpoint directory
- Prevents conflicts between spiders
- Clean separation of state

**Smart cleanup:**
- Exit code 0 (success) → cleanup checkpoint
- Exit code != 0 (error/Ctrl+C) → keep checkpoint for resume

## Troubleshooting

### Checkpoint not resuming

**Check if checkpoint exists:**
```bash
ls -la ./data/myproject/myspider/checkpoint/
```

If directory doesn't exist, checkpoint was cleaned up (successful completion) or never created.

### Want to start fresh (discard checkpoint)

```bash
rm -rf ./data/myproject/myspider/checkpoint/
./scrapai crawl myspider --project myproject
```

### Checkpoint from old spider version

If you updated spider rules/selectors significantly, old checkpoint may be incompatible. Delete checkpoint and start fresh:
```bash
rm -rf ./data/myproject/myspider/checkpoint/
```

### Proxy type changes (Expert-in-the-Loop)

When you get an expert-in-the-loop prompt and switch proxy types:

```bash
# Initial crawl with auto mode (uses datacenter)
./scrapai crawl myspider --project proj

# Datacenter fails → expert prompt appears
# Press Ctrl+C to pause

# Resume with residential proxy
./scrapai crawl myspider --project proj --proxy-type residential

# Output shows:
# ⚠️  Proxy type changed: auto → residential
# 🗑️  Clearing checkpoint to ensure all URLs retried with residential proxy
# ♻️  Starting fresh crawl
```

**Why checkpoint is cleared:**
- Ensures blocked URLs are retried with new proxy type
- Prevents Scrapy's dupefilter from skipping already-seen failed URLs
- Simpler and safer than complex retry logic
- User explicitly chose expensive residential proxy, accepts comprehensive re-crawl

## See Also

- [Analysis Workflow](analysis-workflow.md) - Spider building workflow
- [Cloudflare Bypass](cloudflare.md) - For Cloudflare-protected sites
- [Queue Management](queue.md) - Batch processing multiple sites
