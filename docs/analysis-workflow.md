# Analysis & Spider Creation Workflow

**Read this document before starting any website analysis. Follow Phases 1-4 in order.**

---

## Phase 1: Analysis & Section Documentation

**CRITICAL: Complete FULL site analysis before creating ANY rules. DO NOT create rules prematurely.**

**WARNING: DO NOT RUSH TO RULE CREATION**
The most common mistake is creating spider rules without complete site analysis. This results in:
- Missing entire content sections
- Incomplete URL pattern understanding
- Having to delete and recreate the spider
- Wasted time and effort

**MANDATORY: Follow this systematic analysis process COMPLETELY before Phase 2:**

**IMPORTANT: Directory Structure**
- **NEVER use `mkdir` to create directories** - inspector automatically creates `data/<project>/<spider>/analysis/` directory
- Directory structure: `DATA_DIR/project_name/spider_name/analysis/` (default DATA_DIR is `./data`)
- You can customize DATA_DIR in `.env` file (e.g., `DATA_DIR=~/.scrapai/data` or `/mnt/storage/scrapai`)
- Inspector saves `page.html` and `analysis.json` in the correct location
- Just run inspector with `--project <name>` - no setup needed

### Step 1: Extract ALL URLs from Homepage

```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/<project>/<spider>/analysis/page.html --output data/<project>/<spider>/analysis/all_urls.txt
```
```bash
source .venv/bin/activate && cat data/<project>/<spider>/analysis/all_urls.txt
```

### Step 2: Categorize Every URL Type

**CRITICAL: Review the COMPLETE URL list - do not just search for keywords.**

Manually review ALL URLs from `all_urls.txt` and identify:
- **Content pages**: ANY substantive content (articles, blog posts, reports, publications, research papers, speeches, newsletters, policy briefs, etc.)
- **Navigation/listing pages**: Pages that link to content
- **Utility pages**: Pages to exclude (about, contact, etc.)
- **PDF content**: Note if site has PDFs (we skip these for now, but acknowledge as content)
- **Any other URL patterns**: Document everything you find

### Step 3: Document Complete Site Structure

Create comprehensive `sections.md` documenting EVERY section type and URL pattern found on the site.

### Step 4: Verify Nothing is Missed

Review the complete URL list again and confirm you understand the full site structure before proceeding.

**ONLY AFTER COMPLETE ANALYSIS -> Proceed to Phase 2 (Rule Creation)**

**Key Principle:** Custom selectors extract exactly what you specify. Your job is to:
- Understand COMPLETE site navigation structure
- Identify ALL URL patterns for articles vs. navigation pages
- Create comprehensive rules covering ALL content sections
- Discover CSS selectors for title, content, author, date, and any other fields
- Configure CUSTOM_SELECTORS in spider settings

### Step 1A: Homepage Analysis

Inspect the site structure to understand how to extract content:
```bash
source .venv/bin/activate && bin/inspector --url https://website.com/
```
Read page.html and analysis.json immediately after.

### Step 1B: Create Section Documentation

After homepage analysis, create a comprehensive section map in `sections.md` to document all discovered sections, URL patterns, and rule requirements.

### Step 1C: Iterative Section Drilling

**CRITICAL: SEQUENTIAL PROCESSING ONLY**
- **NEVER run multiple inspectors in parallel**
- Each inspector overwrites `page.html` and `analysis.json`
- **ALWAYS complete this cycle for EACH section:**
  1. Run ONE inspector
  2. Read the output files immediately
  3. Document findings in sections.md
  4. Only then move to next section

