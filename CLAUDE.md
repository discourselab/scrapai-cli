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
**CRITICAL: Complete FULL site analysis before creating ANY rules. DO NOT create rules prematurely.**

**⚠️ WARNING: DO NOT RUSH TO RULE CREATION ⚠️**
The most common mistake is creating spider rules without complete site analysis. This results in:
- Missing entire content sections
- Incomplete URL pattern understanding
- Having to delete and recreate the spider
- Wasted time and effort

**MANDATORY: Follow this systematic analysis process COMPLETELY before Phase 2:**

**Step 1: Extract ALL URLs from Homepage**
```bash
# Extract every single link from the homepage systematically
source .venv/bin/activate
./scrapai extract-urls --file data/website/analysis/page.html --output data/website/analysis/all_urls.txt
cat data/website/analysis/all_urls.txt
```

**Step 2: Categorize Every URL Type**
Manually review ALL URLs and identify:
- Content pages with actual articles
- Navigation/listing pages
- Utility pages to exclude
- Any other URL patterns present

**Step 3: Document Complete Site Structure**
Create comprehensive `sections.md` documenting EVERY section type and URL pattern found on the site.

**Step 4: Verify Nothing is Missed**
Review the complete URL list again and confirm you understand the full site structure before proceeding.

**ONLY AFTER COMPLETE ANALYSIS → Proceed to Phase 2 (Rule Creation)**

**Key Principle:** Smart extractors (newspaper, trafilatura, playwright) automatically handle content extraction. Your job is to:
- Understand COMPLETE site navigation structure
- Identify ALL URL patterns for articles vs. navigation pages
- Create comprehensive rules covering ALL content sections
- Let extractors handle the actual content extraction

**Default Content Focus (CRITICAL):**
**By default, ONLY focus on content sections. Ignore navigation and utility pages.**

**Include:**
- Articles, news, blog posts, research papers, analysis, reports
- Any pages with substantive written content

**Exclude:**
- About, contact, donate, support pages
- Login, signup, account, profile, settings pages
- Legal/policy pages (privacy, terms, cookies)
- Search, sitemap pages
- Tag/category index pages (unless they contain article listings)
- Author profile pages (unless explicitly content pages)
- Newsletter, subscription, advertising pages
- Social sharing links, comments sections, print versions
- Media galleries (unless site is specifically about media content)

Create appropriate allow/deny rules based on the URL patterns you discover during analysis.

**IMPORTANT: User explicit instructions ALWAYS override these defaults.**
If user requests specific sections (e.g., "include author pages"), create rules to include them.

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

**Step 1C: Iterative Section Drilling**
```bash
# Always ensure virtual environment is active
source .venv/bin/activate
# IMPORTANT: Run inspectors SEQUENTIALLY, not in parallel
# Each inspector overwrites the same analysis files

# Iteratively drill down through sections/subsections
bin/inspector --url <section_url>
# Read analysis, update sections.md
# If this page has subsections, inspect those next
bin/inspector --url <subsection_url>
# Continue drilling until you find pages that LINK TO final content
# Document the URL patterns of those final content pages
# STOP: Do NOT inspect the final content pages themselves
# Extractors handle content extraction
```

**Iterative Analysis Workflow:**
1. **Homepage Analysis** - Run inspector on main page, read `page.html` and `analysis.json`
2. **Extract ALL URLs** - Get complete URL list from homepage
3. **Identify Section URLs** - Find URLs that appear to be sections/navigation
4. **Drill Down Systematically**:
   - Visit each section URL with inspector
   - Check if it contains subsections or links to final content
   - If subsections exist, visit those next
   - Continue drilling until you find final content URL patterns
   - Document the patterns but DO NOT inspect the content pages
5. **Document Everything** - Update `sections.md` with complete navigation hierarchy and URL patterns
6. **Create Section Rules** - Generate rule files for each discovered section
7. **Consolidate** - Combine all rules into final spider JSON

**File Structure Created:**
```
data/website/analysis/
├── page.html           (preserved - homepage HTML)
├── analysis.json       (preserved - homepage analysis)
├── all_urls.txt        (all URLs extracted from homepage)
├── sections.md         (comprehensive section documentation with hierarchy)
├── section_rules_*.json (rule files for each section)
└── final_spider.json   (consolidated rules from all sections)
```

