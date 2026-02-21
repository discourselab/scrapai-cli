# Cloudflare Bypass Support

Technical documentation for Cloudflare bypass functionality with hybrid mode (fast) and browser-only mode (legacy).

## Overview

ScrapAI offers two strategies for bypassing Cloudflare protection:

1. **Hybrid Mode (Default, Fast)**: Browser verification once every 10 minutes, then fast HTTP requests with cached cookies. **20-100x faster** than browser-only.
2. **Browser-Only Mode (Legacy, Slow)**: Browser for every request. Most reliable, but slow.

**Recommendation**: Use hybrid mode (default) for production. Only use browser-only if hybrid mode fails.

## Strategy Comparison

### Hybrid Mode (Default)

**How it works:**
1. Browser verification once per 10 minutes (configurable) to get Cloudflare cookies
2. Fast HTTP requests with cached cookies for subsequent requests
3. Automatic fallback to browser if cookies become invalid
4. Proactive cookie refresh before expiry

**Performance:**
- First request: 5-50 seconds (browser verification)
- Subsequent requests: 1-2 seconds (fast HTTP)
- **20-100x faster** than browser-only mode
- Cookie cache shared per spider (survives across crawls within 10 min window)

**Settings:**
```json
{
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid",
    "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600
  }
}
```

**Note**: Do NOT set `CONCURRENT_REQUESTS` - uses Scrapy default (16) for parallel crawling.

**When to use:**
- Production crawls (default)
- Large-scale scraping (hundreds/thousands of pages)
- When speed matters

### Browser-Only Mode (Legacy)

**How it works:**
1. Browser for every single request
2. Cloudflare verification on every page

**Performance:**
- Every request: 5-50 seconds (slow)
- Not suitable for large-scale crawls

**Settings:**
```json
{
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "browser_only",
    "CONCURRENT_REQUESTS": 1
  }
}
```

**Note**: `CONCURRENT_REQUESTS: 1` is REQUIRED - single browser session only.

**When to use:**
- Hybrid mode fails (cookies get blocked repeatedly)
- Very small crawls (<10 pages)
- Testing/debugging

## Detection Indicators

Sites with Cloudflare protection typically show:
- "Checking your browser" or "Just a moment" messages
- 403/503 HTTP errors with Cloudflare branding
- Challenge pages before accessing content

## Inspector with Cloudflare Bypass

```bash
# Regular inspection (Playwright)
./scrapai inspect --url https://example.com
```
```bash
# CF-protected site (nodriver with bypass)
./scrapai inspect --url https://americafirstpolicy.com/issues/energy --cloudflare
```

## Spider Configuration with Cloudflare

### Hybrid Mode (Default, Recommended)

```json
{
  "name": "americafirstpolicy",
  "allowed_domains": ["americafirstpolicy.com"],
  "start_urls": ["https://www.americafirstpolicy.com/issues/energy"],
  "rules": [
    {
      "allow": ["/issues/[^/]+$"],
      "deny": ["/issues/ajax-feed", "/issues/energy-environment"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/issues/"],
      "deny": ["/issues/ajax-feed"],
      "callback": null,
      "follow": true,
      "priority": 50
    }
  ],
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid",
    "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600,
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5,
    "CF_WAIT_SELECTOR": "h1.title-med-1",
    "CF_WAIT_TIMEOUT": 30,
    "DOWNLOAD_DELAY": 2
  }
}
```

**Note**: Do NOT set `CONCURRENT_REQUESTS` for hybrid mode - uses Scrapy default (16 concurrent requests). HTTP requests with cached cookies work in parallel.

### Browser-Only Mode (Legacy, Slow)

```json
{
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "browser_only",
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5,
    "CONCURRENT_REQUESTS": 1
  }
}
```

**Note**: `CONCURRENT_REQUESTS: 1` is REQUIRED for browser-only mode (single browser session can only handle one request at a time).

## Available Settings

### Strategy Settings

- `CLOUDFLARE_ENABLED`: Enable CF bypass mode (true/false, default: false)
- `CLOUDFLARE_STRATEGY`: Strategy to use - 'hybrid' or 'browser_only' (default: 'hybrid')
- `CLOUDFLARE_COOKIE_REFRESH_THRESHOLD`: Seconds before proactive cookie refresh (default: 600 = 10 minutes)

### Browser Settings

- `CF_MAX_RETRIES`: Maximum CF verification attempts (default: 5)
- `CF_RETRY_INTERVAL`: Seconds between retry attempts (default: 1)
- `CF_POST_DELAY`: Seconds to wait after successful CF verification (default: 5)
- `CF_WAIT_SELECTOR`: CSS selector to wait for before extracting (e.g., "h1.title-med-1")
- `CF_WAIT_TIMEOUT`: Max seconds to wait for selector (default: 10)
- `CF_PAGE_TIMEOUT`: Page navigation timeout in milliseconds (default: 120000 = 2 minutes)

## How It Works

### Hybrid Mode (Default)

