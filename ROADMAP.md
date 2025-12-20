# ScrapAI Roadmap

**Core Vision:** Enable AI to automatically scrape any website without humans writing custom code.

---

## 🎯 Critical Features (Must Have)

### 1. Custom Selector-Based Parsing ⭐⭐⭐
**Why:** Currently only works for articles. Can't scrape quotes, products, tables, or any structured data.

**What:**
- Define CSS selectors in JSON config (no Python code)
- Extract multiple items per page (collections)
- Support for tables with auto-headers
- AI analyzes page → AI writes selectors → stored in DB

**Example:**
```json
{
  "extraction": {
    "type": "structured",
    "item_selector": ".quote",
    "fields": {
      "title": ".text::text",
      "author": ".author::text",
      "tags": ".tag::text"
    }
  }
}
```

**Status:** 🔴 Not started
**Priority:** **Do this first** - blocks most non-article sites

---

### 2. Proxy Support ⭐⭐⭐
**Why:** Get rate limited/banned without proxies. Can't scale.

**What:**
- Proxy pool configuration
- Automatic rotation
- Support HTTP/HTTPS/SOCKS5
- Per-spider proxy settings

**Example:**
```json
{
  "proxy": {
    "enabled": true,
    "list": ["proxy1.com:8080", "proxy2.com:8080"],
    "rotation": "per_request"
  }
}
```

**Status:** 🔴 Not started
**Priority:** **Do this second** - needed for real-world scraping

---

### 3. Cloudflare Bypass ⭐⭐
**Why:** Many sites block bots with Cloudflare.

**What:**
- Better browser fingerprinting
- Handle Cloudflare challenges
- Stealth mode improvements

**Status:** 🟡 Partial (Playwright has basic stealth)
**Priority:** **Do this third** - unblocks protected sites

---

## 📋 Nice to Have (Later)

### 4. Better Error Handling
- Smart retry logic
- Queue failed items
- Resume from failures

**Status:** 🟡 Partial
**Priority:** ⭐

### 5. Authentication Support
- Login before scraping
- Session persistence
- Cookie management

**Status:** 🔴 Not started
**Priority:** ⭐

### 6. Export Improvements
- More formats (Excel, SQL)
- Direct S3/cloud upload
- Scheduled exports

**Status:** 🟡 Partial
**Priority:** ⭐

---

## 🚫 Not Doing (Too Complex)

- PDF extraction
- API endpoint scraping
- Distributed scraping
- LLM-based extraction
- Captcha solving
- MCP integration
- REST API

**Why skip these?** Over-engineering. Focus on core scraping first.

---

## 🎯 Execution Plan

**Phase 1 (Critical):**
1. ✅ Infinite scroll support (DONE)
2. 🔴 Selector-based parsing (NEXT)
3. 🔴 Proxy support
4. 🔴 Cloudflare improvements

**Phase 2 (Nice to have):**
- Better error handling
- Authentication
- Export improvements

**Stop there.** Don't over-build.

---

## 📈 Status Legend
- 🔴 Not started
- 🟡 Partial
- ✅ Complete
- ⭐⭐⭐ Critical
- ⭐⭐ Important
- ⭐ Nice to have