Example - sequential section drilling (ONE at a time):
```bash
# Step 1: Inspect first section
source .venv/bin/activate && bin/inspector --url https://example.com/news/
```
```bash
# Step 2: IMMEDIATELY read and document before moving on
source .venv/bin/activate && cat data/<project>/example_com/analysis/analysis.json
```
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/<project>/example_com/analysis/page.html --output data/<project>/example_com/analysis/news_urls.txt
```
```bash
# Step 3: Update sections.md with findings
# Step 4: Now inspect next section
source .venv/bin/activate && bin/inspector --url https://example.com/policy/
```
```bash
# Step 5: IMMEDIATELY read and document
source .venv/bin/activate && cat data/<project>/example_com/analysis/analysis.json
```
```bash
source .venv/bin/activate && ./scrapai extract-urls --file data/<project>/example_com/analysis/page.html --output data/<project>/example_com/analysis/policy_urls.txt
```
```bash
# Step 6: Update sections.md with findings
# Continue this pattern for each section
# STOP: Do NOT inspect the final content pages themselves - Extractors handle content extraction
```

### Iterative Analysis Workflow

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

### File Structure Created

```
data/<project>/<spider>/analysis/
├── page.html           (preserved - homepage HTML)
├── analysis.json       (preserved - homepage analysis)
├── all_urls.txt        (all URLs extracted from homepage)
├── sections.md         (comprehensive section documentation with hierarchy)
├── section_rules_*.json (rule files for each section)
└── final_spider.json   (consolidated rules from all sections)
```

### Key Analysis Principles

1. **Extract complete URL list** - Get every link from homepage
2. **Drill down systematically** - Visit sections, then subsections, iteratively
3. **Stop at content discovery** - When you find final content URL patterns, document and stop
4. **Never inspect content** - Don't analyze individual content pages
5. **Document hierarchy** - Record the full navigation structure
6. **Preserve everything** - Keep all analysis files for reference

### Common Pitfalls to Avoid

- Don't assume homepage analysis is sufficient
- Don't create rules without understanding complete URL patterns
- **DO NOT inspect individual content pages** - Extractors handle content extraction
- **NEVER run multiple inspectors in parallel** - They ALL overwrite `page.html` and `analysis.json`
- **Process sections sequentially**: Run inspector -> Read files -> Document -> Next section
- **ALWAYS read and document analysis immediately** after each inspector run (before next inspector)
- **NEVER delete analysis files** - Keep all analysis artifacts
- Focus on URL patterns and navigation hierarchy, not content structure
- Create section-specific rules before consolidating

---

## Phase 2: Section-Based Rule Generation

Generate comprehensive rules using section documentation. **Do not create Python files.**

### Step 2A: Use sections.md for Rule Creation

Read the complete `sections.md` file to understand:
- All sections discovered during analysis
- URL patterns for each section
- Content types (navigation vs articles)
- Specific requirements for each section

### Step 2B: Create Individual Section Rule Files

For each section documented in `sections.md`, create specific rule files based on discovered URL patterns.

### Step 2C: Consolidate into Final Spider JSON

Combine all section rule files into a comprehensive spider definition.

---

## Phase 2.5: Test Generic Extractors (REQUIRED FIRST)

**Before writing custom selectors, test if generic extractors work correctly.**

### Step 1: Inspect an Article Page

Fetch an actual article (not homepage or listing page):

```bash
source .venv/bin/activate && bin/inspector --url https://website.com/article-url --project <project_name>
```

This saves `page.html` and `analysis.json` to `data/<project_name>/website_com/analysis/`.

### Step 2: Test Generic Extraction

**CRITICAL: You need to actually test if newspaper/trafilatura extract the content correctly.**

Currently, there's no automated tool for this. You must:
1. Manually check the article HTML in `page.html`
2. Verify if the article has clean, semantic HTML structure
3. Consider if newspaper/trafilatura would likely extract:
   - The correct title (not navigation or header text)
   - The full article content (not sidebars/comments/related articles)
   - Author and date if available

**Indicators that generic extractors will work:**
- Article content in `<article>` tags or semantic divs
- Clean HTML without excessive navigation/sidebars mixed in
- Standard news/blog article structure

**Indicators that generic extractors will fail:**
- Complex layouts with content scattered across multiple divs
- Navigation, sidebars, or related content mixed with main content
- Non-standard page structures (products, forums, profiles)
- JavaScript-rendered content

### Step 3: Decision Point

**If you believe generic extractors will work:**
- Skip to Phase 2D
- Use `EXTRACTOR_ORDER: ["newspaper", "trafilatura"]`
- No custom selectors needed

**If you believe generic extractors will fail:**
- Proceed to Phase 2.6 to discover custom selectors
- Use `EXTRACTOR_ORDER: ["custom", "newspaper", "trafilatura"]`

---

## Phase 2.6: Discover Custom Selectors (ONLY IF NEEDED)

**Only do this if generic extractors won't work correctly.**

1. **Use the article page inspected in Phase 2.5**:

2. **Analyze HTML and find selectors**:
   ```bash
   source .venv/bin/activate && bin/analyze_selectors data/<project>/website_com/analysis/page.html
   ```
   This shows: All h1/h2 titles with classes, content containers sorted by size, date elements, author elements.

3. **Test each selector**:
   ```bash
   source .venv/bin/activate && bin/analyze_selectors data/<project>/website_com/analysis/page.html --test "h1.article-title"
   ```
   ```bash
   source .venv/bin/activate && bin/analyze_selectors data/<project>/website_com/analysis/page.html --test "div.article-body"
   ```

4. **Search for specific fields**:
   ```bash
   source .venv/bin/activate && bin/analyze_selectors data/<project>/website_com/analysis/page.html --find "price"
   ```
   ```bash
   source .venv/bin/activate && bin/analyze_selectors data/<project>/website_com/analysis/page.html --find "rating"
   ```

5. **Add CUSTOM_SELECTORS to final_spider.json**:
   ```json
   {
     "name": "website_name",
     "settings": {
       "CUSTOM_SELECTORS": {
         "title": "h1.article-title",
         "content": "div.article-body",
         "author": "span.author-name",
         "date": "time.published-date"
       }
     }
   }
   ```

For full selector documentation (examples, discovery principles, common mistakes), see [docs/extractors.md](extractors.md).

---

## Phase 2D: Final JSON Payload Structure

**Choose the appropriate configuration based on Phase 2.5 decision:**

### Option A: Without Custom Selectors (Generic Extractors Work)

```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com/blog", "https://domain.com/news"],
  "rules": [
    {
      "allow": ["/blog/[^/]+$", "/news/[^/]+$"],
      "deny": [],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/blog$", "/news$"],
      "deny": [],
      "callback": null,
      "follow": true,
      "priority": 50
    },
    {
      "deny": ["/about/", "/contact", "/donate"],
      "callback": null,
      "follow": false,
      "priority": 0
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

### Option B: With Custom Selectors (Generic Extractors Failed)

```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com/blog", "https://domain.com/news"],
  "rules": [
    {
      "allow": ["/blog/[^/]+$", "/news/[^/]+$"],
      "deny": [],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/blog$", "/news$"],
      "deny": [],
      "callback": null,
      "follow": true,
      "priority": 50
    },
    {
      "deny": ["/about/", "/contact", "/donate"],
      "callback": null,
      "follow": false,
      "priority": 0
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
    "EXTRACTOR_ORDER": ["custom", "newspaper", "trafilatura"],
    "CUSTOM_SELECTORS": {
      "title": "h1.article-title",
      "content": "div.article-body",
      "author": "span.author-name",
      "date": "time.published-date"
    }
  }
}
```

**Rule Design Principles:**
- **Extraction rules** (`callback`: `"parse_article"`) - Only for actual content pages
- **Navigation rules** (`follow`: `true`) - For discovering article links
- **Block rules** (`deny`) - Prevent unwanted content extraction
- **Priority matters** - Higher priority rules are evaluated first
- **Keep deny lists minimal** - Only exclude about/contact/donate/privacy/terms

---

## Phase 3: Prepare Spider Configuration

**DO NOT import yet! Phase 3 is just preparation.**

At this point you should have created in Phase 2:
- `final_spider.json` - Full spider with navigation rules
- Optionally `test_spider.json` - Test spider with 5 URLs and follow=false

**All importing happens in Phase 4:**
- **Phase 4A:** Import test_spider.json to test extraction quality
- **Phase 4B:** Import final_spider.json to test navigation and full crawl

**Why delay import until testing:**
- Test extraction first (Phase 4A) before committing to full spider
- If extraction fails, you can fix selectors without deleting/reimporting
- Cleaner workflow: create → test → import final

---

## Phase 4: Execution & Verification

**CRITICAL: Test extraction quality BEFORE testing navigation/discovery.**

Debugging both extraction AND navigation together is difficult. Instead:
1. First verify extraction works correctly on specific articles
2. Then enable navigation to discover more articles

### Step 4A: Test Extraction Quality (5 Specific Articles)

**Why this approach:**
- Isolates extraction issues from navigation issues
- Faster debugging - no waiting for link discovery
- Confirms extractors work before testing rules

**Process:**

1. **Collect 5 article URLs from your analysis** (from earlier URL extraction):
   ```bash
   # Example URLs from sections.md or URL extraction files
   https://example.com/blog/article-1
   https://example.com/blog/article-2
   https://example.com/policy/article-3
   https://example.com/research/article-4
   https://example.com/commentary/article-5
   ```

2. **Create a test spider** (`data/<project>/<spider>/analysis/test_spider.json`):
   ```json
   {
     "name": "website_name",
     "allowed_domains": ["example.com"],
     "start_urls": [
       "https://example.com/blog/article-1",
       "https://example.com/blog/article-2",
       "https://example.com/policy/article-3",
       "https://example.com/research/article-4",
       "https://example.com/commentary/article-5"
     ],
     "rules": [
       {
         "comment": "BLOCK ALL FOLLOWING - Just test extraction",
         "deny": [".*"],
         "callback": null,
         "follow": false,
         "priority": 100
       }
     ],
     "settings": {
       "DOWNLOAD_DELAY": 1,
       "CONCURRENT_REQUESTS": 3,
       "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
       "CLOUDFLARE_ENABLED": true
     }
   }
   ```

3. **Import and test:**
   ```bash
   source .venv/bin/activate && ./scrapai spiders import data/<project>/<spider>/analysis/test_spider.json --project <project_name>
   ```
   ```bash
   source .venv/bin/activate && ./scrapai crawl website_name --limit 5 --project <project_name>
   ```

4. **Verify extraction quality:**
   ```bash
   source .venv/bin/activate && ./scrapai show website_name --limit 5 --project <project_name>
   ```

5. **Check quality:**
   - ✅ **Good:** Titles match URL slugs, correct authors, dates, clean content
   - ❌ **Bad:** Wrong titles, missing content, extraction failed

**If extraction quality is BAD:**
- Go back to Phase 2.5/2.6 to fix extractors or add custom selectors
- Delete spider, update selectors, re-import, re-test
- DO NOT proceed to Step 4B until extraction works correctly

**If extraction quality is GOOD:**
- Proceed to Step 4B to enable full navigation

---

### Step 4B: Enable Navigation & Test Full Crawl

**Only proceed here if Step 4A extraction was successful!**

1. **Delete test spider:**
   ```bash
   source .venv/bin/activate && echo "y" | ./scrapai spiders delete website_name --project <project_name>
   ```

2. **Import final spider with navigation rules:**
   ```bash
   source .venv/bin/activate && ./scrapai spiders import data/<project>/<spider>/analysis/final_spider.json --project <project_name>
   ```

**Spider is now ready for production use!** Extraction quality was already verified in Step 4A.

**Production Mode:**
```bash
# Full scrape - exports to files, no database cost
source .venv/bin/activate && ./scrapai crawl website_name --project <project_name>
```

### Before Marking Queue Item as Complete

**STOP. Verify ALL of these are TRUE:**
- Phase 1 completed: Full analysis documented in `sections.md`
- Phase 2 completed: All rules created and consolidated in `final_spider.json`
- Phase 3 completed: Spider JSON files prepared (test_spider.json and final_spider.json)
- Phase 4A completed: Test spider extraction quality verified (ran `--limit 5`, checked results)
- Phase 4B completed: Final spider imported successfully to database
- No errors: Test spider extracted actual articles with good quality

**ONLY IF ALL ABOVE ARE TRUE**, mark as complete:
```bash
source .venv/bin/activate && ./scrapai queue complete <id>
```

**If test fails or extraction is wrong:**
```bash
# DO NOT mark as complete. Instead, mark as failed with reason:
source .venv/bin/activate && ./scrapai queue fail <id> -m "Extraction failed: [specific reason]"
```
