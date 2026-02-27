# BBC.co.uk - Comprehensive Site Structure Analysis

**Source URL:** https://bbc.co.uk/
**Project:** tmp
**Date:** 2026-02-26
**Queue ID:** 613

---

## Executive Summary

BBC (British Broadcasting Corporation) is one of the world's largest news organizations with extensive content across news, sport, entertainment, education, and lifestyle categories. The site contains **6 primary content sections** with hundreds of subsections and categories.

**Key Findings:**
- No Cloudflare protection (regular HTTP works fine)
- Semantic HTML with `<article>` tags, `<h1>` titles, `<time>` dates
- Consistent structure across all content types
- New URL format: `/section/articles/<id>` (hashed IDs)
- Legacy URL format: `/section/<number>` (numeric IDs)
- Regional editions: England, Scotland, Wales, Northern Ireland
- Massive content volume (millions of articles)

---

## Content Sections (Detailed Analysis)

### 1. News Articles
**URL Pattern:** `/news/articles/<id>` (primary) + `/news/<number>` (legacy)
**Homepage:** `/news`
**Category Structure:** `/news/<category>`

**Article Examples (New Format):**
- https://www.bbc.co.uk/news/articles/cgjz1x5e1xyo (Spain-Gibraltar border)
- https://www.bbc.co.uk/news/articles/c1mjx1grj3yo
- https://www.bbc.co.uk/news/articles/c2k8zyq0qgzo
- https://www.bbc.co.uk/news/articles/c4gjm82lj3jo
- https://www.bbc.co.uk/news/articles/c5y4jpjlp41o
- https://www.bbc.co.uk/news/articles/c5y68gd0gm3o
- https://www.bbc.co.uk/news/articles/c70k5eje4p9o
- https://www.bbc.co.uk/news/articles/c80j3rlp904o
- https://www.bbc.co.uk/news/articles/c86y466v0x6o
- https://www.bbc.co.uk/news/articles/cgjz1x5e1xyo

**Article Examples (Legacy Format):**
- https://www.bbc.co.uk/news/10628994
- https://www.bbc.co.uk/news/20039682

**News Categories/Subsections:**
- `/news/business` - Business and finance news
- `/news/disability` - Disability news and issues
- `/news/education` - Education sector news
- `/news/entertainment_and_arts` - Entertainment, arts, culture
- `/news/health` - Health and medical news
- `/news/politics` - UK and international politics
- `/news/science_and_environment` - Science, climate, environment
- `/news/technology` - Technology and digital news
- `/news/newsbeat` - Youth-focused news
- `/news/in_pictures` - Photo galleries

**Regional News:**
- `/news/england` - England news (with local subsections)
  - `/news/england/manchester`
  - `/news/england/merseyside`
  - `/news/england/nottingham`
  - `/news/england/lincolnshire`
  - `/news/england/suffolk`
  - `/news/england/wiltshire`
  - (Many more regional subsections)
- `/news/scotland` - Scotland news
  - `/news/scotland/glasgow_and_west`
- `/news/wales` - Wales news
- `/news/northern_ireland` - Northern Ireland news
- `/news/uk` - UK-wide news
- `/news/regions` - Regional news hub

**World News:**
- `/news/world` - International news
  - `/news/world/us_and_canada`
  - `/news/world/asia`
  - (Many more regional subsections)

**Special Sections:**
- `/news/bbcindepth` - In-depth features and analysis
- `/news/bbcverify` - Fact-checking and verification

**Live Coverage:**
- `/news/live/<id>` - Live rolling news coverage

**News Videos:**
- `/news/videos/<id>` - Standalone video stories

**Content Type:** News articles, analysis, features
**Fields Expected:** Title, content, date, author/byline, category
**HTML Structure Confirmed:**
- `<h1 class="ssrcss-zwdxc1-Heading">` for title
- `<article class="ssrcss-hmqe3h-ArticleWrapper">` container
- `<time>` tag with readable dates
- `<div class="ssrcss-nqezkk-RichTextContainer">` for content paragraphs
- Clean semantic HTML structure

**Volume:** Millions of articles (active since 1920s, massive archive)

---

### 2. Sport Content
**URL Pattern:** `/sport/<sport>/articles/<id>` (primary) + `/sport/<number>` (legacy)
**Homepage:** `/sport`
**Category Structure:** `/sport/<sport>`

**Article Examples (New Format):**
- https://www.bbc.co.uk/sport/cricket/articles/ce3gyx49z52o (T20 World Cup)
- https://www.bbc.co.uk/sport/football/articles/c80jg0v5d95o
- https://www.bbc.co.uk/sport/boxing/articles/c05v9rjyvedo
- https://www.bbc.co.uk/sport/darts/articles/c4g5zj97w42o

