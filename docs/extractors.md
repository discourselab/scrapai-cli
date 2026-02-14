# Extractor Options

## Extraction Strategy

**The system supports both generic extractors and custom selectors with flexible fallback.**

**During Analysis:** Test generic extractors (newspaper, trafilatura) first. Only write custom selectors if they fail to extract content correctly.

**During Crawling:** Configure `EXTRACTOR_ORDER` to control which extractors to try in sequence. The spider will try each extractor in order until one succeeds.

**Extract ANY fields from ANY page type** using custom CSS selectors when needed.

**Why custom selectors:**
- **Precision**: Target exact elements, no guessing
- **Flexibility**: Extract ANY field (prices, ratings, specs, votes, views, etc.)
- **Reliability**: Always get the right content, not navigation/sidebar/footer
- **Universal**: Works with any page type (articles, products, forums, profiles, events)
- **Flexible storage**: Standard fields (title/author/content/date) + unlimited custom fields in metadata

### Discovery Workflow

**Step 1: Fetch and Inspect Article HTML**
```bash
# Use inspector with CF bypass to get full rendered HTML
source .venv/bin/activate && bin/inspector --url https://example.com/article-url --cloudflare
```

**Step 2: Analyze HTML Structure**

Use the selector analyzer tool to discover selectors:

```bash
# Analyze HTML and get selector suggestions
source .venv/bin/activate && bin/analyze_selectors data/example_com/analysis/page.html
```

This will show:
- All h1/h2 titles with their CSS classes
- Content containers sorted by size
- Date elements
- Author elements

**Alternative: Manual Analysis with BeautifulSoup**

If you need custom analysis:

```python
from bs4 import BeautifulSoup

with open('data/example_com/analysis/page.html') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

# Find title (look for h1, h2 tags)
print("=== TITLES ===")
for tag in ['h1', 'h2']:
    for el in soup.find_all(tag):
        classes = '.'.join(el.get('class', []))
        print(f"{tag}.{classes}: {el.get_text()[:60]}")

# Find content containers (look for article, div with content/body classes)
print("\n=== CONTENT CONTAINERS ===")
for el in soup.find_all(['article', 'div', 'section']):
    classes = el.get('class', [])
    class_str = '.'.join(classes)
    if any(word in str(classes).lower() for word in ['article', 'content', 'body', 'text', 'post']):
        text_len = len(el.get_text(strip=True))
        print(f"{el.name}.{class_str}: {text_len} chars")

# Find date elements
print("\n=== DATES ===")
for el in soup.find_all(['time', 'span', 'div']):
    classes = el.get('class', [])
    if any(word in str(classes).lower() for word in ['date', 'time', 'published']):
        print(f"{el.name}.{'.'.join(classes)}: {el.get_text()[:30]}")

# Find author elements
print("\n=== AUTHORS ===")
for el in soup.find_all(['span', 'div', 'a']):
    classes = el.get('class', [])
    if any(word in str(classes).lower() for word in ['author', 'byline', 'writer']):
        print(f"{el.name}.{'.'.join(classes)}: {el.get_text()[:30]}")
```

**Step 3: Test Selectors**

Use the analyzer to test each selector:

```bash
# Test title selector
source .venv/bin/activate && bin/analyze_selectors data/example_com/analysis/page.html --test "h1.article-title"
```
```bash
# Test content selector
source .venv/bin/activate && bin/analyze_selectors data/example_com/analysis/page.html --test "div.article-body"
```
```bash
# Test date selector
source .venv/bin/activate && bin/analyze_selectors data/example_com/analysis/page.html --test "time.published-date"
```

This shows:
- How many elements match
- The text content of each match
- Whether it's the right element

**Step 4: Create Spider with Custom Selectors**

**Example 1: News Article**
```json
{
  "name": "news_spider",
  "settings": {
    "CUSTOM_SELECTORS": {
      "title": "h1.article-title",
      "author": "span.author-name",
      "content": "div.article-body",
      "date": "time.published-date",
      "category": "a.category-link",
      "tags": "div.tags a"
    }
  }
}
```

