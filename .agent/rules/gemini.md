---
trigger: always_on
---

# ScrapAI Agent Rules

Project-based Scrapy spider management for large-scale web scraping. Database-first approach.

## 🚨 ABSOLUTE CRITICAL RULES 🚨

### SEQUENTIAL PROCESSING ONLY - NO EXCEPTIONS

**FORBIDDEN - NEVER USE:**
- ❌ Task tool / subagents (`Task`, `subagent_type`, etc.)
- ❌ Background tasks (`run_in_background=true`)
- ❌ Parallel agents (multiple agents simultaneously)
- ❌ ANY form of concurrent processing
- ❌ Chaining multiple operations (except venv + single command)
- ❌ Using grep, pipes (`|`), complex one-liners

**REQUIRED - ALWAYS DO:**
- ✅ Process ONE website at a time, start to finish
- ✅ Run ONE command at a time in separate bash calls
- ✅ WAIT for each command to complete
- ✅ READ output before next command
- ✅ OK format: `source .venv/bin/activate && <single command>`

**Example - Multiple Queue Items:**
```
User: "Process the next 10 items"
CORRECT: Process item 1 (full workflow) → item 2 (full workflow) → ... → item 10
WRONG: Launch 10 agents in parallel ← NEVER DO THIS
```

**Command Execution Examples:**
```bash
# ❌ WRONG - Multiple operations chained
source .venv/bin/activate && bin/inspector --url https://example.com && ./scrapai extract-urls ... && cat file | grep pattern

# ✅ CORRECT - One operation at a time
source .venv/bin/activate && bin/inspector --url https://example.com
```
```bash
# Next command - separate bash call
source .venv/bin/activate && ./scrapai extract-urls --file data/site/page.html -o data/site/urls.txt
```
```bash
# Next command - separate bash call
cat data/site/urls.txt
```

### Environment Setup

```bash
# ALWAYS run verify first
./scrapai verify

# If needed: Setup and activate
./scrapai setup
source .venv/bin/activate
```

## 4-PHASE WORKFLOW - NEVER SKIP PHASES

**⚠️ CRITICAL: Complete EVERY step of EVERY phase before proceeding.**

### Common Mistakes That WILL Cause Failures:
❌ Skip analysis and jump to rules → Spider misses content
❌ Create rules without reading ALL URLs → Incomplete coverage
❌ Mark complete before testing → Broken spiders in database
❌ Rush through phases → Have to delete and redo everything
❌ Run multiple inspectors in parallel → Files overwrite each other
❌ Assume site structure → Wrong extraction patterns

### Phase 1: Analysis & Documentation

**🚨 MOST COMMON MISTAKE: Creating rules too early without complete analysis 🚨**

This causes:
- Missing entire content sections
- Incomplete URL pattern understanding
- Having to DELETE spider and start over
- Wasted time and effort

**MANDATORY ANALYSIS PROCESS:**

**Step 1A: Homepage Inspection**
```bash
source .venv/bin/activate && bin/inspector --url https://website.com/
```
```bash
# IMMEDIATELY read the output files
cat data/website_com/analysis/page.html
```
```bash
cat data/website_com/analysis/analysis.json
```

