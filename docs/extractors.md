# Extractors

Test generic extractors (newspaper, trafilatura) first. Only use custom selectors if they fail.

## Discovery Workflow

**Step 1: Inspect article page**
```bash
./scrapai inspect https://example.com/article-url --project proj
```

**Step 2: Analyze HTML structure**
```bash
./scrapai analyze data/proj/spider/analysis/page.html
```
Shows: h1/h2 titles with classes, content containers by size, date elements, author elements.

**Step 3: Test selectors**
```bash
./scrapai analyze data/proj/spider/analysis/page.html --test "h1.article-title"
./scrapai analyze data/proj/spider/analysis/page.html --test "div.article-body"
```

**Step 4: Search for specific fields**
```bash
./scrapai analyze data/proj/spider/analysis/page.html --find "price"
```

## Extractor Order Options

| Config | When to use |
|--------|------------|
| `["newspaper", "trafilatura"]` | Generic extractors work (clean news/blog HTML) |
| `["custom", "newspaper", "trafilatura"]` | Generic extractors fail; custom selectors needed |
| `["playwright", "custom"]` | JS-rendered content (SPAs, dynamic loading) |
| `["playwright", "trafilatura"]` | JS-rendered, generic extractors work after rendering |

## Custom Selectors JSON

**Standard fields** (title, author, content, date) → main DB columns.
**Any other field** → stored in `metadata` JSON column.

**News article:**
```json
{
  "CUSTOM_SELECTORS": {
    "title": "h1.article-title",
    "content": "div.article-body",
    "author": "span.author-name",
    "date": "time.published-date",
    "category": "a.category-link",
    "tags": "div.tags a"
  }
}
```

**E-commerce product:**
```json
{
  "CUSTOM_SELECTORS": {
    "title": "h1.product-name",
    "content": "div.product-description",
    "price": "span.price-value",
    "rating": "div.star-rating",
    "stock": "span.availability",
    "brand": "div.brand-name"
  }
}
```

**Forum thread:**
```json
{
  "CUSTOM_SELECTORS": {
    "title": "h1.thread-title",
    "author": "span.username",
    "content": "div.post-content",
    "date": "time.post-date",
    "upvotes": "span.vote-count"
  }
}
```

## Playwright Wait Configuration

For JS-rendered or delayed content:

```json
{
  "EXTRACTOR_ORDER": ["playwright", "trafilatura"],
  "PLAYWRIGHT_WAIT_SELECTOR": ".article-content",
  "PLAYWRIGHT_DELAY": 5
}
```

- `PLAYWRIGHT_WAIT_SELECTOR`: CSS selector to wait for (max 30s)
- `PLAYWRIGHT_DELAY`: Extra seconds after page load

## Infinite Scroll

For single-page sites with dynamic scroll loading:

```json
{
  "EXTRACTOR_ORDER": ["playwright", "trafilatura"],
  "PLAYWRIGHT_WAIT_SELECTOR": ".quote",
  "PLAYWRIGHT_DELAY": 2,
  "INFINITE_SCROLL": true,
  "MAX_SCROLLS": 10,
  "SCROLL_DELAY": 2.0
}
```

- `INFINITE_SCROLL`: Enable scroll behavior (default: false)
- `MAX_SCROLLS`: Max scrolls to perform (default: 5)
- `SCROLL_DELAY`: Seconds between scrolls (default: 1.0)

Requires `playwright` in `EXTRACTOR_ORDER`. Set `follow: false` in rules.

## Selector Discovery Principles

1. Target MAIN content element — not navigation, sidebar, or footer
2. Selector should match ONE element per page — verify uniqueness
3. Prefer specific classes (`.article-title`) over generic (`.title`)
4. Test on multiple articles — selector must work across pages
5. Prefer semantic tags (`<article>`, `<time>`, `<h1>`)
6. Content selector should return >500 chars; title >10 chars
7. Avoid dynamic/random class names

**Common mistakes:** selector matches multiple elements (gets first, often wrong); selector targets sidebar/footer instead of main content; overly generic selectors like `div.text`; guessing without testing on actual HTML.

## Identifying JS-Rendered Sites

Signs that `page.html` needs Playwright:
- Minimal/empty content, just `<div id="app"></div>`
- Content exists only in `<script>` tags as JS data objects
- "Loading..." placeholder elements
→ Use `["playwright", ...]` in `EXTRACTOR_ORDER`

## Playwright Wait: Common Selectors

`.article-content`, `.quote`, `#posts`, `.loaded`, `[data-loaded="true"]`
