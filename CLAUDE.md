# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites using a database-first approach.

## For Claude Code Instances

**When asked to add any website, follow this Database-First Workflow:**

### 🚨 CRITICAL: ALWAYS SEQUENTIAL, NEVER PARALLEL 🚨

**ABSOLUTE REQUIREMENT: Process ONE website at a time. NEVER use subagents, background tasks, or parallel processing.**

**❌ FORBIDDEN - DO NOT USE:**
- ❌ Task tool / subagents (`Task`, `subagent_type`, etc.)
- ❌ Background tasks (`run_in_background=true`)
- ❌ Parallel agents (multiple agents running simultaneously)
- ❌ ANY form of concurrent processing

**✅ REQUIRED - ALWAYS DO THIS:**
- ✅ Process one website at a time, start to finish
- ✅ Claim queue items one at a time using `./scrapai queue next`
- ✅ Complete the FULL workflow for each website before moving to next
- ✅ All work done directly by Claude Code (no delegation to subagents)

**Why Sequential Only:**
- **Easier to debug** - Clear error messages and output
- **Better visibility** - See exactly what's happening at each step
- **No conflicts** - Avoid file overwrites and race conditions
- **Simpler troubleshooting** - One thing at a time

**Example - Processing Multiple Queue Items:**
```
User: "Process the next 10 items in the queue"
Claude Code:
  1. Claims item 1 with `./scrapai queue next`
  2. Completes full workflow (analyze → rules → import → test → mark complete)
  3. Claims item 2 with `./scrapai queue next`
  4. Completes full workflow (analyze → rules → import → test → mark complete)
  5. ... continues one by one until all 10 are done
```

**❌ WRONG - DO NOT DO THIS:**
```
User: "Process the next 10 items"
Claude Code: [Launches 10 Task agents in parallel] ← NEVER DO THIS
```

**✅ CORRECT - DO THIS:**
```
User: "Process the next 10 items"
Claude Code: [Processes each item sequentially, one complete workflow at a time]
```

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

#### ⚠️ CRITICAL WORKFLOW RULES ⚠️

**NEVER SKIP PHASES. NEVER RUSH. NEVER MARK STATUS PREMATURELY.**

You MUST complete EVERY step of EVERY phase before proceeding to the next phase. Common mistakes to avoid:

**COMMAND EXECUTION RULES:**
- ❌ **NEVER chain multiple operations together** (except venv activation)
- ❌ **NEVER use grep, pipes (`|`), or complex one-liners**
- ✅ **ALWAYS run operations ONE AT A TIME in separate bash calls**
- ✅ **OK to use: `source .venv/bin/activate && <single command>`** (venv + one command is acceptable)
- ✅ **WAIT for each command to complete before running the next**
- ✅ **READ the output of each command before proceeding**

**Bad Example (DO NOT DO THIS):**
```bash
source .venv/bin/activate && bin/inspector --url https://example.com && ./scrapai extract-urls ... && cat file.txt | grep something
```

**Good Example (DO THIS):**
```bash
# Activate venv + single command is OK
source .venv/bin/activate && bin/inspector --url https://example.com
```
```bash
# Next operation - separate bash call
source .venv/bin/activate && ./scrapai extract-urls --file data/site/page.html -o data/site/urls.txt
```
```bash
# Next operation - separate bash call
cat data/site/urls.txt
```

❌ **DO NOT:**
- Skip analysis and jump straight to rule creation
- Create rules without reading ALL URLs from the homepage
- Mark queue items as complete before testing the spider
- Rush through phases to "finish quickly"
- Assume you know the site structure without full analysis
- Skip verification steps

✅ **DO:**
- Complete Phase 1 (Analysis) ENTIRELY before starting Phase 2 (Rules)
- Complete Phase 2 (Rules) ENTIRELY before starting Phase 3 (Import)
- Complete Phase 3 (Import) ENTIRELY before starting Phase 4 (Test)
- Only mark status as complete AFTER successful test verification
- Take time to be thorough - quality over speed

**STATUS MARKING RULE:**
ONLY mark queue items as complete (`./scrapai queue complete <id>`) when:
1. ✅ Phase 1: Full analysis documented in sections.md
2. ✅ Phase 2: All section rules created and consolidated into final_spider.json
3. ✅ Phase 3: Spider successfully imported to database
4. ✅ Phase 4: Test crawl run and results verified with `./scrapai show`

