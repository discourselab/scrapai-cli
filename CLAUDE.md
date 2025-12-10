# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites using a database-first approach.

## For Claude Code Instances

**When asked to add any website, follow this Database-First Workflow:**

### 1. Setup (First Time Only)

#### Virtual Environment & Database Setup
**CRITICAL: Always use virtual environment for all CLI commands.**

**Step 1: Check Environment Status**
```bash
# ALWAYS run verify first to check if setup is needed
./scrapai verify
```

**Step 2: Setup (Only if verify fails)**
```bash
# Only run setup if verify shows issues
./scrapai setup
# Then activate the virtual environment
source .venv/bin/activate
# Run verify again to confirm
./scrapai verify
```

**Step 3: Activate Virtual Environment**
```bash
# If verify passes, just activate and proceed
source .venv/bin/activate
```

**Database Management:**
- `source .venv/bin/activate && ./scrapai db migrate` - Run pending migrations
- `source .venv/bin/activate && ./scrapai db current` - Show current migration state  
- All schema changes are handled safely via Alembic migrations

### 2. Workflow

#### Phase 1: Analysis & Section Documentation
**CRITICAL: Identify site structure and article URL patterns. DO NOT inspect individual articles.**

**Key Principle:** Smart extractors (newspaper, trafilatura, playwright) automatically handle content extraction. Your job is to:
- Understand site navigation structure
- Identify URL patterns for articles vs. navigation pages
- Create rules to follow navigation and extract articles
- Let extractors handle the actual content extraction

**Step 1A: Homepage Analysis**
Inspect the site structure to understand how to extract content:
```bash
# Always activate virtual environment first
source .venv/bin/activate
# Start with homepage analysis
bin/inspector --url https://website.com/
# Read page.html and analysis.json immediately
```

**Step 1B: Create Section Documentation**
After homepage analysis, create a comprehensive section map:
```bash
# Create sections.md to document all discovered sections
# This file will track sections, URL patterns, and rule requirements
```

**Step 1C: Sequential Section Analysis (If Needed)**
```bash
# Always ensure virtual environment is active
source .venv/bin/activate
# IMPORTANT: Run inspectors SEQUENTIALLY, not in parallel
# Each inspector overwrites the same analysis files
# ONLY inspect sections/subsections to find where articles are listed
bin/inspector --url https://website.com/section1
# Read analysis, update sections.md, identify article URL patterns
bin/inspector --url https://website.com/section2
# Read analysis, update sections.md, identify article URL patterns
# STOP when you find article listings - DO NOT inspect actual articles
# Extractors (newspaper/trafilatura/playwright) handle content extraction
```

**Enhanced Analysis Workflow:**
1. **Homepage Analysis** - Run inspector on main page, read `page.html` and `analysis.json`
2. **Create `sections.md`** - Document all discovered sections with:
   - Section name and URL
   - URL patterns found in that section
   - Content type (navigation vs articles)
   - Rule requirements (allow/deny patterns)
3. **Section-by-Section Analysis (If Needed)** - For sections that need deeper inspection:
   - Run inspector on section URL to see article listings
   - Read and analyze results immediately
   - Identify article URL patterns from the listings
   - Update `sections.md` with findings
   - DO NOT inspect individual articles - extractors handle content extraction
   - Create `section_rules_[name].json` with specific rules for that section
4. **Consolidate Rules** - Combine all section rule files into final spider JSON

**File Structure Created:**
```
data/website/analysis/
├── page.html           (preserved - homepage HTML)
├── analysis.json       (preserved - homepage analysis)
├── sections.md         (NEW - comprehensive section documentation)
├── section_rules_news.json     (NEW - rules for news section)
├── section_rules_climate.json  (NEW - rules for climate section)
├── section_rules_research.json (NEW - rules for research section)
└── final_spider.json   (NEW - consolidated rules from all sections)
```

**Key Analysis Steps:**
1. **Start with homepage analysis** - Inspect the main page first to identify ALL major sections
2. **Document ALL sections** - Create `sections.md` with every major content section found
3. **Extract URL patterns from homepage** - Use `grep` to find article URLs:
   ```bash
   grep -o 'href="[^"]*"' data/website/analysis/page.html | head -50
   ```
4. **Identify article URL patterns** - Look for patterns like `/articles/.*`, `/news/.*`, `/analysis-.*`
5. **Section-specific analysis (if needed)** - Only inspect sections/subsections if homepage isn't sufficient
6. **STOP at article listings** - DO NOT inspect individual articles, extractors handle that
7. **Create modular rules** - Generate individual JSON rule files based on URL patterns
8. **Preserve all analysis** - Keep `page.html`, `analysis.json`, `sections.md`, and rule files
9. **Consolidate comprehensive rules** - Combine all section rules into final spider configuration

