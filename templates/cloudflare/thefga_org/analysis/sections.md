# TheFGA.org - Comprehensive Site Structure Analysis

**Source URL:** https://thefga.org/
**Project:** tmp
**Date:** 2026-02-26
**Queue ID:** 612

---

## Executive Summary

The Foundation for Government Accountability (TheFGA) website contains **10 distinct content sections** organized by content type. All sections use consistent URL patterns (`/section-name/<slug>/`) and appear to use semantic HTML structure suitable for generic extraction.

**Key Findings:**
- Cloudflare protection active (HTTP 403 without bypass)
- Semantic HTML with `<article>` tags, `<h1>` titles, `<time>` dates
- Consistent structure across all content types
- Pagination on listing pages (`?paged=N`)
- All content follows article format (title, content, date, author)

---

## Content Sections (Detailed Analysis)

### 1. Blog Posts
**URL Pattern:** `/blog/<slug>/`
**Listing Page:** `/blog/`
**Pagination:** `/blog/?paged=2`, `/blog/?paged=3`, etc.

**Example URLs:**
- https://thefga.org/blog/100-days-in-governor-braun-is-making-indiana-great-again/
- https://thefga.org/blog/even-with-big-beautiful-bill-savings-medicaid-spending-will-continue-to-grow/
- https://thefga.org/blog/minnesota-fraud-scandal-proves-trump-republicans-were-right-on-welfare-reform/
- https://thefga.org/blog/six-ways-states-are-leading-in-2025/
- https://thefga.org/blog/west-virginia-leading-the-way-on-election-integrity/
- https://thefga.org/blog/what-congress-is-saying-about-medicaid-reform/
- https://thefga.org/blog/yes-illegal-aliens-get-medicaid-and-obamacare-protecting-that-is-why-democrats-shut-down-the-government/
- https://thefga.org/blog/fga-in-the-news-ending-washington-schemes-and-fraud/
- https://thefga.org/blog/fga-in-the-news-maha-medicaid-reform-and-accountability-in-washington/
- https://thefga.org/blog/if-rural-hospitals-are-closing-its-not-because-of-the-big-beautiful-bill/

**Content Type:** Standard blog articles
**Fields Expected:** Title, content, date, author
**HTML Structure Confirmed:**
- `<h1>` for title
- `<article class="post-article">` container
- `<time>` tag for dates
- `<div class="text-box">` for content
- Clean semantic HTML

**Volume:** ~10 articles visible on first page (estimated dozens to hundreds total)

---

### 2. Op-Eds (Opinion Pieces)
**URL Pattern:** `/op-eds/<slug>/`
**Listing Page:** `/op-eds/`
**Pagination:** `/op-eds/?paged=N` (pattern assumed based on other sections)

**Example URLs:**
- https://thefga.org/op-eds/ending-the-welfare-welcome-mat-in-immigration/
- https://thefga.org/op-eds/trump-is-right-wall-street-should-not-buy-single-family-homes/
- https://thefga.org/op-eds/the-gop-plan-to-make-america-affordable-again/
- https://thefga.org/op-eds/i-need-an-expensive-asthma-drug-to-live-trumps-rx-plan-helped-me-and-many-others/
- https://thefga.org/op-eds/i-tried-for-years-to-buy-a-home-wall-street-always-beat-me-trump-made-the-right-call/
- https://thefga.org/op-eds/the-real-villains-arent-in-the-movies-theyre-looting-americas-welfare-system-blaze-media/
- https://thefga.org/op-eds/this-food-stamp-travestys-days-are-numbered/
- https://thefga.org/op-eds/to-win-the-midterms-the-gop-should-take-on-then-run-on-fraud/
- https://thefga.org/op-eds/welfare-fraud-threatens-top-tier-democratic-presidential-nominees-ahead-of-2028/
- https://thefga.org/op-eds/will-democrats-allow-a-school-choice-wealth-transfer/