If ANY phase is incomplete or test fails, DO NOT mark as complete.

---

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
**CRITICAL: Review the COMPLETE URL list - do not just search for keywords.**

Manually review ALL URLs from `all_urls.txt` and identify:
- **Content pages**: ANY substantive content (articles, blog posts, reports, publications, research papers, speeches, newsletters, policy briefs, etc.)
- **Navigation/listing pages**: Pages that link to content
- **Utility pages**: Pages to exclude (about, contact, etc.)
- **PDF content**: Note if site has PDFs (we skip these for now, but acknowledge as content)
- **Any other URL patterns**: Document everything you find

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

**CRITICAL PRINCIPLE: BE INCLUSIVE, NOT RESTRICTIVE**

**When in doubt, INCLUDE IT.** We want to capture ALL substantive content. The extractors will handle the actual content extraction.

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
- News, articles, blog posts
- Research, reports, publications, white papers
- Policy documents, analysis, briefs
- Educational content, tutorials, guides
- Case studies, investigations
- Speeches, testimonies, transcripts
- Environmental reports, technical documentation
- Shareholder information, financial reports
- Industry analysis, market reports
- **ANY section with substantive written content**

**Rule of Thumb:**
- If it's clearly about/contact/donate/account/legal/search → EXCLUDE
- Everything else → EXPLORE and likely INCLUDE
- When uncertain → **ERR ON THE SIDE OF INCLUSION**

**IMPORTANT: User explicit instructions ALWAYS override these defaults.**
If user requests specific sections, follow their instructions.

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

⚠️ **CRITICAL: SEQUENTIAL PROCESSING ONLY** ⚠️
- **NEVER run multiple inspectors in parallel**
- Each inspector overwrites `page.html` and `analysis.json`
- **ALWAYS complete this cycle for EACH section:**
  1. Run ONE inspector
  2. Read the output files immediately
  3. Document findings in sections.md
  4. Only then move to next section

```bash
# Always ensure virtual environment is active
source .venv/bin/activate

# Example: Sequential section drilling (ONE at a time)
# Step 1: Inspect first section
bin/inspector --url https://example.com/news/
# Step 2: IMMEDIATELY read and document before moving on
cat data/example_com/analysis/analysis.json
./scrapai extract-urls --file data/example_com/analysis/page.html --output data/example_com/analysis/news_urls.txt
# Step 3: Update sections.md with findings

# Step 4: Now inspect next section
bin/inspector --url https://example.com/policy/
# Step 5: IMMEDIATELY read and document
cat data/example_com/analysis/analysis.json
./scrapai extract-urls --file data/example_com/analysis/page.html --output data/example_com/analysis/policy_urls.txt
# Step 6: Update sections.md with findings

# Continue this pattern for each section
# STOP: Do NOT inspect the final content pages themselves
# Extractors handle content extraction
```

**Iterative Analysis Workflow:**
1. **Homepage Analysis** - Run inspector on main page, read `page.html` and `analysis.json`
2. **Extract ALL URLs** - Get complete URL list from homepage
3. **Identify Section URLs** - Find URLs that appear to be sections/navigation
4. **Drill Down Systematically (ONE SECTION AT A TIME)**:
   - Visit ONE section URL with inspector
   - Read output files immediately and document findings
   - Check if it contains subsections or links to final content
   - If subsections exist, visit those next (one at a time)
   - Continue drilling until you find final content URL patterns
   - Document the patterns but DO NOT inspect the content pages
   - **NEVER run multiple inspectors in parallel - they overwrite the same files**
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
- **NEVER run multiple inspectors in parallel** - They ALL overwrite `page.html` and `analysis.json`
- **Process sections sequentially**: Run inspector → Read files → Document → Next section
- **ALWAYS read and document analysis immediately** after each inspector run (before next inspector)
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
- **Keep deny lists minimal** - Only exclude about/contact/donate/privacy/terms

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
./scrapai crawl website_name --limit 5
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
   - Make the `allow` pattern more specific for articles (NOT the deny list)
   - Ensure `callback: "parse_article"` only on actual content URLs
   - Keep deny list minimal - do NOT add more deny patterns