**Key Analysis Principles:**
1. **Extract complete URL list** - Get every link from homepage
2. **Drill down systematically** - Visit sections, then subsections, iteratively
3. **Stop at content discovery** - When you find final content URL patterns, document and stop
4. **Never inspect content** - Don't analyze individual content pages
5. **Document hierarchy** - Record the full navigation structure
6. **Preserve everything** - Keep all analysis files for reference

**Common Pitfalls to Avoid:**
- Don't assume homepage analysis is sufficient
- Don't create rules without understanding complete URL patterns
- **DO NOT inspect individual content pages** - Extractors handle content extraction
- **NEVER run multiple inspectors in parallel** - They overwrite the same analysis files
- **ALWAYS read and document analysis immediately** after each inspector run
- **NEVER delete analysis files** - Keep all analysis artifacts
- Focus on URL patterns and navigation hierarchy, not content structure
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
For each section documented in `sections.md`, create specific rule files based on discovered URL patterns.

**Step 2C: Consolidate into Final Spider JSON**
Combine all section rule files into a comprehensive spider definition.

#### Phase 2D: Final JSON Payload Structure

**Payload Structure:**
```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": [
    "URL patterns discovered during analysis"
  ],
  "rules": [
    {
      "allow": ["patterns for final content pages"],
      "deny": ["patterns to exclude from content extraction"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["patterns for navigation/listing pages"],
      "deny": ["patterns to avoid following"],
      "callback": null,
      "follow": true,
      "priority": 50
    },
    {
      "deny": ["patterns for utility pages to block completely"],
      "callback": null,
      "follow": false,
      "priority": 0
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
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

**IMPORTANT: Storage Mode Selection**

The `--limit` flag controls where data is saved:
- **With `--limit`**: Saves to database (for testing/verification with `show` command)
- **Without `--limit`**: Exports to files only (production mode, avoids database costs)

**Testing Mode (with --limit):**
```bash
# Test with limited items - saves to database
source .venv/bin/activate
./scrapai crawl website_name --limit 10
```

This will:
- Save data to database for quick verification
- Use `./scrapai show website_name` to check results
- Ideal for testing spider rules and content extraction

**Production Mode (without --limit):**
```bash
# Full scrape - exports to files, no database cost
source .venv/bin/activate
./scrapai crawl website_name
```

This will:
- Export to `data/website_name/crawl_TIMESTAMP.jsonl`
- Skip database to avoid storage costs
- Ideal for large-scale production scrapes

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

### 2.5. Queue System (Optional)

**The queue system is OPTIONAL. Use it when the user explicitly requests it.**

#### When to Use Queue vs Direct Processing

**Direct Processing (Default):**
```
User: "Add this website: https://example.com"
Claude Code: [Immediately processes: analyze → rules → import → test]
```

**Queue Mode (When User Requests):**
```
User: "Add climate.news to the queue"
Claude Code: [Adds to queue for later processing]

User: "Process the next one in the queue"
Claude Code: [Gets next item, then processes it]
```

#### Queue CLI Commands

**Add to Queue:**
```bash
source .venv/bin/activate && ./scrapai queue add <url> [-m "custom instruction"] [--priority N] [--project NAME]
```

**List Queue:**
```bash
# By default: shows 5 pending/processing items (excludes failed/completed)
source .venv/bin/activate && ./scrapai queue list

# Show more items
source .venv/bin/activate && ./scrapai queue list --limit 20

# Show all items including failed and completed
source .venv/bin/activate && ./scrapai queue list --all --limit 50