**Article Examples (Legacy Format):**
- https://www.bbc.co.uk/sport/15561348
- https://www.bbc.co.uk/sport/15890345

**Sport Categories:**
- `/sport/football` - Football/soccer (largest category)
  - `/sport/football/champions-league`
  - `/sport/football/european`
  - `/sport/football/teams/<team>` (e.g., /sport/football/teams/celtic)
- `/sport/cricket` - Cricket
  - `/sport/cricket/teams/<team>` (e.g., /sport/cricket/teams/england)
- `/sport/rugby-union` - Rugby union
  - `/sport/rugby-union/teams/<team>` (e.g., /sport/rugby-union/teams/england)
- `/sport/formula1` - Formula 1 racing
- `/sport/boxing` - Boxing
- `/sport/american-football` - American football/NFL
- `/sport/athletics` - Athletics/track and field
- `/sport/basketball` - Basketball
- `/sport/cycling` - Cycling
- `/sport/darts` - Darts
- `/sport/disability-sport` - Paralympic and disability sports
- `/sport/all-sports` - All sports index

**Regional Sport:**
- `/sport/england` - England regional sport

**Live Sport Coverage:**
- `/sport/<sport>/live/<id>` - Live sport coverage and commentary
  - Example: `/sport/football/live/ce8wz53xn0gt`

**Sport Videos:**
- `/sport/<sport>/videos/<id>` - Sport video highlights and features
  - `/sport/boxing/videos/c4g2ke9jg7go`
  - `/sport/cricket/videos/c2e4jl0gm2ro`
  - `/sport/football/videos/<id>`

**Content Type:** Sport news, match reports, analysis, features
**Fields Expected:** Title, content, date, author, sport category, team tags
**HTML Structure:** Same as news articles (semantic HTML)

**Volume:** Hundreds of thousands of articles (decades of sports coverage)

---

### 3. Food Articles
**URL Pattern:** `/food/articles/<id>`
**Homepage:** `/food`
**Collections:** `/food/collections/<topic>`

**Article Examples:**
- https://www.bbc.co.uk/food/articles/c0q45xx5g03o (Food noise phenomenon)
- https://www.bbc.co.uk/food/articles/dentist_advice_food_white_teeth

**Recipe Collections:**
- https://www.bbc.co.uk/food/collections/10-minute_meals
- https://www.bbc.co.uk/food/collections/high_protein_dinners

**Content Type:** Food articles, health/nutrition features, recipe guides
**Fields Expected:** Title, content, date, author, category, related recipes
**HTML Structure Confirmed:**
- `<h1 class="ssrcss-zwdxc1-Heading">` for title
- `<article class="ssrcss-hmqe3h-ArticleWrapper">` container
- `<time>` tag with dates
- `<div class="ssrcss-nqezkk-RichTextContainer">` for content
- Same semantic structure as news articles

**Volume:** Thousands of articles (food features, not just recipes)

**Note:** BBC Food also contains recipes, but those may use different URL patterns (e.g., `/food/recipes/*`). Focus on `/food/articles/*` for text content.

---

### 4. Bitesize (Educational Content)
**URL Pattern:** `/bitesize/articles/<id>`
**Homepage:** `/bitesize`

**Article Examples:**
- https://www.bbc.co.uk/bitesize/articles/z74wrmn (Business success stories)
- https://www.bbc.co.uk/bitesize/articles/zw24ywx
- https://www.bbc.co.uk/bitesize/articles/zsry239

**Content Type:** Educational articles, study guides, career advice, learning resources
**Fields Expected:** Title, content, date, education level, subject tags
**HTML Structure:** Similar to news articles (semantic HTML)

**Volume:** Tens of thousands of educational articles (primary through university level)

**Note:** Bitesize also includes interactive lessons, videos, quizzes. Focus on `/bitesize/articles/*` for article content.

---

### 5. Newsround (Children's News)
**URL Pattern:** `/newsround/articles/<id>`
**Homepage:** `/newsround`

**Article Examples:**
- https://www.bbc.co.uk/newsround/articles/c5ykx6xng0qo (Roman staircase discovery)

**Content Type:** Age-appropriate news for children (6-12 years old)
**Fields Expected:** Title, content, date, simplified language for young readers
**HTML Structure:** Similar to news articles (semantic HTML)

**Volume:** Thousands of children's news articles

---

### 6. Media Centre
**URL Pattern:** `/mediacentre/articles/<year>/<slug>`
**Homepage:** `/mediacentre`

