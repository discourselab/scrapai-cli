# Amazon.co.uk - Mac Accessories Product Scraper

**Source URL:** https://www.amazon.co.uk/s?k=mac+accessories
**Project:** tmp
**Date:** 2026-02-26
**Task:** Extract 20 product pages with detailed names and delivery dates

---

## Executive Summary

Amazon UK product scraper focused on Mac accessories. The spider will:
1. Start from 2 pages of search results (page 1 & 2)
2. Extract product URLs from search results
3. Visit each product detail page
4. Extract product name, delivery dates, price, and availability
5. Target: 20 products minimum

**Key Findings:**
- No special protection (regular HTTP works)
- Clean HTML structure with ID-based selectors
- Product URLs follow pattern: `/dp/<ASIN>` where ASIN is 10-character alphanumeric
- Delivery dates visible in `#deliveryBlockMessage` div
- Must respect ROBOTSTXT and use polite crawling (DOWNLOAD_DELAY=2)

---

## Content Structure

### Search Results Pages
**URL Pattern:** `/s?k=mac+accessories&page=N`
**Pages to crawl:** 1 and 2

**Product Links in Search Results:**
- Format: `/dp/<ASIN>/ref=...` or clean `/dp/<ASIN>`
- ASIN: 10-character alphanumeric identifier (e.g., B077T4FBSP)
- Appears in: `<a>` tags with class `a-link-normal`

**Example ASINs found:**
- B077T4FBSP - USB C Hub HDMI Adapter
- B0BQLLB61B - Anker Display adapter
- B0DKT8BB4M - Anker Multiport Adapter
- B096KHQWMF - Laptop stand
- B07X1VZRT1 - USB C Dongle Adapter
- B0B7QWBZC9 - MacBook case
- B079MCPJGH - (from page 2)
- B07PPPY1LV - (from page 2)

### Product Detail Pages
**URL Pattern:** `/dp/<ASIN>`
**Example:** https://www.amazon.co.uk/dp/B077T4FBSP

**Fields to Extract:**

1. **Product Name/Title**
   - Selector: `span#productTitle::text` or `h1.a-size-large.a-spacing-none::text`
   - Example: "USB C Hub HDMI Adapter for MacBook Pro/Air, MOKiN 7 IN 1 USB C Dongle Mac Adapter with HDMI, Type C Data Port,100W PD,SD/TF and 2 USB3.0 for Dell/Lenovo/Thinkpad"
   - Note: Full detailed name includes all specifications

2. **Delivery Date (Primary)**
   - Container: `div#deliveryBlockMessage`
   - Primary delivery: First date mentioned
   - Example: "FREE delivery Monday, 2 March on your first order to UK or Ireland"
   - Selector: `div#deliveryBlockMessage span::text` (needs extraction from text)

3. **Delivery Date (Fastest)**
   - Container: `div#mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE`
   - Example: "Or fastest delivery Saturday, 28 February"
   - Alternative selector: `span[data-csa-c-delivery-time]::text`

4. **Price**
   - Selector: `span.a-price span.a-offscreen::text`
   - Example: "£16.99"
   - Note: Hidden offscreen span contains clean price text

5. **Availability**
   - Selector: `div#availability span::text`
   - Example: "In Stock" or "Usually dispatched within..."

6. **ASIN** (for reference)
   - Selector: `input#ASIN::attr(value)`
   - Useful for tracking and deduplication

---

## HTML Structure Analysis

### Product Page Confirmed Selectors

**Product Title:**
```html
<span id="productTitle" class="a-size-large product-title-word-break">
    USB C Hub HDMI Adapter for MacBook Pro/Air...
</span>
```
OR
```html
<h1 class="a-size-large a-spacing-none">
    USB C Hub HDMI Adapter for MacBook Pro/Air...
</h1>
```

**Delivery Information:**
```html
<div id="deliveryBlockMessage" class="a-section">
    <span>FREE delivery</span>
    <span class="a-text-bold">Monday, 2 March</span>
    <span>on your first order to UK or Ireland.</span>
</div>
```

**Price:**
```html
<span class="a-price aok-align-center reinventPricePriceToPayMargin priceToPay">
    <span class="a-offscreen">£16.99</span>
</span>
```

**Availability:**
```html
<div id="availability" class="a-section a-spacing-base">
    <span class="a-size-medium a-color-success">In Stock</span>
</div>
```

---

## Extraction Strategy

**Spider Type:** Custom callback spider (NOT article extraction)
**Callback:** `parse_product`
**Extractor Order:** Empty (using custom field extraction only)

**Custom Fields Configuration:**

```json
{
  "product_name": {
    "css": "span#productTitle::text",
    "processors": [{"type": "strip"}]
  },
  "delivery_primary": {
    "css": "div#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE span::text",
    "get_all": true,
    "processors": [{"type": "join", "separator": " "}]
  },
  "delivery_fastest": {
    "css": "div#mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE span::text",
    "get_all": true,
    "processors": [{"type": "join", "separator": " "}]
  },
  "delivery_full": {
    "css": "div#deliveryBlockMessage span::text",
    "get_all": true,
    "processors": [{"type": "join", "separator": " "}]
  },
  "price": {
    "css": "span.a-price span.a-offscreen::text"
  },
  "availability": {
    "css": "div#availability span::text",
    "processors": [{"type": "strip"}]
  },
  "asin": {
    "css": "input#ASIN::attr(value)"
  }
}
```