**Common Pitfalls to Avoid:**
- Don't assume homepage analysis is sufficient - inspect sections if needed to find article patterns
- Don't create rules without understanding URL patterns
- **DO NOT inspect individual articles** - Extractors (newspaper/trafilatura) handle content extraction
- **NEVER run multiple inspectors in parallel** - They overwrite the same analysis files
- **ALWAYS read and document analysis immediately** after each inspector run
- **NEVER delete analysis files** - Keep `page.html`, `analysis.json`, `sections.md`, and all rule files
- Focus on URL patterns, not content structure - that's the extractor's job
- Create section-specific rules before consolidating

#### Phase 2: Section-Based Rule Generation
Generate comprehensive rules using section documentation. **Do not create Python files.**

**Step 2A: Use sections.md for Rule Creation**
Read the complete `sections.md` file to understand:
- All sections discovered during analysis
- URL patterns for each section
- Content types (navigation vs articles)
- Specific requirements for each section

**Step 2B: Create Individual Section Rule Files**
For each section documented in `sections.md`, create specific rule files:
```json
// section_rules_news.json
{
  "section": "news",
  "rules": [
    {
      "allow": ["/news/.*", "/breaking/.*"],
      "deny": ["/news/live/.*", "/news/.*#comments"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/news/?$", "/breaking/?$"],
      "callback": null,
      "follow": true,
      "priority": 50
    }
  ]
}
```

**Step 2C: Consolidate into Final Spider JSON**
Combine all section rule files into a comprehensive spider definition:

#### Phase 2D: Final JSON Payload Structure

**Payload Structure:**
```json
{
  "name": "website_name",
  "allowed_domains": ["website.com"],
  "start_urls": [
    "https://www.website.com/",
    "https://www.website.com/section1",
    "https://www.website.com/section2"
  ],
  "rules": [
    {
      "allow": ["/articles/.*"],
      "deny": ["/articles/.*#comments", "/articles/.*\\?.*"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/section/.*", "/topics/.*"],
      "deny": ["/live/.*", "/videos/.*", ".*page=.*"],
      "callback": null,
      "follow": true,
      "priority": 50
    },
    {
      "deny": ["/login", "/signup", "/search", "/profile"],
      "callback": null,
      "follow": false,
      "priority": 0
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 3,
    "CONCURRENT_REQUESTS": 2,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura", "playwright"]
  }
}
```

**Rule Design Principles:**
- **Extraction rules** (`callback`: `"parse_article"`) - Only for actual content pages
- **Navigation rules** (`follow`: `true`) - For discovering article links
- **Block rules** (`deny`) - Prevent unwanted content extraction
- **Priority matters** - Higher priority rules are evaluated first
- **Be restrictive** - Only extract what you actually want

#### Phase 3: Import
**Import the final spider JSON file that was created in Phase 2.**

```bash
# Always activate virtual environment and import from the final_spider.json file
source .venv/bin/activate
./scrapai spiders import data/website/analysis/final_spider.json
```

**Why import from file:**
- Uses the consolidated JSON created during analysis
- Preserves the spider configuration for future reference
- Easy to review and modify before importing
- Can re-import same config if needed

#### Phase 4: Execution & Verification
**Always test with limited items first:**
```bash
source .venv/bin/activate
./scrapai crawl website_name --limit 10
```

**Verification Checklist:**
1. **Check extracted content quality**:
   ```bash
   source .venv/bin/activate
   ./scrapai show website_name --limit 5
   ```
2. **Verify article vs navigation extraction**:
   - Look for actual article titles (not "Latest News" or section names)
   - Confirm substantial content length (not just navigation snippets)
   - Check for proper metadata (author, date, etc.)

3. **If spider extracts wrong content**:
   - **DELETE the spider**: `source .venv/bin/activate && echo "y" | ./scrapai spiders delete website_name`
   - **Re-analyze the site structure** (Phase 1)
   - **Refine the rules** (Phase 2)
   - **Re-import and test** (Phases 3-4)

4. **Common fixes for wrong extraction**:
   - Make extraction rules more restrictive
   - Add more comprehensive deny patterns
   - Ensure `callback: "parse_article"` only on actual content URLs
   - Use `follow: true` without callbacks for navigation pages only

### 3. CLI Reference

**Environment Setup:**
-   `./scrapai verify` - Verify environment setup (no installations, just checks status)
-   `./scrapai setup` - Setup virtual environment and initialize database (run first)

**IMPORTANT: All other CLI commands require virtual environment activation:**
```bash
source .venv/bin/activate
```

**Spider Management:**
-   `source .venv/bin/activate && ./scrapai spiders list` - List all spiders in the DB.
-   `source .venv/bin/activate && ./scrapai spiders import <file>` - Import/Update a spider from JSON.
-   `source .venv/bin/activate && ./scrapai spiders delete <name>` - Delete a spider.

