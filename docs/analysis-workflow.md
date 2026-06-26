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

## Phase 2: Section & Extraction Authoring

### Step 2A: Write one section per kind of page — read `project.json` FIRST

The recommended authoring format is top-level **`sections`**: a list where each entry is one **kind of page** the crawl meets (one article layout, one product layout, the listing pages that just link onward). A section says *which URLs it matches* and *how to extract from them* — and that single list replaces hand-writing `rules` + `callbacks` + `settings.FIELDS`. (`sections` is desugared into exactly that older shape at import — see Step 2E. The legacy format is still fully supported; it is simply what `sections` compiles to.)

Before writing sections, read `data/<project>/project.json`. Every field marked `required: true` in its schema must be sourced by some section, and one repeating concept gets one section.

A section is an object:

```json
{ "match": ["/articles/.*"], "extract": <spec>, "follow": true, "priority": 100 }
```

- **`match`** — list of URL regexes the section applies to (absent = match all).
- **`follow`** — whether to follow links found on these pages (default `true`).
- **`priority`** — optional `0`–`1000`; higher is evaluated first.
- Optional link-extractor knobs carried straight onto the rule: **`deny`**, **`restrict_xpaths`**, **`restrict_css`**, **`tags`**.

**`extract` is exactly one of three things:**

1. **Absent** → follow-only navigation. The page is crawled for links but nothing is extracted from it. This is the listing/index section.
2. **`"auto"`** → the built-in article reader fills the four core fields (`title`, `content`, `author`, `published_date`). Use this for ordinary article/blog pages.
3. **A per-field dict** `{ field: value }` → one entry per schema field. Each value is either:
   - **`"auto"`** — valid **only** for the four core fields (`title`, `content`, `author`, `published_date`); and
   - a **directive** `{ "css" | "xpath": "...", "get_all"?, "to_text"?, "to_markdown"?, "processors"? }` for any field, core or not.

**The rule:** keep `"auto"` for the core fields the reader gets right; add a selector only for fields it can't produce (anything non-core) or gets wrong. A non-core field like `images` does **not** mean hand-write `content` — keep `content` on `"auto"` and just add the `images` selector.