5. **⚠️ BEFORE MARKING QUEUE ITEM AS COMPLETE ⚠️**:

   **STOP. Verify ALL of these are TRUE:**
   - ✅ Phase 1 completed: Full analysis documented in `sections.md`
   - ✅ Phase 2 completed: All rules created and consolidated in `final_spider.json`
   - ✅ Phase 3 completed: Spider imported successfully to database
   - ✅ Phase 4 completed: Test crawl run with `--limit 5`
   - ✅ Results verified: Run `./scrapai show website_name` and confirmed quality content
   - ✅ No errors: Spider extracted actual articles, not navigation pages

   **ONLY IF ALL ABOVE ARE TRUE**, mark as complete:
   ```bash
   source .venv/bin/activate && ./scrapai queue complete <id>
   ```

   **If test fails or extraction is wrong:**
   ```bash
   # DO NOT mark as complete
   # Instead, mark as failed with reason:
   source .venv/bin/activate && ./scrapai queue fail <id> -m "Extraction failed: [specific reason]"
   ```

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
-   `source .venv/bin/activate && ./scrapai crawl <name> --limit 5` - Test mode (saves to DB for verification).
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

**🚨 CRITICAL: DEFAULT EXTRACTION APPROACH 🚨**

**ALWAYS use simple extractors by default. NEVER use Playwright custom configuration unless explicitly requested.**

**Default Behavior (Use This Unless User Says Otherwise):**
- Use the standard extractor order: `["newspaper", "trafilatura", "playwright"]`
- **DO NOT configure** `PLAYWRIGHT_WAIT_SELECTOR`, `PLAYWRIGHT_DELAY`, `INFINITE_SCROLL`, or other Playwright customizations
- Let the smart extractors handle content automatically
- Simple spiders with just URL rules (allow/deny patterns)

**Only Use Playwright Custom Configuration When:**
- User explicitly requests "wait for selector" or "add delay"
- User explicitly requests "infinite scroll" or "scroll down"
- User mentions JavaScript delays or specific elements to wait for
- User says the site needs browser rendering with custom settings

**Default Spider Structure (No Custom Extractors):**
```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com"],
  "rules": [
    {
      "allow": ["patterns for content"],
      "deny": ["patterns to exclude"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura", "playwright"]
  }
}
```

**Notice:** No `PLAYWRIGHT_WAIT_SELECTOR`, no `PLAYWRIGHT_DELAY`, no `INFINITE_SCROLL` - just simple rules!

---

The system uses a **Smart Extractor** that tries multiple strategies in order. You can configure the order via `EXTRACTOR_ORDER` in settings.

**Available Strategies:**
1.  `newspaper`: Uses `newspaper4k` on the static HTML (Fast, Default).
2.  `trafilatura`: Uses `trafilatura` on the static HTML (Good for text-heavy sites).
3.  `playwright`: Uses a headless browser to fetch rendered HTML, then extracts with `trafilatura` (Slow, handles JS).

**Default Order:** `["newspaper", "trafilatura", "playwright"]`

### Choosing Extractor Order

**IMPORTANT: You should configure extractor order based on site characteristics identified during analysis.**

**Default (Static HTML Sites):** `["newspaper", "trafilatura", "playwright"]`
- Use for traditional websites with content in static HTML
- Fast extractors first, slow browser rendering as last resort
- Most news sites, blogs, and article-based sites

**JS-Rendered Sites:** `["playwright", "trafilatura", "newspaper"]`
- **Use when content is loaded via JavaScript**
- Playwright first since static extractors will fail on empty HTML
- Static extractors won't work as fallbacks - they'll see the same empty page
- Examples: SPAs (Single Page Apps), dynamic content sites

**How to Identify JS-Rendered Sites During Analysis:**
1. **Check page.html after inspector run** - If it has minimal/empty content
2. **Look for content in `<script>` tags** - Data embedded as JavaScript arrays/objects
3. **Look for "Loading..." placeholders** - Empty containers that JS fills in
4. **Check if browser rendering is needed** - Inspector will use browser if needed

**Example JS-Rendered Indicators:**
```html
<!-- Empty container that JS will fill -->
<div id="app"></div>

<!-- Content as JavaScript data -->
<script>
  var data = [
    {"title": "Article 1", "content": "..."},
    {"title": "Article 2", "content": "..."}
  ];
</script>
```

**Configuration in Spider Settings:**
```json
{
  "settings": {
    "EXTRACTOR_ORDER": ["playwright", "trafilatura", "newspaper"]
  }
}
```

