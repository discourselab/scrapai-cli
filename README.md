# scrapai-cli

Scrapy spider generation for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites.

## For Claude Code Instances

**When asked to add any website, follow this systematic process:**

1. **Analyze site structure** → Use inspector tool (handles JavaScript rendering internally)
2. **Check for sitemaps** → Determine spider strategy  
3. **Generate domain-specific spider** → Create custom extraction code for this specific site
4. **Test spider** → Verify extraction works
5. **Run spider** → Collect articles

**IMPORTANT:** Don't use generic templates. Generate custom spider code based on actual site analysis.

## Quick Start

### 1. Setup Environment

```bash
# Activate virtual environment (ALWAYS use this in the repo)
source .venv/bin/activate  # Linux/Mac

# Install Playwright browsers (required for inspector)
playwright install

# Verify setup
./scrapai list
```

### 2. Add a Website - Proper Analysis Process

**Step 1: Analyze the actual page structure**
```bash
bin/inspector --url https://example.com
# Inspector automatically handles JavaScript rendering when needed
# Creates analysis files in data/[site]/analysis/
```

**Step 2: Generate domain-specific spider**
```python
# DON'T use generic generate_spider_from_analysis()
# Instead, create custom spider code based on:
# - Actual selectors found in the HTML analysis
# - Site-specific URL patterns  
# - Domain-specific content structure
# - Proper extraction logic for this specific site
```

**Step 3: Write the spider with proper selectors**
- Use the analysis to understand the actual page structure
- Create selectors that match the real HTML elements
- Test extraction on sample articles
- Generate spider code that works for this specific domain

## Project Structure

```
scrapai-cli/
├── core/                               # Analysis and generation tools
│   ├── sitemap.py                     # Sitemap discovery
│   ├── analyzer.py                    # Site structure analysis  
│   ├── spider_templates.py            # Spider code generation
│   └── add_site.py                    # Automated workflow
├── scrapers/                          # Scrapy project
│   ├── spiders/                       # Generated spiders go here
│   ├── settings.py                   # Scrapy configuration
│   └── items.py                      # Data models
├── utils/                             # Utilities (http, logging, etc.)
├── bin/                              # Analysis tools
├── scrapai                           # CLI to run spiders
└── scrapy.cfg                        # Scrapy configuration
```

## Analysis Tools

### 1. Inspector Tool
Analyzes page structure and generates selectors:

```bash
bin/inspector --url https://example.com
# Creates analysis files in data/[site]/analysis/
```

### 2. Sitemap Discovery
```python
from core.sitemap import SitemapDiscovery

discovery = SitemapDiscovery('https://example.com')
sitemaps = discovery.discover_sitemaps()
article_urls = discovery.get_all_article_urls()[:10]
```

### 3. Browser Client (for JavaScript sites)
```python
from utils.browser import BrowserClient

browser = BrowserClient()
html = browser.get_rendered_html('https://example.com')
```

## CLI Commands

```bash
# List available spiders
./scrapai list

# Test a spider (limited items)
./scrapai test spidername

# Run a spider
./scrapai crawl spidername --limit 100 --output articles.json
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

## Claude Code Decision Process

```
User asks: "Add [website] to scrapai"
│
├─ Run inspector to analyze actual page structure
│  └─ Inspector uses browser.py internally for JavaScript sites
├─ Check for sitemaps with core/sitemap.py  
├─ Generate CUSTOM spider code (not generic templates)
│  ├─ Analyze real selectors from HTML
│  ├─ Create domain-specific extraction logic
│  └─ Write spider tailored to this specific site
├─ Test with ./scrapai test [spider]
└─ Validate extraction works properly
```

## Common Patterns

### News/Article Sites
- Look for article containers, headlines, bylines
- Check for pagination and category pages  
- Analyze date formats and author attribution
- Test content extraction depth

### Sitemap vs Crawl Strategy
- **Sitemap Spider**: When site has comprehensive sitemaps
- **Crawl Spider**: When need to follow navigation links
- **Mixed Strategy**: Use both for maximum coverage

## Troubleshooting

### No Articles Found
- Check selectors match actual page structure
- Verify URLs are being extracted correctly
- Look at spider logs for crawl patterns

### Wrong Content Extracted  
- Re-run inspector on sample articles
- Update selectors based on analysis
- Test on multiple article types

### JavaScript-Heavy Sites
- Use BrowserClient for proper rendering
- Check if content loads after page load
- Consider API endpoints if available