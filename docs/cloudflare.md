# Browser Mode (JS Rendering + Cloudflare Bypass)

Use `--browser` for JavaScript-rendered sites and Cloudflare-protected sites. scrapai uses **CloakBrowser** - a stealth Chromium with C++ patches that achieves **0.9 reCAPTCHA scores** and passes advanced bot detection.

## Quick Start

```bash
# Inspector - analyze a site
./scrapai inspect https://example.com --project proj --browser

# Crawl - test with 5 pages
./scrapai crawl spider_name --project proj --limit 5 --browser
```

**When to use:**
- Site content is JavaScript-rendered (blank with HTTP)
- Site shows "Checking your browser" or Cloudflare challenge
- Getting 403/503 errors with regular HTTP

**Otherwise:** Use default HTTP mode (faster, no browser overhead).

---

## Try Lighter Transports First

The browser is the heaviest, slowest transport — reach for it last. `inspect`
auto-escalates through a transport ladder (HTTP → curl_cffi → browser) and
reports the **lightest** transport that worked, plus the spider setting to match
it. Before enabling the browser, try **curl_cffi** (TLS fingerprint
impersonation, no JS):

```json
{
  "CURL_CFFI_ENABLED": true
}
```

curl_cffi defeats TLS-fingerprint blocks (the common cause of 403s) without
launching a browser, so it's far faster. Only enable browser mode
(`CLOUDFLARE_ENABLED` / `BROWSER_ENABLED`) when curl_cffi is still blocked or the
content genuinely needs JavaScript rendering. `CURL_CFFI_ENABLED` and the browser
settings are mutually exclusive — curl_cffi takes precedence when both are set.

---

## Browser Mode: Two Names, One Behavior

Two settings enable browser mode, and the code treats them identically (both
start CloakBrowser):

| Setting | Use when |
|---------|----------|
| `CLOUDFLARE_ENABLED` | Site is behind a Cloudflare (or similar) challenge |
| `BROWSER_ENABLED` | Site is plain JavaScript-rendered (no challenge, just needs JS) |

Pick the one that documents your intent. The `--browser` CLI flag enables the
same path. Setting both is harmless — they are aliases.

---

## How It Works

**Hybrid mode (automatic):**
1. **Browser opens once** → solves Cloudflare challenge → extracts cookies
2. **HTTP requests with cookies** → 20-100x faster than keeping browser open
3. **Auto-refresh cookies** every 10 minutes (configurable)

**Performance:** 8min for 1000 pages vs 2+ hours with browser-only mode.

**Headed by default** for maximum stealth. On headless servers, Xvfb is auto-handled by the CLI (never use `xvfb-run` manually).

---

## Platform Support

✅ **Linux x64** (production servers)
✅ **macOS** (Apple Silicon & Intel)
✅ **Windows** via WSL or Docker

**Native Windows (cmd/PowerShell):** Use [WSL](https://docs.microsoft.com/en-us/windows/wsl/install) (5-minute setup).

---

## Why CloakBrowser?

**Source-level C++ patches (not runtime JavaScript injection):**
- **0.9 reCAPTCHA v3 score** (human-level)
- **Passes 30/30 bot detection tests** (FingerprintJS, BrowserScan, Cloudflare Turnstile, DataDome)
- **Headed mode by default** (best stealth, Xvfb auto-handled on servers)
- **Survives Chrome updates** (patches compiled into binary)

Other tools use JavaScript injection or config tweaks that break on updates and get detected.

---

## Backward Compatibility

**Existing spiders with Cloudflare settings still work:**

```json
{
  "CLOUDFLARE_ENABLED": true
}
```

No changes needed. The `--browser` flag is just a simpler way to enable it from CLI.

---

## Advanced Configuration

### Custom Settings (Optional)

Fine-tune browser behavior in spider settings:

```json
{
  "CLOUDFLARE_ENABLED": true,
  "CLOUDFLARE_STRATEGY": "hybrid",           // "hybrid" (default) or "browser_only"
  "CLOUDFLARE_HEADLESS": false,              // false (default, best stealth) or true (no GUI)
  "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600 // seconds (10 min default)
}
```

### Browser-Only Mode

Only use if hybrid mode fails. **Slow** - keeps browser open for every request.

```json
{
  "CLOUDFLARE_STRATEGY": "browser_only",
  "CONCURRENT_REQUESTS": 1  // Required for browser-only
}
```

### All Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `CLOUDFLARE_ENABLED` | false | Enable browser mode (Cloudflare intent) |
| `BROWSER_ENABLED` | false | Enable browser mode (plain JS-render intent); alias of `CLOUDFLARE_ENABLED` |
| `CURL_CFFI_ENABLED` | false | Use curl_cffi TLS impersonation instead of the browser (try first; takes precedence over browser settings) |
| `CLOUDFLARE_STRATEGY` | "hybrid" | "hybrid" (fast) or "browser_only" (slow) |
| `CLOUDFLARE_HEADLESS` | false | Headless mode (true = no GUI, worse stealth) |
| `CLOUDFLARE_COOKIE_REFRESH_THRESHOLD` | 600 | Seconds before cookie refresh |
| `CF_MAX_RETRIES` | 5 | Max verification attempts |
| `CF_RETRY_INTERVAL` | 1 | Seconds between retries |
| `CF_POST_DELAY` | 5 | Seconds after successful verification |
| `CF_WAIT_SELECTOR` | — | CSS selector to wait for |
| `CF_WAIT_TIMEOUT` | 10 | Selector wait timeout (seconds) |
| `CONCURRENT_REQUESTS` | 16 | Must be 1 for browser-only mode |

---

## Troubleshooting

### Crawl Hangs

**Symptoms:** Browser opens but never navigates.

**Solutions:**
1. Check browser actually opens (test with `--browser` flag on inspector first)
2. On headless servers, verify Xvfb is installed (`sudo apt-get install xvfb`) — CLI auto-wraps with `xvfb-run`
3. Check system resources (CPU, memory)
4. Test with different `CLOUDFLARE_STRATEGY` (try browser_only)

### Wrong Content Extracted

**Symptom:** Titles show "Related Articles" instead of actual title.

**Solution:** Set `CF_WAIT_SELECTOR` to the main title element:

```json
{
  "CF_WAIT_SELECTOR": "h1.article-title"
}
```

This captures HTML before related content loads.

### Blocked Despite Cookies

**Symptom:** Logs show "Blocked despite cookies - re-verifying CF"

**What happens:** System auto-retries with fresh cookies, then falls back to browser if still blocked.

**If repeated:** Consider:
1. IP reputation issue (try residential proxy: `--proxy-type residential`)
2. Switch to browser-only mode
3. Site may have additional detection beyond Cloudflare

---

## Performance Tips

1. **Start with hybrid mode** (default) - 20-100x faster
2. **Only use browser-only if hybrid fails** - fallback for tough sites
3. **Use --limit for testing** - verify extraction works before full crawl
4. **Monitor logs** - "Cached N cookies" = hybrid working

---

## Faster Inspects: Persistent Browser Service

When a session does **many browser inspects** — repeated `inspect --screenshot`
across a site, or several parallel agents each inspecting a different
Cloudflare/JS site — start the persistent browser service first. It keeps one
warm browser running so the Cloudflare challenge is solved **once** per site and
reused across `inspect` calls (and across parallel agents), instead of
cold-starting a fresh browser (~10-15s) every time:

```bash
./scrapai browser start
```

`inspect` routes through it automatically when it's running; `./scrapai browser
stop` when done. See [browser-service.md](browser-service.md) for details.
