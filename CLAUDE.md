# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites using a database-first approach.

## For Claude Code Instances

**When asked to add any website, follow this Database-First Workflow:**

### CRITICAL: ALWAYS SEQUENTIAL, NEVER PARALLEL

**ABSOLUTE REQUIREMENT: Process ONE website at a time. NEVER use subagents, background tasks, or parallel processing.**

**FORBIDDEN - DO NOT USE:**
- Task tool / subagents (`Task`, `subagent_type`, etc.)
- Background tasks (`run_in_background=true`)
- Parallel agents (multiple agents running simultaneously)
- ANY form of concurrent processing

**REQUIRED - ALWAYS DO THIS:**
- Process one website at a time, start to finish
- Claim queue items one at a time using `source .venv/bin/activate && ./scrapai queue next --project <name>`
- Complete the FULL workflow for each website before moving to next
- All work done directly by Claude Code (no delegation to subagents)
- **ALWAYS specify `--project <name>` for ALL spider, queue, crawl, show, and export commands**

**Why Sequential Only:**
- Easier to debug, better visibility, no file conflicts, simpler troubleshooting

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

**Data Directory Configuration:**
- Analysis files are saved to `DATA_DIR/<project>/<spider>/analysis/` (default: `./data`)
- Customize in `.env`: `DATA_DIR=./data` (default) or `DATA_DIR=~/.scrapai/data` or any path
- Directory structure is created automatically by inspector - never use `mkdir`

### 2. Workflow

#### CRITICAL WORKFLOW RULES

**NEVER SKIP PHASES. NEVER RUSH. NEVER MARK STATUS PREMATURELY.**

You MUST complete EVERY step of EVERY phase before proceeding to the next phase.

**COMMAND EXECUTION RULES:**
- **NEVER chain multiple operations together** (except venv activation)
- **NEVER use `grep`, `rg`, `awk`, `sed`, `head`, `tail`, or pipes (`|`) in Bash** - use the dedicated Grep, Read, and Glob tools instead
- **NEVER use `mkdir` to create directories** - inspector automatically creates `data/<project>/<spider>/analysis/` directory structure
- **ALWAYS run operations ONE AT A TIME in separate bash calls**
- **OK to use: `source .venv/bin/activate && <single command>`** (venv + one command is acceptable)
- **WAIT for each command to complete before running the next**
- **READ the output of each command before proceeding**
- **To search file contents**: Use the Grep tool (NOT `grep` or `rg` in Bash)
- **To read files**: Use the Read tool (NOT `cat`, `head`, `tail` in Bash)
- **To find files**: Use the Glob tool (NOT `find` or `ls` in Bash)

**Bad Example (DO NOT DO THIS):**
```bash
source .venv/bin/activate && bin/inspector --url https://example.com && ./scrapai extract-urls ... && cat file.txt | grep something
```

