# Analysis & Spider Creation Workflow

Follow Phases 1-4 in order. Never skip phases.

---

## Phase 1: Analysis & Section Documentation

**Complete FULL site analysis before creating ANY rules.**

### Step 1: Inspect Homepage

```bash
./scrapai inspect https://website.com/ --project proj
```

Read `page.html` and `analysis.json` immediately after.

### Step 2: Extract ALL URLs

```bash
./scrapai extract-urls --file data/proj/spider/analysis/page.html --output data/proj/spider/analysis/all_urls.txt
```

### Step 3: Categorize URLs

Review ALL URLs from `all_urls.txt`:
- **Content pages**: articles, blog posts, reports, publications, research
- **Navigation/listing pages**: pages that link to content
- **Utility pages**: about, contact, etc. (exclude)
- **PDFs**: note presence, skip for now

### Step 4: Drill Into Sections (ONE AT A TIME)

Inspector overwrites `page.html` and `analysis.json` each run. Process sequentially:

1. Inspect one section URL
2. Read output files immediately
3. Document findings in `sections.md`
4. Move to next section

```bash
./scrapai inspect https://example.com/news/ --project proj
```
Read analysis. Extract section URLs:
```bash
./scrapai extract-urls --file data/proj/spider/analysis/page.html --output data/proj/spider/analysis/news_urls.txt
```
Update `sections.md`. Repeat for each section.

**Stop at content discovery** — when you find article URL patterns, document them and stop. Do NOT inspect individual content pages.

### File Structure

```
data/<project>/<spider>/analysis/
├── page.html, analysis.json
├── all_urls.txt
├── sections.md
├── section_rules_*.json
└── final_spider.json
```

---

## Phase 2: Rule Generation

### Step 2A: Create Rules from sections.md

For each section, create rule files based on discovered URL patterns.

### Step 2B: Test Generic Extractors

Inspect an article page:
```bash
./scrapai inspect https://website.com/article-url --project proj
```

If inspector shows "Checking your browser" or 403/503 → re-run with `--cloudflare`.

Check if newspaper/trafilatura would extract correctly:
- Clean `<article>` tags / semantic HTML → generic extractors work
- Complex layouts, JS-rendered, sidebars mixed in → need custom selectors

**If generic works:** Use `EXTRACTOR_ORDER: ["newspaper", "trafilatura"]`
**If generic fails:** Proceed to custom selector discovery.

### Step 2C: Custom Selector Discovery (only if needed)

```bash
./scrapai analyze data/proj/spider/analysis/page.html
./scrapai analyze data/proj/spider/analysis/page.html --test "h1.article-title"
./scrapai analyze data/proj/spider/analysis/page.html --test "div.article-body"
./scrapai analyze data/proj/spider/analysis/page.html --find "price"
```

See [extractors.md](extractors.md) for selector documentation.

### Step 2D: Create final_spider.json

**Without custom selectors:**
```json
{
  "name": "spider_name",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com/blog"],
  "rules": [
    { "allow": ["/blog/[^/]+$"], "callback": "parse_article", "follow": false, "priority": 100 },
    { "allow": ["/blog$"], "callback": null, "follow": true, "priority": 50 },
    { "deny": ["/about/", "/contact", "/donate"], "callback": null, "follow": false, "priority": 0 }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 3,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

**With custom selectors:** Add to settings:
```json
{
  "EXTRACTOR_ORDER": ["custom", "newspaper", "trafilatura"],
  "CUSTOM_SELECTORS": {
    "title": "h1.article-title",
    "content": "div.article-body",
    "author": "span.author-name",
    "date": "time.published-date"
  }
}
```

**Rule types:**
- Extraction rules: `callback: "parse_article"`, `follow: false` — content pages
- Navigation rules: `follow: true` — for discovering links
- Block rules: `deny: [...]` — prevent unwanted pages
- Higher priority evaluated first

---

## Phase 3: Prepare Spider Configuration

Create `test_spider.json` and `final_spider.json`. Do NOT import yet — importing happens in Phase 4.

---

## Phase 4: Execution & Verification

### Step 4A: Test Extraction (5 articles)

Create `test_spider.json` with 5 article URLs:
```json
{
  "name": "website_name",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/article-1", "...4 more..."],
  "rules": [{ "deny": [".*"], "callback": null, "follow": false, "priority": 100 }],
  "settings": { "DOWNLOAD_DELAY": 1, "CONCURRENT_REQUESTS": 3, "EXTRACTOR_ORDER": ["newspaper", "trafilatura"] }
}
```

```bash
./scrapai spiders import data/proj/spider/analysis/test_spider.json --project proj
./scrapai crawl website_name --limit 5 --project proj
./scrapai show website_name --limit 5 --project proj
```

**Good:** Correct titles, clean content, authors, dates.
**Bad:** Wrong titles, missing content → go back to Phase 2, fix selectors.

### Step 4B: Import Final Spider

Make `final_spider.json` with **same name** as test spider (auto-updates):
```bash
./scrapai spiders import data/proj/spider/analysis/final_spider.json --project proj
```

Test data from 4A is preserved. Spider ready for production.

### Before Marking Queue Complete

Verify ALL phases passed:
- Phase 1: `sections.md` complete
- Phase 2: Rules consolidated in `final_spider.json`
- Phase 3: Both JSON files prepared
- Phase 4A: Extraction quality verified
- Phase 4B: Final spider imported

```bash
./scrapai queue complete <id>     # only if ALL pass
./scrapai queue fail <id> -m "reason"  # if any fail
```

---

## Common Failures & Recovery

**Inspector overwrites files:** NEVER run multiple inspectors in parallel. Each run overwrites `page.html` and `analysis.json`. Always read output immediately before next inspector run.

**Cloudflare during analysis:** If inspector shows "Checking your browser" or 403/503, re-run with `--cloudflare`. Note this for Phase 4 — add `CLOUDFLARE_ENABLED: true` to spider settings. If inspector works fine, do NOT enable Cloudflare.

**Bad extraction in 4A:** Go back to Phase 2, fix selectors or switch extractor order. Delete spider if needed:
```bash
echo "y" | ./scrapai spiders delete spider_name --project proj
```
Re-create test_spider.json, re-import, re-test. Do NOT proceed to 4B until extraction is good.

**Do NOT add Cloudflare by default in test_spider.json.** Only add if you confirmed CF protection during analysis. It adds major overhead (visible browser, slower crawling).

**Directory creation:** Never use `mkdir`. Inspector auto-creates `data/<project>/<spider>/analysis/`. DATA_DIR is configurable in `.env`.

**Do NOT inspect individual content pages** during Phase 1. Extractors handle content extraction — you only need URL patterns and navigation structure.
