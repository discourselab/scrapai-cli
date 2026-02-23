# Cloudflare Bypass

Only enable when the site requires it. Test WITHOUT `--cloudflare` first.

## Detection Indicators

- "Checking your browser" or "Just a moment" messages
- 403/503 HTTP errors with Cloudflare branding
- Challenge pages before content loads

## Display Requirements

**Cloudflare bypass requires a visible browser** (not headless) - Cloudflare detects headless browsers and blocks them.

- **macOS/Windows:** Uses native display automatically
- **Linux desktop:** Uses native display automatically
- **Linux servers (VPS without GUI):** Auto-detects missing display and uses **Xvfb** (virtual display)

**Installing Xvfb on Linux servers:**
```bash
# Debian/Ubuntu
sudo apt-get install xvfb

# RHEL/CentOS
sudo yum install xorg-x11-server-Xvfb
```

The crawler automatically detects your environment and uses Xvfb when no display is available on Linux - no additional configuration needed.

## Inspector

```bash
# Lightweight HTTP (default) - fast, works for most sites
./scrapai inspect https://example.com --project proj

# Browser mode - for JS-rendered sites
./scrapai inspect https://example.com --project proj --browser

# Cloudflare bypass - for protected sites
./scrapai inspect https://example.com --project proj --cloudflare
```

**Smart resource usage:** Start with default HTTP (fast). Escalate to `--browser` if content is JS-rendered. Use `--cloudflare` only when site shows "Checking your browser" or 403/503 errors.

## Hybrid Mode (Default)

Browser verification once per 10 min, then fast HTTP with cached cookies. **20-100x faster** than browser-only. Do NOT set `CONCURRENT_REQUESTS` (uses Scrapy default of 16).

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

## Browser-Only Mode (Legacy)

Only if hybrid fails. Browser for every request. **Requires `CONCURRENT_REQUESTS: 1`.**

```json
{
  "CLOUDFLARE_ENABLED": true,
  "CLOUDFLARE_STRATEGY": "browser_only",
  "CONCURRENT_REQUESTS": 1
}
```

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `CLOUDFLARE_ENABLED` | false | Enable CF bypass |
| `CLOUDFLARE_STRATEGY` | "hybrid" | "hybrid" or "browser_only" |
| `CLOUDFLARE_COOKIE_REFRESH_THRESHOLD` | 600 | Seconds before cookie refresh |
| `CF_MAX_RETRIES` | 5 | Max verification attempts |
| `CF_RETRY_INTERVAL` | 1 | Seconds between retries |
| `CF_POST_DELAY` | 5 | Seconds after successful verification |
| `CF_WAIT_SELECTOR` | — | CSS selector to wait for before extracting |
| `CF_WAIT_TIMEOUT` | 10 | Max seconds to wait for selector |
| `CF_PAGE_TIMEOUT` | 120000 | Page navigation timeout (ms) |
| `CONCURRENT_REQUESTS` | — | Must be 1 for browser-only mode |

## Full Spider Example (Hybrid)

```json
{
  "name": "americafirstpolicy",
  "allowed_domains": ["americafirstpolicy.com"],
  "start_urls": ["https://www.americafirstpolicy.com/issues/energy"],
  "rules": [
    { "allow": ["/issues/[^/]+$"], "callback": "parse_article", "follow": false, "priority": 100 },
    { "allow": ["/issues/"], "callback": null, "follow": true, "priority": 50 }
  ],
  "settings": {
    "CLOUDFLARE_ENABLED": true,
    "CLOUDFLARE_STRATEGY": "hybrid",
    "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600,
    "CF_MAX_RETRIES": 5,
    "CF_RETRY_INTERVAL": 1,
    "CF_POST_DELAY": 5,
    "CF_WAIT_SELECTOR": "h1.title-med-1",
    "DOWNLOAD_DELAY": 2
  }
}
```

## Troubleshooting

**Diagnosing via logs (hybrid mode):**
- Success: `Cached N cookies (cf_clearance: ...)` → cookies working
- Warning: `Blocked despite cookies - re-verifying CF` → cookies expired/blocked, will auto-retry
- Error: `Still blocked - falling back to browser` → hybrid failing, may need browser-only
- If cookies fail repeatedly, system auto-falls back to browser-only mode

**Diagnosing via logs (browser-only):**
- `Cloudflare verified successfully` → bypass working
- `Opened persistent browser` / `Closed browser` → normal lifecycle

**Title contamination:** If extracted titles show wrong text (e.g., "Related Articles" instead of actual title), set `CF_WAIT_SELECTOR` to the main title element (e.g., `h1.article-title`). This captures HTML before related content loads.

**Wait times:** Initial page load 2s → after selector found +2s → no selector 5s total → small HTML detected +5s → post-CF verification: `CF_POST_DELAY` + 3s.