**Article Examples:**
- https://www.bbc.co.uk/mediacentre/articles/2026/the-claudia-winkleman-show

**Content Type:** Press releases, programme announcements, corporate news
**Fields Expected:** Title, content, date, programme tags
**HTML Structure:** Assumed similar to other sections

**Volume:** Thousands of press releases and corporate announcements

---

## Non-Article Content (Optional to Include)

### iPlayer Episodes
**URL Pattern:** `/iplayer/episode/<id>`
**Type:** TV programmes/episodes (video content, not articles)
**Include in spider?** Optional - primarily video metadata

### Sounds
**URL Pattern:** `/sounds/play/<id>` or `/sounds/brand/<id>`
**Type:** Radio programmes, podcasts, audio content
**Include in spider?** Optional - primarily audio metadata

### Videos
**URL Pattern:** `/videos/<id>`
**Type:** Standalone video content
**Include in spider?** Optional - video metadata only

---

## Regional Language Editions

BBC operates separate language/regional sites:
- `/alba` - BBC Alba (Scottish Gaelic)
- `/cymru` - BBC Cymru (Welsh language)
- `/cymrufyw` - BBC Cymru Fyw (Welsh news)
- `/naidheachdan` - BBC Naidheachdan (Scottish Gaelic news)
- `/northernireland` - BBC Northern Ireland
- `/scotland` - BBC Scotland
- `/wales` - BBC Wales

**Include in spider?** Yes for main article content, but respect domain boundaries (bbc.co.uk only, not separate bbc.com domains).

---

## Exclusions (Non-Content Pages)

### Utility/Navigation
- `/aboutthebbc/*` - Corporate information
- `/usingthebbc/*` - Terms, privacy, cookies
- `/contact/*` - Contact forms
- `/accessibility/*` - Accessibility information
- `/search` - Search pages
- `/reception/` - Early years content (separate section)

### Programme Pages (Not Articles)
- `/iplayer/episodes/*` - TV series pages
- `/programmes/*` - Programme index pages
- `/sounds/my/*` - Personal playlists

### Account/User Pages
- `https://account.bbc.com/*` - User account pages
- `/notifications` - Notification settings
- `/iplayer/watchlist` - Personal watchlists
- `/sounds/my/subscribed` - Personal subscriptions

### External Links
- `https://www.bbc.com/*` - International BBC site (different domain)

### Special Features
- `/news/topics/*` - Topic aggregation pages (not articles)
- `/news/help-*` - Help pages

### Comment Sections
- All URLs ending with `#comments` - Comment sections (duplicates of article URLs)

---

## Technical Requirements

### HTTP Access
- **Status:** No protection (HTTP works fine)
- **Bypass Method:** Not needed - regular lightweight HTTP fetch
- **Settings Required:** None (default Scrapy settings work)

### HTML Structure Analysis
**Confirmed from multiple article inspections:**
- Title: `<h1 class="ssrcss-*-Heading">` tag
- Content: `<article class="ssrcss-*-ArticleWrapper">` container
- Date: `<time>` tag with readable text (e.g., "11 February 2026")
- Content paragraphs: `<div class="ssrcss-nqezkk-RichTextContainer">`
- Clean semantic HTML throughout

**Extractor Strategy:** Generic extractors (newspaper/trafilatura) recommended
- Site uses clean semantic HTML
- Consistent structure across all sections
- `<article>`, `<time>`, proper heading hierarchy
- Generic extractors should handle 95%+ of content correctly

### Crawl Strategy
1. **Start URL:** https://www.bbc.co.uk/ (homepage)
2. **Follow links:** Yes (to discover all article URLs)
3. **Respect robots.txt:** Yes
4. **Concurrent requests:** 16 (default, no restrictions needed)
5. **Depth limit:** No hard limit (follow all content URLs)
6. **Politeness:** DOWNLOAD_DELAY = 1 second (respect BBC servers)

### URL ID Format
BBC uses **hashed IDs** (not sequential numbers):
- New format: `c0q45xx5g03o`, `cgjz1x5e1xyo`, `ce3gyx49z52o`
- Legacy format: `10628994`, `20039682` (numeric)
- No predictable pattern - must crawl from homepage/sections

### Spider Settings Summary
```json
{
  "name": "bbc_co_uk",
  "allowed_domains": ["bbc.co.uk", "www.bbc.co.uk"],
  "start_urls": ["https://www.bbc.co.uk/"],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
    "DOWNLOAD_DELAY": 1,
    "CONCURRENT_REQUESTS": 16,
    "ROBOTSTXT_OBEY": true
  }
}
```

---

## URL Matching Rules (Phase 2 Preview)