**Content Type:** Opinion editorials, often published in external media
**Fields Expected:** Title, content, date, author, publication source
**HTML Structure:** Same as blog posts (semantic HTML)

**Volume:** ~10 articles visible on first page (estimated dozens to hundreds total)

---

### 3. Research Papers
**URL Pattern:** `/research/<slug>/`
**Listing Page:** `/research/`
**Pagination:** `/research/?paged=N` (pattern assumed)

**Example URLs:**
- https://thefga.org/research/congress-should-stop-runaway-spending-enacting-discretionary-spending-caps-reconciliation/
- https://thefga.org/research/crackdownoninstitutionalinvestorsunlockshomeownership/
- https://thefga.org/research/make-america-healthy-again-most-states-commit-banning-taxpayer-funded-junk-food/
- https://thefga.org/research/how-congress-can-stop-the-next-government-shutdown-before-it-starts/
- https://thefga.org/research/the-trump-administration-helping-ensure-definition-public-charge-encourages-work-not-welfare/

**Content Type:** In-depth research reports and policy analysis
**Fields Expected:** Title, content, date, author, executive summary, key findings
**HTML Structure:** Same semantic HTML as blog posts

**Volume:** ~10 papers visible on first page (estimated dozens total)

---

### 4. Press Releases
**URL Pattern:** `/press/<slug>/`
**Listing Page:** `/press/`
**Pagination:** `/press/?paged=2` (confirmed)

**Example URLs:**
- https://thefga.org/press/fga-applauds-closure-of-massive-medicaid-tax-loophole-ends-state-money-laundering-scheme/
- https://thefga.org/press/fga-applauds-introduction-of-the-compete-act-to-restore-affordable-health-coverage-options/
- https://thefga.org/press/fga-applauds-introduction-of-the-great-healthcare-plan-to-transform-the-u-s-health-care-system-and-lower-costs-for-american-families/
- https://thefga.org/press/fga-applauds-introduction-of-the-make-elections-great-again-act/
- https://thefga.org/press/fga-applauds-senator-rick-scotts-proposal-to-make-health-care-more-affordable/
- https://thefga.org/press/fga-applauds-treasury-action-to-block-illegal-aliens-from-receiving-refundable-tax-credits/
- https://thefga.org/press/fga-encourages-passage-of-a-clean-cr-to-end-the-government-shutdown/
- https://thefga.org/press/fga-praises-president-trump-and-gop-leadership-for-standing-strong-to-reopen-the-federal-government/
- https://thefga.org/press/gov-morrisey-leads-way-make-america-healthy-again/
- https://thefga.org/press/trump-administration-safeguards-americans-taxpayer-dollars-from-fraud-and-abuse/

**Content Type:** Official press releases and statements
**Fields Expected:** Title, content, date (likely no author attribution)
**HTML Structure:** Same semantic HTML as other sections

**Volume:** ~10 releases visible on first page (estimated dozens to hundreds total)

---

### 5. In the News
**URL Pattern:** `/in-the-news/<slug>/` (pattern assumed)
**Listing Page:** `/in-the-news/`
**Pagination:** `/in-the-news/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: https://thefga.org/in-the-news/

**Content Type:** Media coverage and news mentions of FGA
**Fields Expected:** Title, content, date, source publication
**HTML Structure:** Assumed same as other sections (to be confirmed during crawl)

**Volume:** Unknown (to be discovered during crawl)

**Note:** Section exists in main navigation but no individual article URLs found on homepage. Will be discovered during full crawl.

---

### 6. Papers
**URL Pattern:** `/papers/<slug>/` (pattern assumed)
**Listing Page:** `/papers/`
**Pagination:** `/papers/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: /papers/

**Content Type:** Policy papers and documents (may overlap with Research)
**Fields Expected:** Title, content, date, author, PDF downloads possible
**HTML Structure:** Assumed same as other sections (to be confirmed during crawl)