# Filter by specific status
source .venv/bin/activate && ./scrapai queue list --status pending
source .venv/bin/activate && ./scrapai queue list --status completed --limit 10
```

**Claim Next Item (Atomic - Safe for Concurrent Use):**
```bash
source .venv/bin/activate && ./scrapai queue next [--project NAME]
# Returns: ID, URL, custom_instruction, priority
```

**Update Status:**
```bash
source .venv/bin/activate && ./scrapai queue complete <id>
source .venv/bin/activate && ./scrapai queue fail <id> [-m "error message"]
source .venv/bin/activate && ./scrapai queue retry <id>
source .venv/bin/activate && ./scrapai queue remove <id>
```

**Bulk Cleanup:**
```bash
source .venv/bin/activate && ./scrapai queue cleanup --completed --force  # Remove all completed
source .venv/bin/activate && ./scrapai queue cleanup --failed --force     # Remove all failed
source .venv/bin/activate && ./scrapai queue cleanup --all --force        # Remove all completed and failed
```

#### Queue Workflow for Claude Code

**When user says "Add X to queue":**
1. Run `./scrapai queue add <url> -m "custom instruction if provided" --priority N`
2. Confirm addition with queue ID
3. Do NOT process immediately

**When user says "Process next in queue":**
1. Run `./scrapai queue next` to claim next item
2. Note the ID, URL, and custom_instruction from output
3. **If custom_instruction exists**: Use it to override CLAUDE.md defaults during analysis
4. Follow the full workflow (Phases 1-4):
   - Analysis & Section Documentation
   - Rule Generation
   - Import Spider
   - Test & Verify
5. **If successful**: `./scrapai queue complete <id>`
6. **If failed**: `./scrapai queue fail <id> -m "error description"`

#### Queue Features

- **Project Isolation**: Multiple projects can have separate queues (default: "default")
- **Priority System**: Higher priority items processed first (default: 5)
- **Custom Instructions**: Per-site instructions override CLAUDE.md defaults
- **Concurrent Safe**: Multiple team members can work simultaneously without conflicts
- **Atomic Claiming**: `queue next` uses PostgreSQL locking to prevent duplicate work
- **Audit Trail**: Tracks who's processing what, when completed/failed

#### Example: Queue with Custom Instructions

```
User: "Add climate.news to the queue and focus only on research articles"
Claude Code runs:
  ./scrapai queue add https://climate.news -m "Focus only on research articles" --priority 10

Later...

User: "Process the next one"
Claude Code runs:
  ./scrapai queue next
  # Output: ID: 1, URL: https://climate.news, Instructions: Focus only on research articles

  # During analysis, Claude Code remembers:
  # "USER INSTRUCTION: Focus only on research articles"
  # This overrides the default content focus rules

  # After successful processing:
  ./scrapai queue complete 1
```

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
-   `source .venv/bin/activate && ./scrapai crawl <name>` - Production scrape (exports to files, no DB cost).
-   `source .venv/bin/activate && ./scrapai crawl <name> --limit 10` - Test mode (saves to DB for verification).
    - **With `--limit`**: Saves to database, use `show` command to verify results
    - **Without `--limit`**: Exports to `data/<name>/crawl_TIMESTAMP.jsonl`, skips database

**Database Management:**
-   `source .venv/bin/activate && ./scrapai db migrate` - Run database migrations.
-   `source .venv/bin/activate && ./scrapai db current` - Show current migration revision.

**Queue Management (Optional):**
-   `source .venv/bin/activate && ./scrapai queue add <url> [-m "instruction"] [--priority N]` - Add website to queue.
-   `source .venv/bin/activate && ./scrapai queue list [--status pending|processing|completed|failed]` - List queue items.
-   `source .venv/bin/activate && ./scrapai queue next` - Claim next pending item (atomic).
-   `source .venv/bin/activate && ./scrapai queue complete <id>` - Mark item as completed.
-   `source .venv/bin/activate && ./scrapai queue fail <id> [-m "error"]` - Mark item as failed.
-   `source .venv/bin/activate && ./scrapai queue retry <id>` - Retry a failed item.
-   `source .venv/bin/activate && ./scrapai queue remove <id>` - Remove item from queue.
-   `source .venv/bin/activate && ./scrapai queue cleanup --completed --force` - Remove all completed items.
-   `source .venv/bin/activate && ./scrapai queue cleanup --failed --force` - Remove all failed items.
-   `source .venv/bin/activate && ./scrapai queue cleanup --all --force` - Remove all completed and failed items.

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