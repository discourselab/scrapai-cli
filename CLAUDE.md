# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites using a database-first approach.

## For Claude Code Instances

**When asked to add any website, follow this Database-First Workflow:**

### CRITICAL: Adaptive Queue Processing (Parallel or Sequential)

**When user requests processing multiple websites:**

**Step 1: Detect capabilities and inform user**
- Check if Task tool is available
- **IMMEDIATELY tell user which mode you're using:**
  - ✅ "Task tool available - using parallel processing (max 5 concurrent)"
  - ℹ️ "Task tool not available - using sequential processing"

**Example User Experience:**
```
User: "Process next 12 sites from brown_v2 queue"

Agent: "✓ Task tool available - using parallel processing (max 5 concurrent)"
Agent: "Total: 12 sites → Processing in 3 batches (5 + 5 + 2)"
Agent: ""
Agent: "📦 Batch 1/3: Processing 5 sites in parallel..."
Agent: "  ⏳ climate.news - Phase 1 started"
Agent: "  ⏳ factcheck.org - Phase 1 started"
Agent: "  ⏳ politifact.com - Phase 1 started"
Agent: "  ⏳ snopes.com - Phase 1 started"
Agent: "  ⏳ fullfact.org - Phase 1 started"
Agent: ""
[... progress updates ...]
Agent: "  ✓ factcheck.org completed"
Agent: "  ✓ snopes.com completed"
Agent: "  ✗ climate.news failed: extraction quality poor"
Agent: "  ✓ politifact.com completed"
Agent: "  ✓ fullfact.org completed"
Agent: ""
Agent: "📊 Batch 1 complete: 4 succeeded, 1 failed"
Agent: ""
Agent: "📦 Batch 2/3: Processing next 5 sites in parallel..."
[... continues ...]
```

**Step 2: Process websites with frequent updates**

**🚨 ABSOLUTE LIMITS (NEVER EXCEED):**
- **MAXIMUM 5 websites in parallel at any time** (HARD LIMIT - NO EXCEPTIONS)
- If user requests more than 5, process in batches of 5
- Example: "Process 12 sites" → Batch 1 (5 parallel) → Batch 2 (5 parallel) → Batch 3 (2 parallel)

**If Task tool available (Parallel Mode):**
1. **Announce batch:** "Batch 1: Processing 5 sites in parallel..."
2. **Claim items:** Get next 5 items from queue (max 5!)
3. **Spawn Task agents:** One Task agent per website (max 5 concurrent)
   - **DO NOT use `run_in_background=true`** - Wait for agents to complete
   - Agents run in parallel with each other, but main agent waits for all
4. **Give regular updates:** Report progress as agents work
   - "Started: climate.news (Phase 1)"
   - "Progress: factcheck.org completed Phase 2"
   - "Completed: snopes.com ✓"
5. **Wait for batch:** All 5 Task agents complete before next batch
6. **Report results:** "Batch 1: 4 succeeded, 1 failed"
7. **Repeat:** If more items remain, process next batch of max 5

**If Task tool NOT available (Sequential Mode):**
1. **Announce mode:** "Processing sequentially (one at a time)..."
2. **Process each website:** Claim → Phase 1-4 → Mark complete
3. **Give updates after each phase:** "climate.news: Completed Phase 2"
4. **Report completion:** "Completed: climate.news ✓ (3/10 done)"
5. **Repeat:** Until all requested sites are processed

**CRITICAL RULES (APPLY TO BOTH MODES):**
- **Phases within each website MUST be sequential:** Phase 1 → 2 → 3 → 4 (NEVER parallel)
- **Each website is independent:** Different data directories, different spiders
- **Always specify --project:** ALL spider, queue, crawl, show, export commands need --project
- **Update user frequently:** Don't go silent - tell user what's happening every 1-2 minutes
- **Report failures immediately:** If a site fails, tell user right away with error details

