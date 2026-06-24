# Analysis & Spider Creation Workflow

Follow Phases 1-4 in order. Never skip phases.

---

## Phase 1: Analysis & Section Documentation

**Complete FULL site analysis before creating ANY rules.**

### Step 1: Inspect Homepage

```bash
./scrapai inspect https://website.com/ --project proj
```

Then use `./scrapai extract-urls` and `./scrapai analyze` to process the saved HTML. Do NOT read `page.html` directly.

**Required for section mapping:** run `./scrapai inspect <url> --screenshot` and `Read` the saved `page.png` for the homepage and each section/listing page. Seeing the rendered page is the most reliable way to identify sections, content types, and navigation. (For individual content pages in Phase 2, use vision by judgment — screenshot only when generic extraction is unclear or fields like date/author come out wrong; it forces a browser launch, so don't do it by reflex.)

### Step 2: Extract ALL URLs

```bash
./scrapai extract-urls --file data/proj/spider/analysis/page.html --output data/proj/spider/analysis/all_urls.txt
```

### Step 3: Categorize URLs

Review ALL URLs from `all_urls.txt`. **Collect everything you can find — there is no exclusion list.** Incomplete collection is the painful, unrecoverable failure; over-collecting is cheap (unwanted links/content are dropped later in post-processing). Map every section and subsection:

- **Content pages**: articles, blog posts, reports, publications, research, op-eds, one-pagers, annual reports
- **Navigation/listing pages**: pages that link to content
- **Peripheral pages**: about, team, etc. — include them when they hold any content
- **PDFs**: collected by default. `PDF_MODE: links_only` (the default) records each linked PDF as a URL-only item without downloading it; `PDF_MODE: extract` follows each PDF, downloads it, and extracts its text via pypdfium2 (born-digital only — scanned/image PDFs stay URL-only, no OCR).

When unsure whether something is content, **include it.** **"Different layout" or "analyze later" is never a reason to drop a section** — a different layout means add another rule + callback in Phase 2, not exclude it.

You never hand-list external links to skip — `allowed_domains` keeps the crawl on-site automatically. The **one** carve-out is an **infinite URL trap** (calendar `?date=` loops, faceted-search/filter permutations): not low-value content but *not content at all*, and a rule that follows it never terminates. Exclude the trap *pattern* only — never a content section.

### Step 4: Drill Into Sections (ONE AT A TIME)

Inspector overwrites `page.html` each run. Process sequentially:

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
DATA_DIR/<project>/<spider>/
├── analysis/
│   ├── page.html
│   ├── all_urls.txt
│   ├── sections.md
│   ├── section_rules_*.json
│   └── final_spider.json
├── crawls/
│   └── crawl_DDMMYYYY.jsonl   # date-based; one file per day, same-day runs append
└── exports/
    └── export_TIMESTAMP.format
```

---

## Phase 2: Rule Generation

### Step 2A: Decide the extraction strategy — read `project.json` FIRST

Before writing any rules, read `data/<project>/project.json` and route on its field schema:

- **Core-only schema** (only `title` / `content` / `author` / `published_date`) → `EXTRACTOR_ORDER: ["trafilatura", "newspaper"]`; add `FIELDS` directives only to fix wrong guesses.
- **Schema with ANY non-core field** (required or optional) → pure-CSS: `EXTRACTOR_ORDER: ["custom"]` plus one `FIELDS` directive per schema field. Mixing generic extractors (newspaper/trafilatura) with a non-core schema is **REJECTED on import** (enforced in `core/schema_validator.py`).
- **Products / jobs / listings / forums** → named callbacks, one per section layout (see Step 2E).

### Step 2B: Create Rules from sections.md

For each section, create rule files based on discovered URL patterns.

**A spider is not one function.** Write as many rules and callbacks as the site's sections need — never force structurally-different sections through a single callback. Same article layout everywhere → one `parse_article` is right. Sections that differ in structure or fields → give each its own rule and callback. You are free to split as finely as the site demands. **Different layouts per section?** One spider holds many rules — route each section to its own named callback (one `{"allow": ["/blog/.*"], "callback": "parse_blog"}` per section, each with its own `extract`).

### Step 2C: Test Generic Extractors

Inspect an article page:
```bash
./scrapai inspect https://website.com/article-url --project proj
```

`inspect` auto-escalates transport (plain HTTP → curl_cffi → browser) and reports the lightest one that worked — set the matching flag it names (`CURL_CFFI_ENABLED` or `CLOUDFLARE_ENABLED`). No need to re-run manually; prefer curl_cffi over the browser when it works.

Check if the chosen strategy (Step 2A) holds up on a real page:
- Clean `<article>` tags / semantic HTML → generic extractors work for a core-only schema
- Complex layouts, JS-rendered, sidebars mixed in, or fields coming out wrong → pin selectors with `FIELDS`

### Step 2D: Selector Discovery (only when needed)

```bash
./scrapai analyze data/proj/spider/analysis/page.html
./scrapai analyze data/proj/spider/analysis/page.html --test "h1.article-title"
./scrapai analyze data/proj/spider/analysis/page.html --find "price"
```

**The fast path — read selectors off the screenshot.** When extraction is shaky or a field (especially **date/author**) comes out wrong, `./scrapai inspect <url> --screenshot` a sample content page and `Read` the `page.png` to see the actual values — title, author "John Smith", date "June 20, 2026". Then reverse-search the HTML for the element holding that value:

```bash
./scrapai analyze data/proj/spider/analysis/page.html --find-text "John Smith"
```

`--find-text` returns the element + selector holding the value you saw (even obfuscated classes like `time.css-1a2b3c`), tightest first. (`--find` matches class/id keywords; `--find-text` matches the value you saw.) Confirm with `--test "<selector>"`. This is faster and more reliable than guessing from class names. Doing many pages? Run `./scrapai browser start` so screenshots stay warm.

See [extractors.md](extractors.md) for selector documentation.

### Step 2E: Create final_spider.json

**Naming gate:** the spider `name` MUST equal the domain with dots → underscores (`imn.org` → `imn_org`, `bbc.co.uk` → `bbc_co_uk`). A mismatch silently routes crawls to the wrong `data/<project>/<spider>/` folder.

**Core-only schema (generic extractors):**
```json
{
  "name": "domain_com",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com/blog"],
  "rules": [
    { "allow": ["/blog/[^/]+$"], "callback": "parse_article", "follow": false, "priority": 100 },
    { "allow": ["/blog$"], "callback": null, "follow": true, "priority": 50 }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 0,
    "CONCURRENT_REQUESTS": 32,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
    "AUTOTHROTTLE_ENABLED": false,
    "EXTRACTOR_ORDER": ["trafilatura", "newspaper"]
  }
}
```
(Lower these throughput numbers only if the site is fragile.) Add `FIELDS` directives only to fix fields the generic extractors get wrong.

**Schema with a non-core field (pure-CSS):** Generic extractors are not allowed here — use `["custom"]` plus one `FIELDS` directive per schema field:
```json
{
  "EXTRACTOR_ORDER": ["custom"],
  "FIELDS": {
    "title": { "css": "h1.article-title::text" },
    "content": { "css": "div.article-body" },
    "author": { "css": "span.author-name::text" },
    "published_date": { "css": "time.published-date::attr(datetime)" }
  }
}
```

**Non-article structured data (products / jobs / listings / forums):** route each section to its own named callback, each with its own `extract` block:
```json
{
  "rules": [
    { "allow": ["/product/.*"], "callback": "parse_product" },
    { "allow": ["/review/.*"], "callback": "parse_review" }
  ],
  "callbacks": {
    "parse_product": { "extract": { "name": { "css": "h1.title::text" }, "price": { "css": "span.price::text" } } },
    "parse_review":  { "extract": { "title": { "css": "h1.review-title::text" }, "rating": { "css": "span.stars::attr(data-score)" } } }
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

Create `test_spider.json` with 5 article URLs (`name` MUST be the domain with dots → underscores):
```json
{
  "name": "example_com",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/article-1", "...4 more..."],
  "rules": [{ "deny": [".*"], "callback": null, "follow": false, "priority": 100 }],
  "settings": { "DOWNLOAD_DELAY": 0, "CONCURRENT_REQUESTS": 32, "CONCURRENT_REQUESTS_PER_DOMAIN": 16, "AUTOTHROTTLE_ENABLED": false, "EXTRACTOR_ORDER": ["trafilatura", "newspaper"] }
}
```

```bash
./scrapai spiders import data/proj/spider/analysis/test_spider.json --project proj
./scrapai crawl example_com --limit 5 --project proj
./scrapai show example_com --limit 5 --project proj
```

**Verify every `required: true` field in `project.json` is non-null on every test item.**
**Good:** Correct titles, clean content, every required field populated.
**Bad:** Wrong titles, missing content, any required field null → go back to Phase 2, fix selectors, re-test.

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
- Phase 4A: Extraction quality verified (every `required: true` field non-null on every item)
- Phase 4B: Final spider imported

```bash
./scrapai queue complete <id>     # only if ALL pass
./scrapai queue fail <id> -m "reason"  # if any fail
```

---

## Common Failures & Recovery

**Inspector overwrites files:** NEVER run multiple inspectors in parallel. Each run overwrites `page.html`. Always process output (extract-urls, analyze) before next inspector run.

**Blocked during analysis:** `inspect` auto-escalates plain HTTP → curl_cffi → browser and reports the transport that worked. Set the flag it names in Phase 4: curl_cffi → `CURL_CFFI_ENABLED: true`; browser → `CLOUDFLARE_ENABLED: true`. If plain HTTP works, set no transport flag. Don't reach for the browser when curl_cffi already gets through.

**Bad extraction in 4A:** Go back to Phase 2, fix selectors or switch extractor order. Delete spider if needed:
```bash
echo "y" | ./scrapai spiders delete spider_name --project proj
```
Re-create test_spider.json, re-import, re-test. Do NOT proceed to 4B until extraction is good.

**Do NOT add Cloudflare by default in test_spider.json.** Only add if you confirmed CF protection during analysis. It adds major overhead (visible browser, slower crawling).

**Directory creation:** Never use `mkdir`. Inspector auto-creates `DATA_DIR/<project>/<spider>/analysis/`. Crawl and export commands auto-create their subdirectories. DATA_DIR is configurable in `.env` (default: `./data`).

**Do NOT inspect individual content pages** during Phase 1. Extractors handle content extraction — you only need URL patterns and navigation structure.