**Example 2: E-commerce Product**
```json
{
  "name": "product_spider",
  "settings": {
    "CUSTOM_SELECTORS": {
      "title": "h1.product-name",
      "content": "div.product-description",
      "price": "span.price-value",
      "rating": "div.star-rating",
      "reviews_count": "span.review-count",
      "stock": "span.availability",
      "brand": "div.brand-name",
      "sku": "span.product-sku",
      "images": "div.product-images img"
    }
  }
}
```

**Example 3: Forum Thread**
```json
{
  "name": "forum_spider",
  "settings": {
    "CUSTOM_SELECTORS": {
      "title": "h1.thread-title",
      "author": "span.username",
      "content": "div.post-content",
      "date": "time.post-date",
      "upvotes": "span.vote-count",
      "replies_count": "span.reply-count",
      "views": "span.view-count"
    }
  }
}
```

### How It Works

1. **Custom selectors are optional** - use when generic extractors fail or for complex content
2. **Extraction**: Uses BeautifulSoup with your CSS selectors
3. **Standard fields**: title, author, content, date -> mapped to main columns in database
4. **ANY other field**: stored in metadata JSON (price, rating, category, tags, etc.)

**You can extract ANYTHING:**
```json
{
  "CUSTOM_SELECTORS": {
    "title": "h1.product-name",
    "price": "span.price-value",
    "rating": "div.star-rating",
    "stock": "span.availability",
    "category": "a.breadcrumb:last-child",
    "reviews_count": "span.review-count",
    "brand": "div.brand-name",
    "sku": "span.product-sku"
  }
}
```

**Storage:**
- `title`, `author`, `content`, `date` -> Standard database columns (always available)
- Everything else -> `metadata` JSON column (flexible, any structure)

### When to Use Custom Selectors

**Test generic extractors first during analysis:**
1. Inspect an article page and check if newspaper/trafilatura extract correctly
2. If they work → use generic extractors (no custom selectors needed)
3. If they fail → discover and configure custom selectors

**Use custom selectors when:**
- Generic extractors miss content, pick up navigation/sidebars, or extract wrong fields
- You need to extract non-standard fields (price, rating, views, etc.)
- Content requires precise targeting (forums, products, complex layouts)

### Selector Discovery Principles

1. **Look for the MAIN content element** - not navigation, sidebars, or related articles
2. **Verify uniqueness** - selector should match ONE element per page
3. **Use specific classes** - prefer `.article-title` over generic `.title`
4. **Test on multiple articles** - ensure selector works across different pages
5. **Prefer semantic tags** - `<article>`, `<time>`, `<h1>` when available
6. **Check text length** - content should be substantial (>100 chars for title, >500 for content)
7. **Avoid dynamic classes** - skip classes with random strings or IDs

**Common Mistakes:**
- Using selector that matches multiple elements (gets first one, often wrong)
- Using selector from navigation/sidebar/footer (not main content)
- Using overly generic selectors like `div.text` or `span.content`
- Not testing the selector - verify it finds the right element!
- Guessing selectors without analyzing actual HTML

---

## Generic Extractors (Newspaper & Trafilatura)

**Generic extractors are available and should be tested first during analysis.**

**Advantages:**
- Fast setup - no selector discovery needed
- Work well for standard news/blog articles
- Good for sites with clean, semantic HTML

**Limitations:**
- May pick up navigation, sidebars, or related articles
- Limited to article-like content (title, author, content, date)
- Use heuristics that may fail on complex layouts

**Recommendation:** Test generic extractors first. If they extract correctly, use them. If not, configure custom selectors for precise targeting.

---

## Choosing Extractor Order

**Configure `EXTRACTOR_ORDER` based on site characteristics and whether you need custom selectors.**

**With Custom Selectors (Recommended):** `["custom", "newspaper", "trafilatura"]`
- Custom selectors first for precise targeting
- Falls back to generic extractors if custom extraction fails
- Best for sites where generic extractors are unreliable

**Generic Only (No Custom Selectors):** `["newspaper", "trafilatura", "playwright"]`
- Use when generic extractors work correctly during analysis
- Fast extractors first, browser rendering as last resort
- Good for clean news sites, blogs with standard HTML

**JS-Rendered Sites:** `["playwright", "custom"]` or `["playwright", "trafilatura"]`
- **Use when content is loaded via JavaScript**
- Playwright first to get rendered HTML, then extract
- Static extractors won't work on empty HTML
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

---

## Playwright Wait Configuration

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

---

## Infinite Scroll Support

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