**Step 1B: Extract EVERY URL from Homepage**
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/website_com/analysis/page.html -o data/website_com/analysis/all_urls.txt
```
```bash
# READ THE COMPLETE URL LIST - DO NOT SKIP THIS
cat data/website_com/analysis/all_urls.txt
```

**Step 1C: Categorize URLs - Review EVERY Single URL**
**CRITICAL: Do NOT just search for keywords. Review the COMPLETE list manually.**

Identify:
- **Content pages**: Articles, reports, publications, research, speeches, newsletters, policy briefs, analysis, etc.
- **Navigation pages**: Section pages, category listings that LINK to content
- **Utility pages**: About, contact, login, terms (EXCLUDE these)
- **PDF content**: Note if present (skip for now but acknowledge as content)

**Default Content Focus:**
- **INCLUDE**: ANY substantive HTML content (articles, reports, research, speeches, analysis, etc.)
- **EXCLUDE**: About/team, contact/donate, login, privacy/terms, author bios, category archives, pagination, PDFs

**Rule of Thumb: When uncertain, INCLUDE IT. Be inclusive, not restrictive.**

**Step 1D: Create sections.md**
Document EVERY section type, URL pattern, and navigation hierarchy discovered.

**Step 1E: Iterative Section Drilling**

**⚠️ CRITICAL: ONE SECTION AT A TIME - Files Overwrite Each Other**

```bash
# Example: Drill into first section
source .venv/bin/activate && bin/inspector --url https://example.com/news/
```
```bash
# STOP. Read files IMMEDIATELY before next inspector
cat data/example_com/analysis/analysis.json
```
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/example_com/analysis/page.html -o data/example_com/analysis/news_urls.txt
```
```bash
cat data/example_com/analysis/news_urls.txt
# Update sections.md with findings
```
```bash
# NOW inspect next section (not before)
source .venv/bin/activate && bin/inspector --url https://example.com/policy/
```
```bash
# IMMEDIATELY read and document
cat data/example_com/analysis/analysis.json
```
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/example_com/analysis/page.html -o data/example_com/analysis/policy_urls.txt
```
```bash
cat data/example_com/analysis/policy_urls.txt
# Update sections.md with findings
```

**Iterative Drilling Workflow:**
1. Homepage → Extract ALL URLs
2. Identify section URLs from complete list
3. Visit ONE section URL → Read output immediately → Document
4. Check for subsections in that section → Visit if needed → Document
5. Continue drilling until you find final content URL patterns
6. **STOP at content discovery** - DO NOT inspect individual articles
7. **NEVER run multiple inspectors in parallel**
8. Document complete navigation hierarchy in sections.md

**Key Principles:**
- Smart extractors handle content extraction automatically
- Your job: Understand navigation structure and URL patterns
- Never run parallel inspectors (file overwrites)
- Preserve all analysis files

**ONLY AFTER COMPLETE ANALYSIS → Proceed to Phase 2**

### Phase 2: Rule Generation

**Use sections.md to create comprehensive rules for ALL discovered sections.**

**Step 2A:** Read complete sections.md to understand all sections
**Step 2B:** Create section-specific rule files for each section
**Step 2C:** Consolidate all rules into final_spider.json

**Spider JSON Structure:**
```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["URL patterns from analysis"],
  "rules": [
    {
      "allow": ["patterns for FINAL CONTENT pages only"],
      "deny": ["exclude patterns"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["patterns for NAVIGATION pages that link to content"],
      "callback": null,
      "follow": true,
      "priority": 50
    },
    {
      "deny": ["utility pages to block completely"],
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

**Rule Design Critical Principles:**
- **Extraction rules** (`callback: "parse_article"`) - ONLY for actual content pages
- **Navigation rules** (`follow: true`) - For discovering article links, NO callback
- **Block rules** (`deny`) - Prevent unwanted extraction
- **Priority matters** - Higher priority = evaluated first
- **Be restrictive** - Only extract what you want

### Phase 3: Import

```bash
source .venv/bin/activate && ./scrapai spiders import data/website_com/analysis/final_spider.json
```

**Why import from file:** Uses consolidated JSON from Phase 2, preserves config for reference

### Phase 4: Test & Verify

**Storage Mode Selection:**
- **With `--limit`**: Saves to database for verification with `show` command
- **Without `--limit`**: Exports to files (production, avoids DB costs)

**Test Mode (with --limit):**
```bash
source .venv/bin/activate && ./scrapai crawl spider_name --limit 10
```
```bash
source .venv/bin/activate && ./scrapai show spider_name --limit 5
```

**Production Mode (without --limit):**
```bash
source .venv/bin/activate && ./scrapai crawl spider_name
# Exports to: data/spider_name/crawl_TIMESTAMP.jsonl
```

**Verification Checklist - CRITICAL:**
1. Check content: `source .venv/bin/activate && ./scrapai show spider_name`
2. Verify ACTUAL articles (not navigation page titles like "Latest News")
3. Confirm substantial content length (not just snippets)
4. Check metadata (author, date) if available

**If Spider Extracts Wrong Content:**
```bash
# DELETE and start over - DO NOT try to fix with patches
source .venv/bin/activate && echo "y" | ./scrapai spiders delete spider_name
# Go back to Phase 1: Re-analyze site structure
# Phase 2: Refine rules based on new understanding
# Phase 3: Re-import
# Phase 4: Test again
```

**Common Extraction Problems:**
- Extracting navigation pages instead of articles → Rules too broad
- Missing content sections → Incomplete analysis in Phase 1
- Wrong content type → Allow patterns not restrictive enough

**Fixes:**
- Make extraction rules MORE restrictive
- Add comprehensive deny patterns
- Ensure `callback: "parse_article"` ONLY on actual content URLs
- Use `follow: true` WITHOUT callbacks for navigation only

**⚠️ BEFORE MARKING COMPLETE - VERIFY ALL:**
- ✅ Phase 1: Full analysis in sections.md
- ✅ Phase 2: All rules in final_spider.json
- ✅ Phase 3: Spider imported successfully
- ✅ Phase 4: Test crawl completed with `--limit 10`
- ✅ Results verified: `./scrapai show spider_name` shows QUALITY content
- ✅ No errors: Actual articles extracted, not navigation

**ONLY IF ALL TRUE:**
```bash
source .venv/bin/activate && ./scrapai queue complete <id>
```

**If test fails or extraction wrong:**
```bash
source .venv/bin/activate && ./scrapai queue fail <id> -m "Specific reason: [describe issue]"
```

## Queue System (Optional)

**Use ONLY when user explicitly requests queue mode. Otherwise, process websites directly.**

**Queue Commands:**
```bash
# Add to queue
source .venv/bin/activate && ./scrapai queue add <url> [-m "instruction"] [--priority N]

# List queue (default: 5 pending)
source .venv/bin/activate && ./scrapai queue list
source .venv/bin/activate && ./scrapai queue list --all --limit 50

# Claim next (atomic - safe for concurrent use)
source .venv/bin/activate && ./scrapai queue next

# Update status
source .venv/bin/activate && ./scrapai queue complete <id>
source .venv/bin/activate && ./scrapai queue fail <id> -m "error message"
source .venv/bin/activate && ./scrapai queue retry <id>
source .venv/bin/activate && ./scrapai queue remove <id>

# Cleanup
source .venv/bin/activate && ./scrapai queue cleanup --completed --force
source .venv/bin/activate && ./scrapai queue cleanup --failed --force
```

## Essential Commands

**Setup:**
- `./scrapai verify` - Check environment
- `./scrapai setup` - Initialize (first time)

**Spiders:**
- `source .venv/bin/activate && ./scrapai spiders list`
- `source .venv/bin/activate && ./scrapai spiders import <file>`
- `source .venv/bin/activate && ./scrapai spiders delete <name>`

**Data:**
- `source .venv/bin/activate && ./scrapai show <name>` - View recent articles
- `source .venv/bin/activate && ./scrapai show <name> --limit 10`
- `source .venv/bin/activate && ./scrapai show <name> --title "pattern"`

**Export (only when user requests):**
- `source .venv/bin/activate && ./scrapai export <name> --format csv`
- `source .venv/bin/activate && ./scrapai export <name> --format json`
- `source .venv/bin/activate && ./scrapai export <name> --format parquet`

## Architecture

**Database:** PostgreSQL with Alembic migrations
**Schema:** spiders, spider_rules, spider_settings, scraped_items
**Spider:** Generic DatabaseSpider loads rules dynamically from database
**Extractors:** newspaper (fast) → trafilatura (text-heavy) → playwright (JS-rendered)