### News Articles
```json
{
  "allow": ["/news/articles/.*"],
  "deny": ["/news/articles/.*#comments"],
  "callback": "parse_article"
}
```

### Legacy News
```json
{
  "allow": ["/news/[0-9]+$"],
  "callback": "parse_article"
}
```

### Sport Articles
```json
{
  "allow": ["/sport/.*/articles/.*"],
  "deny": ["/sport/.*/articles/.*#comments"],
  "callback": "parse_article"
}
```

### Legacy Sport
```json
{
  "allow": ["/sport/[0-9]+$"],
  "callback": "parse_article"
}
```

### Food Articles
```json
{
  "allow": ["/food/articles/.*"],
  "callback": "parse_article"
}
```

### Bitesize Articles
```json
{
  "allow": ["/bitesize/articles/.*"],
  "deny": ["/bitesize/articles/.*#z.*"],
  "callback": "parse_article"
}
```

### Newsround Articles
```json
{
  "allow": ["/newsround/articles/.*"],
  "deny": ["/newsround/articles/.*#comments"],
  "callback": "parse_article"
}
```

### Media Centre
```json
{
  "allow": ["/mediacentre/articles/.*"],
  "callback": "parse_article"
}
```

**Exclusion Rules (Apply to all):**
- Deny: `/iplayer/.*` (video content, not articles)
- Deny: `/sounds/.*` (audio content, not articles)
- Deny: `.*#comments$` (comment sections)
- Deny: `/aboutthebbc/.*` (corporate pages)
- Deny: `/usingthebbc/.*` (legal pages)
- Deny: `/contact/.*` (utility pages)
- Deny: `/search.*` (search pages)

---

## Estimated Content Volume

**News:** 5-10 million articles (decades of archive)
- Business: ~500K+ articles
- Politics: ~1M+ articles
- Technology: ~300K+ articles
- Health: ~200K+ articles
- Regional: ~2M+ articles (England, Scotland, Wales, NI)
- World: ~3M+ articles

**Sport:** 2-5 million articles
- Football: ~2M+ articles (largest)
- Cricket: ~500K+ articles
- Rugby: ~300K+ articles
- Formula 1: ~100K+ articles
- Other sports: ~500K+ articles

**Food:** ~20K+ articles

**Bitesize:** ~50K+ educational articles

**Newsround:** ~10K+ children's news articles

**Media Centre:** ~5K+ press releases

**Total estimated:** 10-20 million articles (one of the world's largest news archives)

**Recommendation:** For testing, use `--limit` heavily. For production, consider:
- Crawling specific categories only
- Date-based filtering (recent articles only)
- Incremental crawling with DELTAFETCH

---

## Notes & Observations

- **Massive scale:** BBC is one of the largest news sites globally - crawling everything is a multi-week project
- **Clean architecture:** Consistent URL patterns and HTML structure make scraping reliable
- **No paywalls:** All content is free and publicly accessible (funded by UK license fee)
- **Regional diversity:** Extensive local/regional news coverage across UK
- **Language editions:** Welsh and Scottish Gaelic content available
- **Legacy compatibility:** Both new (hashed) and old (numeric) URL formats still active
- **Comment sections:** Many articles have `#comments` anchors - these should be deduplicated
- **Live coverage:** Special handling may be needed for live rolling coverage pages
- **Video/audio metadata:** iPlayer and Sounds content could be included for metadata but not full transcripts
- **Robots.txt compliance:** BBC likely has comprehensive robots.txt - respect it
- **Rate limiting:** Be polite - use DOWNLOAD_DELAY and don't overwhelm their servers

---

## Recommended Crawl Approach

Given the massive scale (10M+ articles), recommend one of these strategies:

### Option 1: Category-Focused
Crawl specific categories only:
```json
{
  "allow": [
    "/news/articles/.*",
    "/sport/football/articles/.*",
    "/sport/cricket/articles/.*"
  ]
}
```

### Option 2: Time-Bounded
Crawl recent articles only (last 1-5 years):
- Implement date extraction and filtering
- Use DELTAFETCH for incremental updates

### Option 3: Full Archive (Advanced)
Full crawl with checkpoint support:
- Expect: weeks/months of crawling
- Use DELTAFETCH
- Enable checkpoint/resume
- Monitor storage (10M articles = ~50-100GB compressed)

---

**Analysis completed:** 2026-02-26
**Analyst:** ScrapAI
**Status:** ✅ Phase 1 Complete - Ready for Phase 2

**WARNING:** This is a massive-scale crawl. Recommend starting with category-focused or time-bounded approach for testing before attempting full archive crawl.