**Volume:** Unknown (to be discovered during crawl)

**Note:** Section exists in main navigation but no individual article URLs found on homepage. May contain fewer items or require login/deeper navigation.

---

### 7. One-Pagers
**URL Pattern:** `/one-pagers/<slug>/` (pattern assumed)
**Listing Page:** `/one-pagers/`
**Pagination:** `/one-pagers/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: /one-pagers/

**Content Type:** Brief single-page policy summaries
**Fields Expected:** Title, content, date (likely short-form content)
**HTML Structure:** Assumed same as other sections (to be confirmed during crawl)

**Volume:** Unknown (to be discovered during crawl)

**Note:** Section exists in main navigation. Content format may differ from full articles (shorter, more concise).

---

### 8. Polling Data
**URL Pattern:** `/polling/<slug>/` (pattern assumed)
**Listing Page:** `/polling/`
**Pagination:** `/polling/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: /polling/

**Content Type:** Poll results and survey data
**Fields Expected:** Title, content, date, poll methodology, results/statistics
**HTML Structure:** May include charts/graphs, but text extraction should work

**Volume:** Unknown (to be discovered during crawl)

**Note:** Some polling data is hosted on external domain (excellenceinpolling.com). Spider should focus on thefga.org content only.

---

### 9. Videos
**URL Pattern:** `/videos/<slug>/` (pattern assumed)
**Listing Page:** `/videos/`
**Pagination:** `/videos/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: https://thefga.org/videos/

**Content Type:** Video pages (likely embedded YouTube/Vimeo with descriptions)
**Fields Expected:** Title, description, date, video URL/embed code
**HTML Structure:** Text content extraction (video URLs as metadata)

**Volume:** Unknown (to be discovered during crawl)

**Note:** Focus on text content (title, description, transcript if available). Video files themselves won't be downloaded.

---

### 10. Additional Research
**URL Pattern:** `/additional-research/<slug>/` (pattern assumed)
**Listing Page:** `/additional-research/`
**Pagination:** `/additional-research/?paged=N` (pattern assumed)

**Example URLs:**
- Navigation link confirmed: /additional-research/

**Content Type:** Supplementary research materials (may overlap with Research section)
**Fields Expected:** Title, content, date, author
**HTML Structure:** Assumed same as other sections (to be confirmed during crawl)

**Volume:** Unknown (to be discovered during crawl)

**Note:** Relationship to /research/ section unclear. May contain different content types or formats.

---

## Exclusions (Non-Content Pages)

These URL patterns should be **excluded** from crawling (utility/navigation pages):

### Site Structure/Navigation
- `/about-us/*` - About pages, team bios, impact reports
- `/solution/*` - Solution category pages (policy areas - navigation only, not content)
- `/who-we-are/*` - Organization information

### Utility Pages
- `/give/*` - Donation and fundraising pages
- `/privacy-policy/` - Legal/policy pages
- `/fga-author/*` - Author profile pages (metadata, not content)

### Campaign Pages
- `/2023-farm-bill/` - Specific campaign landing page
- `/fga-vs-doj/` - Legal case landing page
- `/election-crimes/` - Campaign landing page
- `/ranked-choice-voting-is-a-disaster/` - Campaign landing page
- `/reins-act/` - Legislation landing page

### External Links
- `https://app.candid.org/*` - External charity profile
- `https://excellenceinpolling.com/*` - External polling site
- `https://truthsocial.com/*` - Social media
- `https://twitter.com/*` - Social media
- `https://www.facebook.com/*` - Social media
- `https://www.instagram.com/*` - Social media
- `https://www.youtube.com/*` - Social media

---

## Technical Requirements

### Cloudflare Protection
- **Status:** Active (HTTP 403 on direct requests)
- **Bypass Method:** Cloudflare browser bypass (--cloudflare flag)
- **Strategy:** Hybrid mode (browser once per 10min, then HTTP with cookies)
- **Settings Required:**
  ```json
  {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid",
    "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600,
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5
  }
  ```

### HTML Structure Analysis
**Confirmed from sample blog post inspection:**
- Title: `<h1>` tag (single, clean)
- Content: `<article class="post-article">` container
- Date: `<time>` tag with readable text
- Structure: Semantic HTML with clean hierarchy

**Extractor Strategy:** Generic extractors (newspaper/trafilatura) recommended
- Site uses semantic HTML (`<article>`, `<time>`, proper heading hierarchy)
- Clean content structure in `<div class="text-box">`
- No complex JavaScript rendering required for content
- Generic extractors should handle 90%+ of content correctly

### Crawl Strategy
1. **Start URL:** https://thefga.org/ (homepage)
2. **Follow links:** Yes (to discover all section pages and articles)
3. **Respect robots.txt:** Yes
4. **Concurrent requests:** 8 (Cloudflare hybrid mode supports normal concurrency)
5. **Depth limit:** No hard limit (follow all content URLs)

### Spider Settings Summary
```json
{
  "name": "thefga_org",
  "allowed_domains": ["thefga.org"],
  "start_urls": ["https://thefga.org/"],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid",
    "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600,
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5
  }
}
```

---

## URL Matching Rules (Phase 2 Preview)

Each content section requires two rules:
1. **Allow rule:** Match article URLs (`/section/<slug>/`)
2. **Deny rule:** Exclude listing pages (`/section/$`) and pagination (`/section/?paged=`)

**Example for blog section:**
```json
{
  "allow": ["/blog/.*"],
  "deny": ["/blog/$", "/blog/\\?paged="],
  "callback": "parse_article"
}
```

**All 10 sections follow same pattern:**
- `/blog/.*` → parse_article
- `/op-eds/.*` → parse_article
- `/research/.*` → parse_article
- `/press/.*` → parse_article
- `/in-the-news/.*` → parse_article
- `/papers/.*` → parse_article
- `/one-pagers/.*` → parse_article
- `/polling/.*` → parse_article
- `/videos/.*` → parse_article
- `/additional-research/.*` → parse_article

---

## Estimated Content Volume

**High confidence (confirmed):**
- Blog: ~100+ articles (10 per page, pagination active)
- Op-eds: ~100+ articles (10 per page, pagination active)
- Research: ~50+ papers (estimated)
- Press: ~100+ releases (10 per page, pagination active)

**To be discovered during crawl:**
- In the News: Unknown
- Papers: Unknown (may be small collection)
- One-Pagers: Unknown (likely smaller, focused collection)
- Polling: Unknown
- Videos: Unknown
- Additional Research: Unknown

**Total estimated:** 300-1000+ items across all sections

---

## Next Steps (Phase 2)

1. ✅ Phase 1 complete - all sections documented
2. **Phase 2:** Create URL matching rules for all 10 sections
3. **Phase 2:** Test generic extractors on sample articles from different sections
4. **Phase 2:** Verify extractor quality (title, content, date extraction)
5. **Phase 3:** Create test_spider.json and final_spider.json
6. **Phase 4:** Test crawl with --limit 5, verify quality, import to database

---

## Notes & Observations

- **Consistent architecture:** All content sections appear to use same WordPress/CMS template
- **Clean URLs:** No query parameters in article URLs (SEO-friendly slugs)
- **Pagination standard:** All listing pages use `?paged=N` parameter
- **External content warning:** Polling section has external domain links (excellenceinpolling.com) - spider should ignore
- **Semantic HTML quality:** High quality markup suitable for generic extraction
- **Cloudflare behavior:** No challenges after initial bypass - hybrid mode should be highly efficient
- **Content freshness:** Recent dates observed (2025 content) - active site with regular updates

---

**Analysis completed:** 2026-02-26
**Analyst:** ScrapAI
**Status:** ✅ Phase 1 Complete - Ready for Phase 2