1. **First request**: Browser opens, navigates to URL, solves Cloudflare challenge
2. **Cookie extraction**: After verification, extracts CF cookies (cf_clearance) and user-agent
3. **Cookie caching**: Stores cookies with timestamp (valid for ~25 minutes)
4. **Subsequent requests**: Fast HTTP requests using cached cookies (no browser needed)
5. **Proactive refresh**: Before 10 min threshold, refreshes cookies via browser
6. **Automatic fallback**: If HTTP request gets blocked, re-verifies and retries
7. **Spider closes**: Closes browser and clears cookie cache

**Performance**: First page ~10-20 seconds, subsequent pages ~1-2 seconds each.

### Browser-Only Mode (Legacy)

1. Spider opens: Starts persistent nodriver browser (visible, not headless)
2. First request: Navigates to URL and solves Cloudflare challenge
3. Post-CF wait: Waits for full page render (CF_POST_DELAY + 3s additional)
4. Subsequent requests: Reuses verified browser session (no additional CF challenges)
5. Page stabilization: Waits 2s for JavaScript to start executing
6. Content loading: If CF_WAIT_SELECTOR set, waits for that element + 2s additional
7. HTML verification: Checks content size, waits longer if skeleton HTML detected
8. Content extraction: Returns fully-rendered HTML to extractors
9. Spider closes: Closes browser and cleans up resources

**Performance**: Every page ~5-10 seconds (browser overhead on each request).

## Wait Times (configurable)

- Initial page load: 2 seconds
- After selector found: 2 seconds additional
- No selector: 5 seconds total wait
- Small HTML detected: 5 seconds additional
- Post-CF verification: CF_POST_DELAY + 3 seconds

## Preventing Title Contamination

The persistent browser session can cause title mismatches if "Related Articles" sections load before HTML extraction. To prevent this:

1. **Use `CF_WAIT_SELECTOR`** to wait for the main article title specifically
2. **Extract HTML immediately** after main content loads (before related articles)
3. **Example:** For a site with `<h1 class="article-title">`, set `CF_WAIT_SELECTOR: "h1.article-title"`

This ensures the extractor gets clean HTML with the correct title for each page.

## Session Persistence Benefits

- Cloudflare challenge solved once, not on every page
- Significantly faster crawling after initial verification
- Reliable access to all pages using same verified session

## Performance Notes

### Hybrid Mode (Default)

- **First request**: 5-50 seconds (browser verification + cookie extraction)
- **Subsequent requests**: 1-2 seconds (fast HTTP with cookies)
- **Cookie lifetime**: ~25 minutes (proactive refresh at 10 min threshold)
- **Parallel crawling**: SUPPORTED (uses Scrapy default: 16 concurrent requests)
- **Speed improvement**: 20-100x faster than browser-only mode
- **Resource usage**: Low (browser only used every 10 minutes)

### Browser-Only Mode (Legacy)

- **Every request**: 5-10 seconds (browser overhead on each page)
- **Parallel crawling**: NOT SUPPORTED (single browser session)
- **Required setting**: `CONCURRENT_REQUESTS: 1`
- **Resource usage**: High (browser memory/CPU on every request)
- **When to use**: Hybrid mode fails or very small crawls (<10 pages)

## Logging

### Hybrid Mode Logs

```
[INFO] CloudflareDownloadHandler: Handler opened (browser will start on first request)
[INFO] [spider_name] Getting/refreshing CF cookies via browser
[INFO] Starting shared browser for CF verification
[INFO] Browser started successfully
[INFO] [spider_name] Cached 15 cookies (cf_clearance: 0vZc...)
[INFO] [spider_name] Cookies aging (9.5 min) - refreshing proactively
[INFO] CloudflareDownloadHandler: Closing shared browser...
[INFO] CloudflareDownloadHandler: Browser stopped successfully
```

**If cookies get blocked:**
```
[WARNING] [spider_name] Blocked despite cookies - re-verifying CF
[ERROR] [spider_name] Still blocked - falling back to browser
```

### Browser-Only Mode Logs

```
[INFO] CloudflareDownloadHandler: Opened persistent browser
[INFO] Started nodriver browser for Cloudflare bypass
[INFO] Navigating to https://... for Cloudflare verification
[INFO] Cloudflare verified successfully for https://...
[INFO] Fetching https://... using verified Cloudflare session
[INFO] CloudflareDownloadHandler: Closed browser
```

## Technical Limitations

### Hybrid Mode

- Browser must be visible during cookie refresh (Cloudflare may detect headless browsers)
- Cookie refresh every 10 minutes (configurable via `CLOUDFLARE_COOKIE_REFRESH_THRESHOLD`)
- First request slower (~10-20s), subsequent requests fast (~1-2s)
- If cookies fail repeatedly, falls back to browser-only mode
- Requires `aiohttp` dependency (installed automatically)

### Browser-Only Mode

- Browser must be visible - `headless=False` required (Cloudflare may detect headless browsers)
- Single browser session = single concurrent request only (`CONCURRENT_REQUESTS: 1` required)
- Higher resource usage: browser memory and CPU overhead on every request
- Slower than HTTP requests: adds 5-10 second overhead per page
- Not suitable for large-scale crawls

### Both Modes

- SmartExtractor handles content extraction from fetched HTML
- Compatible with all `EXTRACTOR_ORDER` configurations
- Works with custom selectors and Playwright extractors
