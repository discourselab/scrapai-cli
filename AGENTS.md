# ScrapAI CLI - Cursor Rules

You are working on ScrapAI CLI, a project-based Scrapy spider management system for large-scale web scraping.

## 🚨 CRITICAL: ALWAYS SEQUENTIAL, NEVER PARALLEL

**ABSOLUTE REQUIREMENT: Process ONE website at a time. NEVER use parallel processing.**

❌ FORBIDDEN:
- Background tasks or concurrent processing
- Processing multiple websites simultaneously
- Creating multiple spiders in parallel

✅ REQUIRED:
- Process one website at a time, start to finish
- Complete the FULL workflow for each website before moving to next
- All work done sequentially

## Virtual Environment Requirements

**CRITICAL: Always use virtual environment for all CLI commands.**

Every CLI command MUST start with:
```bash
source .venv/bin/activate && <command>
```

First time setup:
1. Check: `./scrapai verify`
2. If needed: `./scrapai setup` then `source .venv/bin/activate`

## Command Execution Rules

**NEVER chain multiple operations together** (except venv activation)

❌ BAD:
```bash
source .venv/bin/activate && bin/inspector --url https://example.com && ./scrapai extract-urls ... && cat file.txt | grep something
```

✅ GOOD:
```bash
# Activate venv + single command is OK
source .venv/bin/activate && bin/inspector --url https://example.com
```

Then in separate bash calls:
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/site/page.html -o data/site/urls.txt
```

**Key Principle: ONE command at a time. Wait for completion. Read output before proceeding.**

## Database-First Workflow: Four Phases

### ⚠️ NEVER SKIP PHASES. NEVER MARK STATUS PREMATURELY.

Complete EVERY step of EVERY phase before proceeding:

### Phase 1: Analysis & Section Documentation

**CRITICAL: Complete FULL site analysis before creating ANY rules.**

**Step 1: Extract ALL URLs from Homepage**
```bash
source .venv/bin/activate
./scrapai extract-urls --file data/website/analysis/page.html --output data/website/analysis/all_urls.txt
cat data/website/analysis/all_urls.txt
```

**Step 2: Categorize Every URL Type**
Review ALL URLs from `all_urls.txt` and identify:
- Content pages (articles, blog posts, reports, publications, etc.)
- Navigation/listing pages
- Utility pages (exclude these)
- PDF content (note but skip)
- Any other URL patterns

**Step 3: Document Complete Site Structure**
Create comprehensive `sections.md` documenting EVERY section type and URL pattern.

**Step 4: Iterative Section Drilling (ONE AT A TIME)**
```bash
# Visit ONE section URL
source .venv/bin/activate && bin/inspector --url https://example.com/news/

# IMMEDIATELY read and document
cat data/example_com/analysis/analysis.json
source .venv/bin/activate && ./scrapai extract-urls --file data/example_com/analysis/page.html --output data/example_com/analysis/news_urls.txt

# Update sections.md with findings

