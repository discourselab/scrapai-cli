# Spider Health Checks

**Automated testing to detect broken spiders before they impact production.**

Websites redesign constantly. The `health` command tests all spiders in a project, detects failures, and generates a report for the coding agent to fix.

## The Problem

- **Websites change:** High-traffic sites redesign every 3-6 months
- **Scrapers break silently:** Empty fields, missing articles, broken URL patterns
- **Manual fixes are slow:** 45+ minutes to investigate, update selectors, and test
- **At scale, it's unsustainable:** 100 spiders × 4 breaks/year = 300+ hours

## The Solution

**AI-assisted health checks:**

```bash
# Monthly cron job
./scrapai health --project news

# Output: which spiders passed/failed
# Report: markdown file for agent to read and fix
```

**Fix workflow:**
1. Health check detects broken spider (5 min)
2. Agent reads report, re-analyzes site (3 min)
3. Agent updates config, verifies fix (2 min)
4. **Total: 10 minutes vs 45 minutes manual**

## Usage

### Basic Usage

```bash
# Test all spiders in project
./scrapai health --project news

# Custom report location
./scrapai health --project news --report /tmp/health.md

# Test with more items
./scrapai health --project news --limit 10

# Adjust content length threshold
./scrapai health --project news --min-content-length 100
```

### Example Output

```
============================================================
Spider Health Check - Project: news
============================================================

Testing 5 spider(s)...

✅ nytimes       5 items, extraction OK
✅ guardian      5 items, extraction OK
❌ bbc           5 items, EXTRACTION BROKEN
❌ techcrunch    0 items, CRAWLING BROKEN
✅ reuters       5 items, extraction OK

============================================================
Summary
============================================================
Total:  5
Passed: 3 ✅
Failed: 2 ❌

Report saved to: data/news/health/20260302/report.md
```

### Report Format

The generated report is designed for coding agents to read and fix:

```markdown
# Spider Health Report - news

**Date:** 2026-03-02 10:30:00
**Total:** 5 spiders
**Passed:** 3
**Failed:** 2

## Failed Spiders

### bbc (EXTRACTION BROKEN)

- **Items found:** 5
- **Problem:** Content too short (0 chars). Extraction selectors may be broken.
- **Sample output:**
  ```json
  {
    "title": "UK weather warnings",
    "content": "",
    "author": "",
    "date": "2026-03-02",
    "url": "https://www.bbc.co.uk/news/articles/xyz"
  }
  ```
- **Fix needed:** Update CSS selectors for content extraction
- **Test URL:** https://www.bbc.co.uk/news/articles/xyz

### techcrunch (CRAWLING BROKEN)

- **Items found:** 0
- **Problem:** Only 0 items found (expected 5). Spider may not be finding articles.
- **Fix needed:** Update crawling rules (URL patterns, start URLs, or allowed domains)
- **Action:** Re-analyze site structure and update spider config

## Passed Spiders
- nytimes (5 items)
- guardian (5 items)
- reuters (5 items)
```

## Two Failure Modes

### 1. Extraction Broken

**Symptoms:** Spider finds articles but extracts empty/incomplete fields

**Cause:** CSS selectors changed (e.g., `.article-content` → `.article-body`)

**Sample output:**
```json
{
  "title": "Article Title",
  "content": "",        // ❌ Empty
  "author": "",         // ❌ Empty
  "date": "2026-03-01"
}
```

**Fix:** Agent updates extraction selectors

### 2. Crawling Broken

**Symptoms:** Spider can't find articles (0-2 items or timeout)

**Cause:** URL patterns changed (e.g., `/blog/` → `/articles/`)

**Fix:** Agent updates crawling rules

## Automated Testing with Cron

### Monthly Testing (Recommended)

```bash
# Edit crontab
crontab -e
```

```bash
# Test news spiders monthly (1st of month at 2 AM)
0 2 1 * * cd /path/to/scrapai-cli && ./scrapai health --project news

# Test e-commerce spiders monthly (1st at 3 AM)
0 3 1 * * cd /path/to/scrapai-cli && ./scrapai health --project ecommerce

# Test critical spiders weekly (every Monday at 4 AM)
0 4 * * 1 cd /path/to/scrapai-cli && ./scrapai health --project critical
```

### Bash Wrapper Script

