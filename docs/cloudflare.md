# Cloudflare Bypass Support

**For sites protected by Cloudflare challenges**, the system supports automatic bypass using a persistent browser session.

## When to Use

- Site shows "Checking your browser" or "Just a moment" messages
- Site returns 403/503 errors with Cloudflare branding
- Content extraction fails with normal extractors
- Inspector fails to fetch the homepage

## Inspector with Cloudflare Bypass

```bash
# Regular inspection (Playwright)
source .venv/bin/activate && bin/inspector --url https://example.com
```
```bash
# CF-protected site (nodriver with bypass)
source .venv/bin/activate && bin/inspector --url https://americafirstpolicy.com/issues/energy --cloudflare
```

## Spider Configuration with Cloudflare

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
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5,
    "CF_WAIT_SELECTOR": "h1.title-med-1",
    "CF_WAIT_TIMEOUT": 30,
    "CF_PAGE_TIMEOUT": 120000,
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 1
  }
}
```

## Available Settings

- `CLOUDFLARE_ENABLED`: Enable CF bypass mode (true/false, default: false)
- `CF_MAX_RETRIES`: Maximum CF verification attempts (default: 5)
- `CF_RETRY_INTERVAL`: Seconds between retry attempts (default: 1)
- `CF_POST_DELAY`: Seconds to wait after successful CF verification (default: 5)
- `CF_WAIT_SELECTOR`: CSS selector to wait for before extracting (e.g., "h1.title-med-1")
- `CF_WAIT_TIMEOUT`: Max seconds to wait for selector (default: 10)
- `CF_PAGE_TIMEOUT`: Page navigation timeout in milliseconds (default: 120000 = 2 minutes)

## How It Works

1. Spider opens: Starts persistent nodriver browser (visible, not headless)
2. First request: Navigates to URL and solves Cloudflare challenge
3. Post-CF wait: Waits for full page render (CF_POST_DELAY + 3s additional)
4. Subsequent requests: Reuses verified session (no additional CF challenges)
5. Page stabilization: Waits 2s for JavaScript to start executing
6. Content loading: If CF_WAIT_SELECTOR set, waits for that element + 2s additional
7. HTML verification: Checks content size, waits longer if skeleton HTML detected
8. Content extraction: Returns fully-rendered HTML to extractors
9. Spider closes: Closes browser and cleans up resources

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

- CF verification takes 5-50 seconds on first request
- Subsequent requests are fast (~1-2 seconds per page)
- Requires visible browser (headless mode may fail CF verification)
- Set `CONCURRENT_REQUESTS: 1` (required for single browser session)
- Not compatible with parallel crawling

## Logging

Look for these log messages during crawl:
```
[INFO] CloudflareDownloadHandler: Opened persistent browser
[INFO] Started nodriver browser for Cloudflare bypass
[INFO] Navigating to https://... for Cloudflare verification
[INFO] Cloudflare verified successfully for https://...
[INFO] Fetching https://... using verified Cloudflare session
[INFO] CloudflareDownloadHandler: Closed browser
```

## Important Notes

- Only use when site is actually Cloudflare-protected (adds overhead)
- Browser must be visible - set `headless=False` (CF may detect headless mode)
- Single browser session = single concurrent request only
- SmartExtractor still handles content extraction from fetched HTML
- No changes to `EXTRACTOR_ORDER` needed - works with all extractors