**Why This Approach:**
- Parallel: 3-5x faster when available, handles batch work efficiently
- Sequential: Works everywhere, easier to debug, better visibility
- Adaptive: Same command works with any AI agent, optimized automatically

---

### Task Agent Instructions (Parallel Mode Only)

**When spawning Task agents for parallel processing:**

**Task Agent Prompt (what to tell each Task agent):**
```
Process this website from the queue:

Queue Item ID: <id>
Website URL: <url>
Project: <project_name>
Custom Instructions: <custom_instruction if any>

Complete the FULL workflow (Phases 1-4):
1. Phase 1: Analysis & Section Documentation
2. Phase 2: Rule Generation & Extraction Testing
3. Phase 3: Prepare Spider Configuration (include source_url)
4. Phase 4A: Test extraction quality (import test_spider, verify)
5. Phase 4B: Import final spider

CRITICAL: Mark your own status before reporting back:
- If successful: Run `queue complete <id>`
- If failed: Run `queue fail <id> -m "error description"`

Then report back to main agent:
- Status: SUCCESS or FAILED
- Spider name: <name>
- Queue item ID: <id>
- Summary: Brief description of what was completed or what failed
- Any errors encountered

Follow ALL instructions in CLAUDE.md for each phase.
```

**Main Agent - After Task agents complete:**
1. **Collect results from each Task agent**
2. **Report summary to user:**
   - For each successful: "✓ climate.news completed successfully"
   - For each failed: "✗ factcheck.org failed: [error details]"
3. **Summary report:** "Batch complete: 4/5 succeeded, 1/5 failed"

**Note:** Task agents mark their own queue status - main agent only reports results to user.

---

### CRITICAL: Allowed Tools and Commands

**🚨 STRICT REQUIREMENT: Only use tools and commands available in this repository.**

**ALLOWED - Repository Tools:**
- `./scrapai` - Main CLI tool (all commands: spider management, queue, crawl, export, show, inspect, analyze)

**ALLOWED - Claude Code Tools:**
- **Read** - Read file contents (use instead of cat/head/tail)
- **Write** - Write new files (use instead of echo >/cat <<EOF)
- **Edit** - Edit existing files (use instead of sed/awk)
- **Glob** - Find files by pattern (use instead of find/ls)
- **Grep** - Search file contents (use instead of grep/rg)
- **Bash** - Execute shell commands (ONLY for git, npm, docker, etc.)
- **Task** - Spawn subagents for parallel processing (when available)

**FORBIDDEN - DO NOT USE:**
- ❌ `fetch` - not available in this repo
- ❌ `curl` - use ./scrapai inspect instead
- ❌ `wget` - use ./scrapai inspect instead
- ❌ `grep`, `rg`, `awk`, `sed` in Bash - use Grep tool instead
- ❌ `cat`, `head`, `tail` in Bash - use Read tool instead
- ❌ `find`, `ls` for searching - use Glob tool instead
- ❌ `echo >`, `cat <<EOF` for files - use Write/Edit tools instead
- ❌ `mkdir` - directories created automatically by inspector
- ❌ Any external tools not listed in "ALLOWED" section

**Why This Restriction:**
- Ensures commands work in any environment
- Prevents permission issues and missing dependencies
- Uses optimized tools designed for the repo's workflow
- Maintains consistency across different systems

---

### 1. Environment Notes

**If user needs setup help:** Direct them to [docs/onboarding.md](docs/onboarding.md) - don't walk them through setup yourself.