### Playwright Wait Configuration

**For sites with JavaScript delays or dynamic content**, you can configure Playwright to wait for specific elements or add extra delays:

**Available Settings:**
- `PLAYWRIGHT_WAIT_SELECTOR`: CSS selector to wait for after page load (max 30 seconds)
- `PLAYWRIGHT_DELAY`: Additional seconds to wait after page load (for JS that runs after network idle)

**When to Use:**
- **JS Delays**: Content loads via `setTimeout()` or delayed AJAX calls
- **Dynamic Content**: Elements appear after initial page render
- **Infinite Scroll**: Content loads as you scroll
- **SPAs**: Single Page Apps that render content progressively

**Example Configuration:**
```json
{
  "name": "example_spider",
  "settings": {
    "EXTRACTOR_ORDER": ["playwright", "trafilatura", "newspaper"],
    "PLAYWRIGHT_WAIT_SELECTOR": ".article-content",
    "PLAYWRIGHT_DELAY": 5
  }
}
```

**How It Works:**
1. Browser navigates to URL and waits for `networkidle`
2. If `PLAYWRIGHT_WAIT_SELECTOR` is set, waits for that element to appear (up to 30s)
3. If `PLAYWRIGHT_DELAY` is set, waits additional seconds before capturing HTML
4. Then captures HTML and proceeds with extraction

**Common Selectors to Wait For:**
- `.article-content` - Main content container
- `.quote` - Quote elements
- `#posts` - Posts container
- `.loaded` - Class added when content finishes loading
- `[data-loaded="true"]` - Attribute indicating loaded state

**Note:** These settings only affect Playwright extraction. If Playwright is not in your `EXTRACTOR_ORDER`, these settings are ignored.

### Infinite Scroll Support

**For single-page sites with infinite scroll** (content loads dynamically as you scroll), configure the spider to automatically scroll and load all content:

**Available Settings:**
- `INFINITE_SCROLL`: Enable infinite scroll behavior (true/false)
- `MAX_SCROLLS`: Maximum number of scrolls to perform (default: 5)
- `SCROLL_DELAY`: Seconds to wait between scrolls for content to load (default: 1.0)

**When to Use:**
- **Infinite scroll pages**: Content loads via AJAX as user scrolls
- **Single-page sites**: All content on one URL with no pagination links
- **Dynamic feeds**: Social media feeds, quote collections, product listings
- **No pagination**: Sites without "Next" buttons or page numbers

**Example Configuration:**
```json
{
  "name": "quotes_toscrape_scroll",
  "allowed_domains": ["quotes.toscrape.com"],
  "start_urls": ["https://quotes.toscrape.com/scroll"],
  "rules": [
    {
      "allow": [],
      "deny": [".*"],
      "callback": null,
      "follow": false,
      "priority": 100
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["playwright", "trafilatura", "newspaper"],
    "PLAYWRIGHT_WAIT_SELECTOR": ".quote",
    "PLAYWRIGHT_DELAY": 2,
    "INFINITE_SCROLL": true,
    "MAX_SCROLLS": 10,
    "SCROLL_DELAY": 2.0
  }
}
```

**How It Works:**
1. Browser navigates to URL and waits for initial content
2. If `PLAYWRIGHT_WAIT_SELECTOR` is set, waits for that element
3. Scrolls to bottom of page and waits `SCROLL_DELAY` seconds
4. Checks if page height increased (new content loaded)
5. Repeats until `MAX_SCROLLS` reached or no new content detected
6. Captures final HTML with all loaded content
7. Extracts content using configured extractors

**Smart Detection:**
- Automatically stops scrolling when no new content loads
- Prevents over-scrolling and wasted time
- Detects when all content has been loaded

**Use Cases:**
- `quotes.toscrape.com/scroll` - Quote collections
- Social media feeds (Twitter, Instagram timelines)
- Product listings with infinite scroll
- Search results that load on scroll
- News feeds that auto-load articles

**Important Notes:**
- Requires `EXTRACTOR_ORDER` to include `"playwright"`
- Works with single-page sites that have no pagination links
- The `parse_start_url()` override ensures start URLs are processed
- Set `follow: false` in rules to stay on the single page
- Combine with `PLAYWRIGHT_WAIT_SELECTOR` for best results

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