```bash
#!/bin/bash
# health-check.sh

PROJECT="$1"
if [ -z "$PROJECT" ]; then
  echo "Usage: $0 <project>"
  exit 1
fi

cd /path/to/scrapai-cli

# Run health check
./scrapai health --project "$PROJECT"
EXIT_CODE=$?

# Send notification if failures
if [ $EXIT_CODE -ne 0 ]; then
  # Email notification
  echo "Health check failed for project: $PROJECT" | \
    mail -s "ScrapAI: Spider failures detected" team@example.com

  # Or Slack notification
  # curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK \
  #   -d '{"text": "ScrapAI health check failed for '"$PROJECT"'"}'
fi

exit $EXIT_CODE
```

```bash
chmod +x health-check.sh
```

## Fixing Broken Spiders

### Step 1: Confirm the Issue

```bash
./scrapai health --project news
# Check report: data/news/health/20260302/report.md
```

### Step 2: Agent Re-Analysis

**Prompt to agent:**

```
The spider "bbc" in project "news" is broken.

Read the health report at: data/news/health/20260302/report.md

Re-analyze the site and update the spider config to fix the extraction.
```

### Step 3: Agent Updates Config

Agent will:
1. Inspect the failing URL
2. Analyze current HTML structure
3. Update CSS selectors in spider config
4. Import updated config
5. Test to verify fix

### Step 4: Verify Fix

```bash
# Run health check again
./scrapai health --project news

# Or test specific spider
./scrapai crawl bbc --project news --limit 5
./scrapai show bbc --project news --limit 5
```

## Exit Codes

- **0:** All spiders passed
- **1:** One or more spiders failed

Useful for CI/CD pipelines and monitoring scripts:

```bash
./scrapai health --project news
if [ $? -ne 0 ]; then
  echo "Failures detected, sending alert..."
  notify-team.sh
fi
```

## Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--project` | Project name (required) | - |
| `--report` | Custom report path | `data/<project>/health/<YYYYMMDD>/report.md` |
| `--limit` | Items to test per spider | `5` |
| `--min-content-length` | Min chars to pass extraction | `50` |

## How Detection Works

For each spider, the health check:

1. **Runs crawl:** `./scrapai crawl <spider> --limit 5 --project <name>`
2. **Counts items:** Queries database for scraped items
3. **Checks crawling:**
   - ✅ Pass: 3+ items found
   - ❌ Fail: < 3 items (crawling broken)
4. **Checks extraction:**
   - ✅ Pass: Content length ≥ 50 chars
   - ❌ Fail: Content too short (extraction broken)
5. **Generates report:** Markdown with failure details + sample output

## Best Practices

1. **Monthly testing for most spiders** - Sites don't redesign more than once a month
2. **Weekly for critical data sources** - High-priority spiders warrant more frequent checks
3. **Check both item count and content** - Detects both failure modes
4. **Keep reports for trend analysis** - Track which spiders break frequently
5. **Batch fixes** - If multiple spiders break, fix them in one session
6. **Update test configs** - When start_urls become outdated, update them

## Troubleshooting

### All Tests Failing

**Possible causes:**
- Network issues
- Database corruption
- Rate limiting

**Debug:**
```bash
# Test one spider manually with verbose logging
./scrapai crawl single_spider --project news --limit 1 \
  --scrapy-args '-L DEBUG'
```

### Intermittent Failures

**Symptoms:** Same spider passes sometimes, fails others

**Causes:**
- A/B testing on the site
- Geo-based content
- Rate limiting
- Dynamic content loading

**Solutions:**
- Run test multiple times
- Use `--browser` flag if JS rendering needed
- Add delays between tests

### Agent Can't Fix

**Symptoms:** Agent updates config but extraction still fails

**Possible reasons:**
- Site fundamentally changed (static → JS-rendered)
- Paywall added
- Anti-scraping measures increased

**Next steps:**
1. Try `--browser` flag for JS rendering
2. Manual inspection and fix
3. Consider if spider is still viable

## Economics

### Time Savings

| Scale | Manual | Agent-Assisted | Saved |
|-------|--------|---------------|-------|
| 10 spiders | 30 hrs/year | 3 hrs/year | 27 hrs |
| 50 spiders | 150 hrs/year | 15 hrs/year | 135 hrs |
| 100 spiders | 300 hrs/year | 30 hrs/year | **270 hrs** |

**Assumptions:**
- 4 breaks per spider per year
- Manual fix: 45 min (investigation + update + test)
- Agent-assisted: 10 min (report + re-analysis + verify)

## See Also

- [Queue System](queue.md) - Batch processing multiple sites
- [Analysis Workflow](analysis-workflow.md) - How agents build spiders
- [Extractors](extractors.md) - CSS selector configuration