**Good Example (DO THIS):**
```bash
source .venv/bin/activate && bin/inspector --url https://example.com --project myproject
```
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/myproject/site/analysis/page.html -o data/myproject/site/analysis/urls.txt
```
```bash
source .venv/bin/activate && cat data/myproject/site/analysis/urls.txt
```

**DO NOT:**
- Skip analysis and jump straight to rule creation
- Create rules without reading ALL URLs from the homepage
- Mark queue items as complete before testing the spider
- Rush through phases to "finish quickly"
- Assume you know the site structure without full analysis
- Skip verification steps

**DO:**
- Complete Phase 1 (Analysis) ENTIRELY before starting Phase 2 (Rules)
- Complete Phase 2 (Rules) ENTIRELY before starting Phase 3 (Import)
- Complete Phase 3 (Import) ENTIRELY before starting Phase 4 (Test)
- Only mark status as complete AFTER successful test verification
- Take time to be thorough - quality over speed

**STATUS MARKING RULE:**
ONLY mark queue items as complete (`source .venv/bin/activate && ./scrapai queue complete <id>`) when:
1. Phase 1: Full analysis documented in sections.md
2. Phase 2: All section rules created and consolidated into final_spider.json
3. Phase 3: Spider JSON files prepared (test_spider.json and final_spider.json)
4. Phase 4A: Extraction quality verified on test spider
5. Phase 4B: Final spider imported successfully (ready for production)

If ANY phase is incomplete or test fails, DO NOT mark as complete.

---

#### Phase 1: Analysis & Section Documentation

**Complete FULL site analysis before creating ANY rules.**

**Before starting Phase 1, read `docs/analysis-workflow.md` for the detailed procedure.**

Summary: Run inspector on homepage -> Extract all URLs -> Categorize URL types -> Drill down into sections one at a time -> Document everything in sections.md -> Only then proceed to rule creation.

**CRITICAL PRINCIPLE: BE INCLUSIVE, NOT RESTRICTIVE**

**When in doubt, INCLUDE IT.** We want to capture ALL substantive content.

**Exclusion Policy (MINIMAL LIST ONLY):**

ONLY exclude these specific sections and their subsections:
- **About pages** (about, team, leadership, company info, history)
- **Contact pages** (contact, email, phone, address, support)
- **Donate pages** (donate, contribute, support, funding)
- **Account pages** (login, signup, register, account, profile)
- **Legal pages** (privacy, terms, cookies, legal)
- **Search pages** (search functionality pages)
- **PDF files** (ignore for now, but note their presence as potential content)

**Everything else should be explored and considered for inclusion:**
- News, articles, blog posts, research, reports, publications, white papers
- Policy documents, analysis, briefs, educational content, tutorials, guides
- Case studies, investigations, speeches, testimonies, transcripts
- Environmental reports, technical documentation, shareholder information
- Industry analysis, market reports, **ANY section with substantive written content**

**Rule of Thumb:**
- If it's clearly about/contact/donate/account/legal/search -> EXCLUDE
- Everything else -> EXPLORE and likely INCLUDE
- When uncertain -> **ERR ON THE SIDE OF INCLUSION**

**IMPORTANT: User explicit instructions ALWAYS override these defaults.**

#### Phase 2: Rule Generation & Extraction Testing

**Read `docs/analysis-workflow.md` for Phase 2, 2.5, and 2D details.**

Summary: Use sections.md to create rules -> Test generic extractors (newspaper/trafilatura) on an article -> If they fail, discover custom CSS selectors -> Create final_spider.json with rules + extraction config.

**Testing Workflow:**
1. **Test Generic Extractors First**: Inspect an article and check if newspaper/trafilatura extract correctly
2. **Only If They Fail**: Discover custom CSS selectors by inspecting HTML structure
3. **Configure Extractor Order**: Set `EXTRACTOR_ORDER` based on what works

See `docs/extractors.md` for full selector documentation, examples, and discovery principles.

#### Phase 3: Prepare Spider Configuration

**CRITICAL: Include source_url in your spider JSON**
When processing from queue, ALWAYS include the original queue URL as `"source_url"` in your `final_spider.json`:
```json
{
  "name": "spider_name",
  "source_url": "https://original-queue-url.com",
  "allowed_domains": [...],
  "start_urls": [...]
}
```

**DO NOT import yet.** Importing happens in Phase 4 after you've created both test_spider.json and final_spider.json.

#### Phase 4: Execution & Verification

**CRITICAL: Test extraction quality BEFORE testing navigation.**

**Read `docs/analysis-workflow.md` Phase 4 for full two-step testing process.**

**Step 4A: Test extraction on 5 specific article URLs first**
- Collect 5 article URLs from your analysis
- Create test_spider.json with only those URLs and `follow: false`
- Import, crawl, and verify extraction quality
- If quality is bad, fix extractors/selectors and re-test
- Only proceed to Step 4B when extraction is confirmed good

**Step 4B: Import final spider for production**
- Delete test spider
- Import final_spider.json with navigation rules enabled
- Spider is now ready for production use

**Production Mode:**
```bash
source .venv/bin/activate && ./scrapai crawl website_name --project <name>
```

### 2.5. Queue System (Optional)

**The queue system is OPTIONAL. Use it when the user explicitly requests it.**

**Read `docs/queue.md` for full queue documentation, CLI commands, and workflow.**

**CRITICAL: ALWAYS specify `--project` for ALL queue operations.**

Quick reference:
- `source .venv/bin/activate && ./scrapai queue add <url> --project <name> [-m "instruction"] [--priority N]` - Add to queue
- `source .venv/bin/activate && ./scrapai queue next --project <name>` - Claim next item
- `source .venv/bin/activate && ./scrapai queue complete <id>` - Mark complete (ID is unique, no --project needed)
- `source .venv/bin/activate && ./scrapai queue fail <id> [-m "error"]` - Mark failed (ID is unique, no --project needed)

### 3. CLI Reference

**Environment Setup:**
- `./scrapai verify` - Verify environment setup
- `./scrapai setup` - Setup virtual environment and initialize database

**IMPORTANT: All other CLI commands require virtual environment activation.**

**🚨 CRITICAL: ALWAYS specify `--project <name>` for ALL spider, queue, crawl, show, and export commands. Never omit it.**

**Spider Management:**
- `source .venv/bin/activate && ./scrapai spiders list --project <name>` - List spiders in project (**always specify --project**)
- `source .venv/bin/activate && ./scrapai spiders import <file> --project <name>` - Import/Update spider (**always specify --project**)
- `source .venv/bin/activate && ./scrapai spiders delete <name> --project <name>` - Delete spider from project (**always specify --project**)

**Crawling:**
- `source .venv/bin/activate && ./scrapai crawl <name> --project <name>` - Production scrape (**always specify --project**)
- `source .venv/bin/activate && ./scrapai crawl <name> --project <name> --limit 5` - Test mode (**always specify --project**)
  - **With `--limit`**: Saves to database, use `show` command to verify results
  - **Without `--limit`**: Exports to `data/<name>/crawl_TIMESTAMP.jsonl`, skips database

**Database Management:**
- `source .venv/bin/activate && ./scrapai db migrate` - Run database migrations
- `source .venv/bin/activate && ./scrapai db current` - Show current migration revision

**Queue Management (Optional):**
- `source .venv/bin/activate && ./scrapai queue add <url> --project <name> [-m "instruction"] [--priority N]` - Add to queue (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue bulk <file.csv|file.json> --project <name> [--priority N]` - Bulk add from CSV/JSON (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue list --project <name> [--status pending|processing|completed|failed] [--count]` - List items or get count (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue next --project <name>` - Claim next pending item (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue complete <id>` - Mark completed (ID is globally unique)
- `source .venv/bin/activate && ./scrapai queue fail <id> [-m "error"]` - Mark failed (ID is globally unique)
- `source .venv/bin/activate && ./scrapai queue retry <id>` - Retry failed item (ID is globally unique)
- `source .venv/bin/activate && ./scrapai queue remove <id>` - Remove from queue (ID is globally unique)
- `source .venv/bin/activate && ./scrapai queue cleanup --completed --force --project <name>` - Remove all completed (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue cleanup --failed --force --project <name>` - Remove all failed (**always specify --project**)
- `source .venv/bin/activate && ./scrapai queue cleanup --all --force --project <name>` - Remove all completed and failed (**always specify --project**)

**Data Inspection:**
- `source .venv/bin/activate && ./scrapai show <spider_name> --project <name>` - Show recent articles (**always specify --project**)
- `source .venv/bin/activate && ./scrapai show <spider_name> --project <name> --limit 10` - Show specific number (**always specify --project**)
- `source .venv/bin/activate && ./scrapai show <spider_name> --project <name> --url pattern` - Filter by URL (**always specify --project**)
- `source .venv/bin/activate && ./scrapai show <spider_name> --project <name> --text "climate"` - Search title or content (**always specify --project**)
- `source .venv/bin/activate && ./scrapai show <spider_name> --project <name> --title "climate"` - Search titles only (**always specify --project**)

Note: `--project` is technically optional for `show` and `export` commands (defaults to first match), but **strongly recommended** to avoid confusion when spider names exist in multiple projects.

**Data Export:**

**IMPORTANT: Only export data when the user EXPLICITLY requests it. Never export proactively.**

When the user requests an export:
1. **Ask which format they want**: CSV, JSON, JSONL, or Parquet
2. **Run the export command** with the chosen format
3. **Provide the full file path** to the user after export completes

Export commands (**always specify --project**):
- `source .venv/bin/activate && ./scrapai export <spider_name> --project <name> --format csv` - Export to CSV
- `source .venv/bin/activate && ./scrapai export <spider_name> --project <name> --format json --limit 100` - Export limited records
- `source .venv/bin/activate && ./scrapai export <spider_name> --project <name> --format parquet --title "climate"` - Export with filters
- `source .venv/bin/activate && ./scrapai export <spider_name> --project <name> --format jsonl --output /path/to/file.jsonl` - Custom output path

Export behavior:
- Default location: `data/<spider_name>_export_<timestamp>.<format>` (timestamp format: ddmmyyyy_HHMMSS)
- Custom location: Use `--output` to specify any path
- Filters work with export: `--url`, `--title`, `--text`, `--limit`
- Each export gets a unique timestamped filename (no overwrites)

## Extractor Options

**Test generic extractors first. Only use custom selectors if they fail.**

**Analysis Workflow:**
1. Inspect article page with `bin/inspector`
2. Test if newspaper/trafilatura extract correctly
3. If yes → use generic extractors (`EXTRACTOR_ORDER: ["newspaper", "trafilatura"]`)
4. If no → discover custom selectors and use `EXTRACTOR_ORDER: ["custom", "newspaper", "trafilatura"]`

**Read `docs/extractors.md` for full documentation:** selector discovery workflow, BeautifulSoup analysis, examples (news/e-commerce/forum), extractor order config, Playwright wait, and infinite scroll support.

**Read `docs/cloudflare.md` for Cloudflare bypass:** settings, session persistence, wait times, and troubleshooting.

Quick reference for spider settings:

**With Custom Selectors (when generic extractors fail):**
```json
{
  "settings": {
    "EXTRACTOR_ORDER": ["custom", "newspaper", "trafilatura"],
    "CUSTOM_SELECTORS": { "title": "h1.x", "content": "div.y", "author": "span.z", "date": "time.w" }
  }
}
```

**Without Custom Selectors (when generic extractors work):**
```json
{
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura", "playwright"]
  }
}
```

**For JS-Rendered Sites:**
```json
{
  "settings": {
    "EXTRACTOR_ORDER": ["playwright", "custom"],
    "CUSTOM_SELECTORS": { ... },
    "PLAYWRIGHT_WAIT_SELECTOR": ".article-content",
    "PLAYWRIGHT_DELAY": 5
  }
}
```

**For Cloudflare-Protected Sites:**
```json
{
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5
  }
}
```

**Other Settings:**
- `INFINITE_SCROLL`: Enable infinite scroll (default: false)
- `MAX_SCROLLS`: Maximum scrolls when infinite scroll enabled (default: 5)
- `SCROLL_DELAY`: Delay between scrolls in seconds (default: 1.0)

## Core Principles
- **Database First**: All configuration lives in the database.
- **Agent Driven**: Agents use CLI tools to manage the DB.
- **Generic Spider**: The system uses a single `DatabaseSpider` that loads rules dynamically.
- **Smart Extraction**: Content extraction is handled automatically with multiple fallback strategies.
- **Database Persistence**: Scraped items are batched and saved efficiently to the PostgreSQL database.

## What Claude Code Can Modify
- **Allowed**:
  - Creating/Editing JSON payloads.
  - Running CLI commands (`scrapai`, `init_db.py`).
  - Updating `.env` (if requested).
- **Not Allowed**:
  - Creating `.py` spider files (Legacy).
  - Modifying core framework code.

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