**Crawling:**
-   `source .venv/bin/activate && ./scrapai crawl <name>` - Run a specific spider.
-   `source .venv/bin/activate && ./scrapai crawl <name> --limit 10` - Test with a limit.

**Database Management:**
-   `source .venv/bin/activate && ./scrapai db migrate` - Run database migrations.
-   `source .venv/bin/activate && ./scrapai db current` - Show current migration revision.

**Data Inspection:**
-   `source .venv/bin/activate && ./scrapai show <spider_name>` - Show recent articles from spider (default: 5).
-   `source .venv/bin/activate && ./scrapai show <spider_name> --limit 10` - Show specific number of articles.
-   `source .venv/bin/activate && ./scrapai show <spider_name> --url pattern` - Filter by URL pattern (case-insensitive).
-   `source .venv/bin/activate && ./scrapai show <spider_name> --text "climate"` - Search title or content for text (case-insensitive).
-   `source .venv/bin/activate && ./scrapai show <spider_name> --title "climate"` - Search only article titles (case-insensitive).

**Data Export:**

**IMPORTANT: Only export data when the user EXPLICITLY requests it. Never export proactively.**

When the user requests an export:
1. **Ask which format they want**: CSV, JSON, JSONL, or Parquet
2. **Run the export command** with the chosen format
3. **Provide the full file path** to the user after export completes

Available export formats:
-   **CSV** - Comma-separated values (universal, works with Excel)
-   **JSON** - Pretty-printed JSON array (human-readable)
-   **JSONL** - JSON Lines format (one object per line, streaming-friendly)
-   **Parquet** - Columnar format (efficient for large datasets, works with pandas/data analysis tools)

Export commands:
-   `source .venv/bin/activate && ./scrapai export <spider_name> --format csv` - Export to CSV
-   `source .venv/bin/activate && ./scrapai export <spider_name> --format json --limit 100` - Export limited records
-   `source .venv/bin/activate && ./scrapai export <spider_name> --format parquet --title "climate"` - Export with filters
-   `source .venv/bin/activate && ./scrapai export <spider_name> --format jsonl --output /path/to/file.jsonl` - Custom output path

Export behavior:
-   Default location: `data/<spider_name>_export_<timestamp>.<format>` (timestamp format: ddmmyyyy_HHMMSS)
-   Custom location: Use `--output` to specify any path
-   Filters work with export: `--url`, `--title`, `--text`, `--limit`
-   Each export gets a unique timestamped filename (no overwrites)

Example workflow:
```
User: "Can you export the climate data?"
Assistant: "What format would you like? CSV, JSON, JSONL, or Parquet?"
User: "CSV please"
Assistant: [runs export command and provides file path]
"✅ Exported to: data/climate_spider_export_10122025_153045.csv"
```

## Extractor Options

The system uses a **Smart Extractor** that tries multiple strategies in order. You can configure the order via `EXTRACTOR_ORDER` in settings.

**Available Strategies:**
1.  `newspaper`: Uses `newspaper4k` on the static HTML (Fast, Default).
2.  `trafilatura`: Uses `trafilatura` on the static HTML (Good for text-heavy sites).
3.  `playwright`: Uses a headless browser to fetch rendered HTML, then extracts with `trafilatura` (Slow, handles JS).

**Default Order:** `["newspaper", "trafilatura", "playwright"]`

## Core Principles
-   **Database First**: All configuration lives in the database.
-   **Agent Driven**: Agents use CLI tools to manage the DB.
-   **Generic Spider**: The system uses a single `DatabaseSpider` that loads rules dynamically.
-   **Smart Extraction**: Content extraction is handled automatically with multiple fallback strategies.
-   **Database Persistence**: Scraped items are batched and saved efficiently to the PostgreSQL database.

## What Claude Code Can Modify
-   **✅ Allowed**:
    -   Creating/Editing JSON payloads.
    -   Running CLI commands (`scrapai`, `init_db.py`).
    -   Updating `.env` (if requested).
-   **❌ Not Allowed**:
    -   Creating `.py` spider files (Legacy).
    -   Modifying core framework code.

## Architecture Notes

**Database Schema:**
- `spiders` - Spider definitions (domains, start URLs)
- `spider_rules` - Link extraction rules (allow/deny patterns, selectors)  
- `spider_settings` - Custom Scrapy settings per spider
- `scraped_items` - Extracted content storage

**Key Framework Files:**
- `spiders/database_spider.py` - Generic spider loads config from DB
- `core/db.py` - Database connection and session management
- `core/models.py` - SQLAlchemy ORM models with timestamps (created_at, updated_at)
- `core/extractors.py` - Smart content extraction system
- `alembic/` - Database migration files for safe schema evolution

**Database Migration System:**
- Uses Alembic for safe schema changes without data loss
- `./init_db.py` now runs migrations instead of create_all()
- Migration history tracked for rollback capability
- Automatic timestamp tracking for spider configurations