# Then move to next section (repeat cycle)
```

**⚠️ CRITICAL: NEVER run multiple inspectors in parallel - they overwrite `page.html` and `analysis.json`**

**DO NOT inspect individual content pages - extractors handle content extraction**

### Phase 2: Section-Based Rule Generation

**Step 2A: Use sections.md for Rule Creation**
Read complete `sections.md` to understand all sections, URL patterns, and content types.

**Step 2B: Create Individual Section Rule Files**
For each section in `sections.md`, create specific rule files.

**Step 2C: Consolidate into Final Spider JSON**
Combine all section rule files into comprehensive spider definition.

**Rule Structure:**
```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["URL patterns from analysis"],
  "rules": [
    {
      "allow": ["patterns for final content pages"],
      "deny": ["patterns to exclude"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["patterns for navigation pages"],
      "deny": ["patterns to avoid"],
      "callback": null,
      "follow": true,
      "priority": 50
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura", "playwright"]
  }
}
```

**Do not create Python files. Only JSON configurations.**

### Phase 3: Import

```bash
source .venv/bin/activate && ./scrapai spiders import data/website/analysis/final_spider.json
```

### Phase 4: Execution & Verification

**Storage Mode Selection:**
- **With `--limit`**: Saves to database (testing/verification)
- **Without `--limit`**: Exports to files only (production)

**Testing:**
```bash
source .venv/bin/activate && ./scrapai crawl website_name --limit 10
source .venv/bin/activate && ./scrapai show website_name --limit 5
```

**Production:**
```bash
source .venv/bin/activate && ./scrapai crawl website_name
```

## Content Focus Rules

**Default: ONLY focus on content sections. Ignore navigation and utility pages.**

**Include (HTML content only - ignore PDFs):**
- Articles, blog posts, news items
- Research papers, policy reports, analysis
- Publications, speeches, testimonies
- Case studies, briefs, commentaries
- ANY pages with substantive written content

**Exclude (Minimal List):**
- About/team/leadership pages
- Contact, donate, support pages
- Login, signup, account pages
- Privacy, terms, cookies pages
- Author profile pages
- Category/tag archive pages
- Pagination pages
- PDF files (note presence but skip)

**When in doubt, INCLUDE IT.** User explicit instructions ALWAYS override defaults.

## Status Marking Rule

ONLY mark queue items as complete when:
1. ✅ Phase 1: Full analysis documented in sections.md
2. ✅ Phase 2: All rules created and consolidated into final_spider.json
3. ✅ Phase 3: Spider successfully imported to database
4. ✅ Phase 4: Test crawl run and results verified

```bash
# Only if ALL phases complete:
source .venv/bin/activate && ./scrapai queue complete <id>

# If test fails:
source .venv/bin/activate && ./scrapai queue fail <id> -m "Extraction failed: [reason]"
```

## Queue System (Optional)

Use queue when user explicitly requests it.

**Direct Processing (Default):**
User: "Add this website: https://example.com"
→ Immediately process: analyze → rules → import → test

**Queue Mode (When Requested):**
```bash
# Add to queue
source .venv/bin/activate && ./scrapai queue add <url> -m "instruction"

# Process next item
source .venv/bin/activate && ./scrapai queue next
# Then follow full 4-phase workflow
# Mark complete/failed when done
```

## CLI Reference

**Spider Management:**
```bash
source .venv/bin/activate && ./scrapai spiders list
source .venv/bin/activate && ./scrapai spiders import <file>
source .venv/bin/activate && ./scrapai spiders delete <name>
```

**Data Inspection:**
```bash
source .venv/bin/activate && ./scrapai show <spider_name>
source .venv/bin/activate && ./scrapai show <spider_name> --limit 10
source .venv/bin/activate && ./scrapai show <spider_name> --title "search"
```

**Data Export (Only when user explicitly requests):**
```bash
source .venv/bin/activate && ./scrapai export <spider_name> --format csv
source .venv/bin/activate && ./scrapai export <spider_name> --format json
source .venv/bin/activate && ./scrapai export <spider_name> --format parquet
```

Formats: CSV, JSON, JSONL, Parquet
Location: `data/<spider_name>_export_<timestamp>.<format>`

## Core Principles

1. **Database First**: All configuration lives in database
2. **Sequential Processing**: One site at a time, no parallelism
3. **Complete Workflows**: Never skip phases or mark status prematurely
4. **Smart Extraction**: Content extraction handled automatically
5. **One Command at a Time**: No chaining except venv activation
6. **Quality over Speed**: Thorough analysis beats rushing

## What to Modify

✅ Allowed:
- Creating/editing JSON payloads
- Running CLI commands
- Updating .env (if requested)

❌ Not Allowed:
- Creating .py spider files (legacy)
- Modifying core framework code
- Using parallel processing or background tasks