**Key Facts (you don't need to do anything about these):**
- Virtual environment activation is automatic - commands just work
- SQLite is the default database (no PostgreSQL setup required)
- Data directory structure is auto-created by inspector (never use `mkdir`)

**Database Commands:**
- `./scrapai db migrate` - Run pending migrations
- `./scrapai db current` - Show current migration state

**Data Directory:**
- Analysis files saved to `DATA_DIR/<project>/<spider>/analysis/` (default: `./data`)
- Configured in `.env` if user wants to change location

### 2. Workflow

#### CRITICAL WORKFLOW RULES

**NEVER SKIP PHASES. NEVER RUSH. NEVER MARK STATUS PREMATURELY.**

You MUST complete EVERY step of EVERY phase before proceeding to the next phase.

**COMMAND EXECUTION RULES:**
- **ONLY use allowed tools** - See "Allowed Tools and Commands" section above (NO fetch, curl, wget, etc.)
- **NEVER chain multiple operations together** - run commands one at a time
- **NEVER use `grep`, `rg`, `awk`, `sed`, `head`, `tail`, or pipes (`|`) in Bash** - use the dedicated Grep, Read, and Glob tools instead
- **NEVER use `mkdir` to create directories** - inspector automatically creates `data/<project>/<spider>/analysis/` directory structure
- **ALWAYS run operations ONE AT A TIME in separate bash calls**
- **WAIT for each command to complete before running the next**
- **READ the output of each command before proceeding**
- **To search file contents**: Use the Grep tool (NOT `grep` or `rg` in Bash)
- **To read files**: Use the Read tool (NOT `cat`, `head`, `tail` in Bash)
- **To find files**: Use the Glob tool (NOT `find` or `ls` in Bash)
- **For web inspection**: Use `./scrapai inspect` (NOT curl, wget, fetch)

**Note:** Virtual environment activation is automatic - you don't need `source .venv/bin/activate` anymore!

**Bad Example (DO NOT DO THIS):**
```bash
./scrapai inspect https://example.com && ./scrapai extract-urls ... && cat file.txt | grep something
```

**Good Example (DO THIS):**
```bash
./scrapai inspect https://example.com --project myproject
```
```bash
./scrapai extract-urls --file data/myproject/site/analysis/page.html -o data/myproject/site/analysis/urls.txt
```
```bash
cat data/myproject/site/analysis/urls.txt
```

**🚨 CRITICAL: Piping Input to Commands**

When you need to pipe input to a command (like "y" for confirmation):

**✅ CORRECT:**
```bash
echo "y" | ./scrapai spiders delete name --project proj
```

This works because the pipe sends "y" directly to the scrapai command.

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
ONLY mark queue items as complete (`./scrapai queue complete <id>`) when:
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
- Create test_spider.json with `"name": "website_name"`, 5 URLs, and `follow: false`
- Import: `./scrapai spiders import test_spider.json --project <name>`
- Crawl: `./scrapai crawl website_name --limit 5 --project <name>`
- Verify: `./scrapai show website_name --limit 5 --project <name>`
- If quality is bad, fix extractors/selectors and re-test
- Only proceed to Step 4B when extraction is confirmed good

**Step 4B: Import final spider for production**
- Create final_spider.json with **same name:** `"name": "website_name"` (full navigation rules)
- Import: `./scrapai spiders import final_spider.json --project <name>`
- **Import automatically updates the existing spider** (no deletion needed!)
- Test data from Step 4A is preserved
- Spider is now ready for production use

**Production Mode:**
```bash
./scrapai crawl website_name --project <name>
```

### 2.5. Queue System (Optional)

**The queue system is OPTIONAL. Use it when the user explicitly requests it.**

**Read `docs/queue.md` for full queue documentation, CLI commands, and workflow.**

**CRITICAL: ALWAYS specify `--project` for ALL queue operations.**

Quick reference:
- `./scrapai queue add <url> --project <name> [-m "instruction"] [--priority N]` - Add to queue
- `./scrapai queue next --project <name>` - Claim next item
- `./scrapai queue complete <id>` - Mark complete (ID is unique, no --project needed)
- `./scrapai queue fail <id> [-m "error"]` - Mark failed (ID is unique, no --project needed)

### 3. CLI Reference

**Environment Setup:**
- `./scrapai verify` - Verify environment setup
- `./scrapai setup` - Setup virtual environment and initialize database

**IMPORTANT: All other CLI commands require virtual environment activation.**

**🚨 CRITICAL: ALWAYS specify `--project <name>` for ALL spider, queue, crawl, show, and export commands. Never omit it.**

**Spider Management:**
- `./scrapai spiders list --project <name>` - List spiders in project (**always specify --project**)
- `./scrapai spiders import <file> --project <name>` - Import/Update spider (**always specify --project**)
- `./scrapai spiders delete <name> --project <name>` - Delete spider from project (**always specify --project**)

**Crawling:**
- `./scrapai crawl <name> --project <name>` - Production scrape (**always specify --project**)
- `./scrapai crawl <name> --project <name> --limit 5` - Test mode (**always specify --project**)
  - **With `--limit`**: Saves to database, use `show` command to verify results
  - **Without `--limit`**: Exports to `data/<name>/crawl_TIMESTAMP.jsonl`, skips database

**Database Management:**
- `./scrapai db migrate` - Run database migrations
- `./scrapai db current` - Show current migration revision

**Queue Management (Optional):**
- `./scrapai queue add <url> --project <name> [-m "instruction"] [--priority N]` - Add to queue (**always specify --project**)
- `./scrapai queue bulk <file.csv|file.json> --project <name> [--priority N]` - Bulk add from CSV/JSON (**always specify --project**)
- `./scrapai queue list --project <name> [--status pending|processing|completed|failed] [--count]` - List items or get count (**always specify --project**)
- `./scrapai queue next --project <name>` - Claim next pending item (**always specify --project**)
- `./scrapai queue complete <id>` - Mark completed (ID is globally unique)
- `./scrapai queue fail <id> [-m "error"]` - Mark failed (ID is globally unique)
- `./scrapai queue retry <id>` - Retry failed item (ID is globally unique)
- `./scrapai queue remove <id>` - Remove from queue (ID is globally unique)
- `./scrapai queue cleanup --completed --force --project <name>` - Remove all completed (**always specify --project**)
- `./scrapai queue cleanup --failed --force --project <name>` - Remove all failed (**always specify --project**)
- `./scrapai queue cleanup --all --force --project <name>` - Remove all completed and failed (**always specify --project**)

**Data Inspection:**
- `./scrapai show <spider_name> --project <name>` - Show recent articles (**always specify --project**)
- `./scrapai show <spider_name> --project <name> --limit 10` - Show specific number (**always specify --project**)
- `./scrapai show <spider_name> --project <name> --url pattern` - Filter by URL (**always specify --project**)
- `./scrapai show <spider_name> --project <name> --text "climate"` - Search title or content (**always specify --project**)
- `./scrapai show <spider_name> --project <name> --title "climate"` - Search titles only (**always specify --project**)

Note: `--project` is technically optional for `show` and `export` commands (defaults to first match), but **strongly recommended** to avoid confusion when spider names exist in multiple projects.

**Data Export:**

**IMPORTANT: Only export data when the user EXPLICITLY requests it. Never export proactively.**

When the user requests an export:
1. **Ask which format they want**: CSV, JSON, JSONL, or Parquet
2. **Run the export command** with the chosen format
3. **Provide the full file path** to the user after export completes

Export commands (**always specify --project**):
- `./scrapai export <spider_name> --project <name> --format csv` - Export to CSV
- `./scrapai export <spider_name> --project <name> --format json --limit 100` - Export limited records
- `./scrapai export <spider_name> --project <name> --format parquet --title "climate"` - Export with filters
- `./scrapai export <spider_name> --project <name> --format jsonl --output /path/to/file.jsonl` - Custom output path

Export behavior:
- Default location: `data/<spider_name>_export_<timestamp>.<format>` (timestamp format: ddmmyyyy_HHMMSS)
- Custom location: Use `--output` to specify any path
- Filters work with export: `--url`, `--title`, `--text`, `--limit`
- Each export gets a unique timestamped filename (no overwrites)

## Extractor Options

**Test generic extractors first. Only use custom selectors if they fail.**

**Analysis Workflow:**
1. Inspect article page with `./scrapai inspect`
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