---

## URL Matching Rules

**Rule 1: Product Pages**
```json
{
  "allow": ["/dp/[A-Z0-9]{10}"],
  "deny": [
    "/gp/",
    "/ap/",
    "/customer-reviews/",
    "/product-reviews/",
    "/ask/questions/",
    "/review/",
    "/offer-listing/",
    "/twister/"
  ],
  "callback": "parse_product",
  "follow": false
}
```

**Deny Patterns Explanation:**
- `/gp/` - Generic pages (help, cart, etc.)
- `/ap/` - Account pages
- `/customer-reviews/` - Review pages (duplicates)
- `/product-reviews/` - Review pages (duplicates)
- `/ask/questions/` - Q&A pages
- `/review/` - Individual reviews
- `/offer-listing/` - Seller listings
- `/twister/` - Variation selection pages

**Follow: false** - We don't want to follow links from product pages, only extract from them

---

## Spider Settings

```json
{
  "EXTRACTOR_ORDER": [],
  "DOWNLOAD_DELAY": 2,
  "CONCURRENT_REQUESTS": 4,
  "ROBOTSTXT_OBEY": true,
  "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
```

**Settings Explanation:**
- `EXTRACTOR_ORDER: []` - No generic extractors, using custom fields only
- `DOWNLOAD_DELAY: 2` - Be polite to Amazon servers (2 seconds between requests)
- `CONCURRENT_REQUESTS: 4` - Low concurrency to avoid rate limiting
- `ROBOTSTXT_OBEY: true` - Respect robots.txt (required for ethical scraping)
- `USER_AGENT` - Standard browser UA (avoid being flagged as bot)

---

## Estimated Volume

**Search Results:**
- Page 1: ~48 products
- Page 2: ~48 products
- **Total available:** ~96 products

**Target:** 20 products (using `--limit 20`)

---

## Start URLs

```json
[
  "https://www.amazon.co.uk/s?k=mac+accessories&page=1",
  "https://www.amazon.co.uk/s?k=mac+accessories&page=2"
]
```

**Note:** Starting from search result pages, not homepage. The spider will:
1. Load page 1 of search results
2. Load page 2 of search results
3. Extract all `/dp/<ASIN>` product URLs from both pages
4. Visit each product page and extract detailed information
5. Stop after 20 products (if using --limit 20)

---

## Exclusions

**Pages to NOT crawl:**
- Homepage (`/`)
- Category pages (`/s?i=...`)
- Cart pages (`/gp/cart/`)
- Account pages (`/ap/signin`, `/gp/your-account/`)
- Review pages (handled via deny rules)
- Seller pages (`/sp?seller=...`)
- Help pages (`/gp/help/`)
- Subscribe & Save variations
- Amazon Prime pages

---

## Technical Considerations

### Rate Limiting
- Amazon may rate limit aggressive crawling
- Use `DOWNLOAD_DELAY: 2` minimum
- If blocked, increase to 3-5 seconds
- Consider rotating User-Agent if needed

### Session/Cookies
- Amazon may require cookies for full functionality
- Scrapy's default cookie handling should work
- Location detection: may show "Delivering to Exeter EX2" or other default location
- This doesn't affect product information extraction

### Dynamic Content
- Amazon uses some JavaScript but core product information is in HTML
- No need for Playwright/browser mode for basic product data
- Delivery dates are server-rendered in HTML

### CAPTCHA Risk
- Low risk for 20 products with polite settings
- If CAPTCHA appears, increase DOWNLOAD_DELAY
- For production scale (100+ products), consider:
  - Residential proxies
  - Session rotation
  - Longer delays

---

## Test Plan (Phase 4)

1. **Import test spider** with 5 sample ASINs
2. **Run crawl** with `--limit 5`
3. **Verify extraction:**
   - Product names are complete and detailed
   - Delivery dates are extracted (both primary and fastest)
   - Prices are present
   - Availability status is captured
   - No empty/null fields
4. **Check output format** with `./scrapai show`
5. **Import final spider** with search result start URLs

---

## Sample Expected Output

```json
{
  "url": "https://www.amazon.co.uk/dp/B077T4FBSP",
  "metadata_json": {
    "product_name": "USB C Hub HDMI Adapter for MacBook Pro/Air, MOKiN 7 IN 1 USB C Dongle Mac Adapter with HDMI, Type C Data Port,100W PD,SD/TF and 2 USB3.0 for Dell/Lenovo/Thinkpad",
    "delivery_primary": "FREE delivery Monday, 2 March on your first order to UK or Ireland. Details",
    "delivery_fastest": "Or fastest delivery Saturday, 28 February. Details",
    "delivery_full": "FREE delivery Monday, 2 March on your first order to UK or Ireland. Details Or fastest delivery Saturday, 28 February. Details",
    "price": "£16.99",
    "availability": "In Stock",
    "asin": "B077T4FBSP"
  },
  "scraped_at": "2026-02-26T23:30:00"
}
```

---

## Next Steps

**Phase 2:** ✅ Complete (URL rules and custom fields defined above)

**Phase 3:** Create spider configurations
- `test_spider.json` - 5 sample ASINs for testing
- `final_spider.json` - Full configuration with search result start URLs

**Phase 4:** Skip testing per user request (configs created but not executed)

---

**Analysis completed:** 2026-02-26
**Analyst:** ScrapAI
**Status:** ✅ Phase 1-2 Complete - Ready for Phase 3
