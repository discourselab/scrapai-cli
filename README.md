# scrapai-cli

Scrapy spider generation for large-scale web scraping. Built for Claude Code to easily add new websites.

## For Claude Code Instances

**When asked to add any website, follow this systematic process:**

1. **Check for sitemaps** → Choose spider type
2. **Analyze site structure** → Get selectors  
3. **Copy template** → Modify for site
4. **Test spider** → Verify it works
5. **Run spider** → Get articles

## Quick Start

### 1. Setup Environment

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment in the repo
uv venv

# Activate virtual environment (ALWAYS use this in the repo)
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install dependencies
uv pip install -r requirements.txt

# Verify setup
./scrapai list
```

### 2. Add a Website - Step by Step

#### Step 1: Check for Sitemaps

```python
from core.sitemap import SitemapDiscovery

discovery = SitemapDiscovery('https://example.com')
sitemaps = discovery.discover_sitemaps()

if sitemaps:
    print(f"✅ Found sitemaps: {sitemaps}")
    # Use SitemapSpider template
else:
    print("❌ No sitemaps found")
    # Use CrawlSpider template
```

#### Step 2: Analyze Site Structure

```bash
# Use the inspector tool
bin/inspector --url https://example.com

# This creates analysis files in data/[site]/analysis/
# Look at analysis.json for selectors
```

**If HTML is unclear/empty (JavaScript-based site):**
```python
# Use headless browser for JavaScript-heavy sites
from utils.browser import BrowserClient

browser = BrowserClient()
html = browser.get_rendered_html('https://example.com')
print(html[:500])  # Check if content is now visible
```

#### Step 3: Choose and Copy Template

**If sitemaps exist:**
```bash
cp templates/sitemap_spider_template.py scrapers/spiders/sitename.py
```

**If no sitemaps:**
```bash
cp templates/crawl_spider_template.py scrapers/spiders/sitename.py
```

#### Step 4: Modify Template

**Replace in the copied file:**
1. `SITENAME` → actual spider name
2. `example.com` → actual domain
3. Update URLs (start_urls or sitemap_urls)
4. Update selectors based on analysis

#### Step 5: Test and Run

```bash
# Test with limited items
./scrapai test sitename

# Run full crawl
./scrapai crawl sitename --limit 100 --output articles.json
```

## Project Structure

```
scrapai-cli/
├── templates/                          # Spider templates
│   ├── crawl_spider_template.py       # For sites without sitemaps
│   └── sitemap_spider_template.py     # For sites with sitemaps
├── core/                               # Analysis tools
│   ├── sitemap.py                     # Sitemap discovery
│   ├── analyzer.py                    # Site structure analysis
│   └── add_site.py                    # Automated workflow (optional)
├── scrapers/                          # Scrapy project
│   ├── spiders/                       # Generated spiders go here
│   ├── settings.py                   # Scrapy configuration
│   └── items.py                      # Data models
├── utils/                             # Utilities (http, logging, etc.)
├── bin/                              # Analysis tools
├── scrapai                           # CLI to run spiders
└── scrapy.cfg                        # Scrapy configuration
```

## Available Tools

### 1. Sitemap Discovery

```python
from core.sitemap import SitemapDiscovery

discovery = SitemapDiscovery('https://example.com')
sitemaps = discovery.discover_sitemaps()
article_urls = discovery.get_all_article_urls()[:10]
```

### 2. Inspector Tool

```bash
# Analyze website structure
bin/inspector --url https://example.com

# Creates analysis files in data/[site]/analysis/
```

### 3. Browser Client

```python
from utils.browser import BrowserClient

# For JavaScript-heavy sites (when HTML is garbled/empty)
browser = BrowserClient()
html = browser.get_rendered_html('https://example.com')
```

## Spider Templates

### CrawlSpider (No Sitemaps)
**Use when:** No sitemaps found, need to follow links manually

### SitemapSpider (Has Sitemaps)  
**Use when:** Site has sitemap.xml files

## CLI Commands

```bash
# List available spiders
./scrapai list

# Test a spider
./scrapai test spidername

# Run a spider
./scrapai crawl spidername --limit 100 --output articles.json
```

## Common Selector Patterns

### News/Article Sites
```css
title:     h1, .headline, .article-title
content:   article p, .article-body p, .content p
date:      time, .date, .published
author:    .author, .byline, [rel="author"]
tags:      .tag, .category, .label
```

## Output Format

```json
{
  "url": "https://example.com/article/...",
  "title": "Article title",
  "content": "Full article text...",
  "published_date": "2024-01-15",
  "author": "Author name",
  "tags": ["tag1", "tag2"],
  "source": "sitename",
  "scraped_at": "2024-01-15T10:30:00"
}
```

## Decision Tree

```
User asks: "Add [website] to scrapai"
│
├─ Check sitemaps with core/sitemap.py
│  │
│  ├─ Sitemaps found?
│  │  ├─ YES → Use sitemap_spider_template.py
│  │  │        → Update sitemap_urls
│  │  │        → Analyze sample articles for selectors
│  │  │
│  │  └─ NO  → Use crawl_spider_template.py
│  │           → Analyze site navigation
│  │           → Update start_urls and rules
│  │
├─ Analyze site structure with bin/inspector
├─ Copy appropriate template
├─ Modify selectors based on analysis
├─ Test with ./scrapai test [spider]
└─ Run with ./scrapai crawl [spider] --limit 100
```

## Common Issues

### No Articles Found
- Check selectors with browser developer tools
- Verify URLs are correct
- Look at spider logs for errors

### Wrong Content Extracted  
- Update CSS selectors in parse_article method
- Test selectors in browser console first
- Check for JavaScript-loaded content

### JavaScript-Heavy Sites
- HTML appears garbled/compressed? Use headless browser
- Content not loading? Site likely uses JavaScript
- Use `utils.browser.BrowserClient()` for proper rendering

### Spider Not Found
- Ensure file is in scrapers/spiders/ directory
- Check file naming matches spider name
- Verify Python syntax is correct