- **Article / blog page** → `"extract": "auto"` (all four core fields).
- **Article that also needs extras** (images, a pdf link, a stubborn author) → keep the core fields on `"auto"` and add a selector per extra: `{ "title": "auto", "content": "auto", "images": {"css": "…"} }`.
- **Non-article page** (product, job — there's no article body for the reader to find) → a directive per field.
- **Listing / index / navigation page** → omit `extract` (follow-only).

**Mixing `"auto"` with an override:** a section may pair `"auto"` core fields with a selector override for a specific field (e.g. a stubborn `author`). That override path is **spider-wide** (it writes the global `FIELDS`), so **at most one section per spider** may mix `"auto"` with overrides. Other sections must give explicit selectors for every field.

**Validation (enforced at import):** `"auto"` on a non-core field is rejected — give it a selector. Every `required: true` schema field must be sourced by some section.

**Sitemaps work with `sections`:** add `"USE_SITEMAP": true` to `settings` and the sitemap enumerates the URLs while your sections do the extraction — you get sitemap completeness *and* the generic reader + custom fields together. (Keep a `match` per content type; you don't need follow-only navigation sections in sitemap mode.)

**Still authored the legacy way (not yet expressible as `sections`):** listing→detail (`iterate`), `ajax_nested_list`, and JS `PAGINATED_LISTINGS`. For these, write `rules` + `callbacks`/`settings` directly as documented below. Transport, throughput, `PDF_MODE`, DeltaFetch, `USE_SITEMAP` all stay in top-level `settings`, never per-section.

### Step 2B: Map each section from sections.md

**A spider is not one function.** Write as many sections as the site has kinds of pages — never force structurally-different pages through one extract spec. Same article layout everywhere → one `"extract": "auto"` section is right. Pages that differ in structure or fields → give each its own section with its own `match` and `extract`. You are free to split as finely as the site demands.

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

**The shape — a `sections` list.** Each kind of page from `sections.md` becomes one section; transport/throughput stay in top-level `settings`:

```json
{
  "name": "domain_com",
  "allowed_domains": ["domain.com"],
  "start_urls": ["https://domain.com/articles"],
  "sections": [
    { "match": ["/articles/.*"], "extract": { "title": "auto", "content": "auto", "author": { "css": ".byline a::text" } } },
    { "match": ["/products/.*"], "extract": { "name": { "css": "h1::text" }, "price": { "css": ".price::text" } } },
    { "match": [".*"], "follow": true }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 0,
    "CONCURRENT_REQUESTS": 32,
    "CONCURRENT_REQUESTS_PER_DOMAIN": 16,
    "AUTOTHROTTLE_ENABLED": false
  }
}
```

Reading it top to bottom: the article section reads core fields with `"auto"` but pins `author` with a selector (the one allowed `auto` + override section); the product section gives one directive per non-core field; the final `{ "match": [".*"], "follow": true }` is the follow-only listing/navigation section. (Lower the throughput numbers only if the site is fragile.)

**Plain article site (core fields only):** one `"auto"` article section plus a follow-only navigation section:
```json
{
  "sections": [
    { "match": ["/blog/[^/]+$"], "extract": "auto", "follow": false, "priority": 100 },
    { "match": ["/blog$"], "follow": true, "priority": 50 }
  ]
}
```

**Non-article structured data (products / jobs / listings / forums):** one section per layout, each a per-field dict. A directive may carry `get_all`, `to_text`, `to_markdown`, and `processors`:
```json
{
  "sections": [
    { "match": ["/product/.*"], "extract": { "name": { "css": "h1.title::text" }, "price": { "css": "span.price::text" } } },
    { "match": ["/review/.*"],  "extract": { "title": { "css": "h1.review-title::text" }, "rating": { "css": "span.stars::attr(data-score)" } } }
  ]
}
```

**Section knobs:**
- Extraction sections: `"extract": "auto"` or a per-field dict, usually `"follow": false` — content pages
- Navigation sections: omit `extract`, `"follow": true` — for discovering links
- Block unwanted pages: `"deny": [...]` on a section
- Higher `"priority"` evaluated first

**Legacy format (still supported).** `sections` is desugared at import (`core/sections.py`) into the older `rules` + `callbacks` + `settings.FIELDS` shape, which still imports and crawls identically. You author that shape directly only for the features `sections` does not yet cover (`iterate`, `ajax_nested_list`, JS `PAGINATED_LISTINGS`). It routes by `project.json` schema:

- **Core-only schema** → `"EXTRACTOR_ORDER": ["trafilatura", "newspaper"]`; add `FIELDS` only to fix wrong guesses.
- **Schema with ANY non-core field** → `"EXTRACTOR_ORDER": ["custom"]` plus one `FIELDS` directive per schema field. Mixing generic extractors with a non-core schema is **REJECTED on import** (`core/schema_validator.py`).
- **Products / jobs / listings / forums** → named `rules` + `callbacks`, one callback per layout.

```json
{
  "rules": [
    { "allow": ["/blog/[^/]+$"], "callback": "parse_article", "follow": false, "priority": 100 },
    { "allow": ["/blog$"], "callback": null, "follow": true, "priority": 50 }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["custom"],
    "FIELDS": {
      "title": { "css": "h1.article-title::text" },
      "content": { "css": "div.article-body" },
      "author": { "css": "span.author-name::text" },
      "published_date": { "css": "time.published-date::attr(datetime)" }
    }
  }
}
```

---

## Phase 3: Prepare Spider Configuration

Create `test_spider.json` and `final_spider.json`. Do NOT import yet — importing happens in Phase 4.

---

## Phase 4: Execution & Verification

### Step 4A: Test Extraction (5 articles)

Create `test_spider.json` with 5 article URLs (`name` MUST be the domain with dots → underscores). Reuse the same `sections` you wrote for the final spider, but add a leading follow-only `deny: [".*"]` section so the test extracts the 5 start URLs without crawling outward:
```json
{
  "name": "example_com",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com/article-1", "...4 more..."],
  "sections": [
    { "match": [".*"], "extract": "auto", "follow": false, "deny": [".*"], "priority": 100 }
  ],
  "settings": { "DOWNLOAD_DELAY": 0, "CONCURRENT_REQUESTS": 32, "CONCURRENT_REQUESTS_PER_DOMAIN": 16, "AUTOTHROTTLE_ENABLED": false }
}
```
(Swap `"extract": "auto"` for the same per-field dict your final spider uses, so the test exercises the real selectors.)

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
- Phase 2: Sections consolidated in `final_spider.json` (one per kind of page)
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
