# scrapai-cli

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites with multi-project isolation and newspaper4k-powered content extraction.

## For Claude Code Instances

**When asked to add any website, follow the 3-phase enhanced workflow:**

1. **Phase 1: URL Collection** → Create basic spider to collect article URLs
2. **Phase 2: Parser Creation** → Analyze samples and create newspaper4k parser
3. **Phase 3: Integration** → Integrate parser into spider and deploy

**IMPORTANT:**

- Use the newspaper4k library for content extraction (not CSS selectors)
- Always test parsers on sample URLs before integration
- **ALWAYS inspect collected URLs** and make spider restrictive to avoid non-article pages
- Create spiders in the shared `spiders/` directory and parsers in `parsers/`
- Use project system for client isolation and output organization

## Claude Code Decision Process - ENHANCED WORKFLOW

**When user says: "Add [website] to our system" or "Create project X and add [website] to it"**

```
PHASE 1: PROJECT SETUP & HTML ANALYSIS
│
├─ 1. CREATE PROJECT (if needed)
│  └─ ./scrapai projects create --name X --spiders ""
│
├─ 2. INSPECT WEBSITE STRUCTURE
│  ├─ bin/inspector --url https://website.com/
│  ├─ Analyze homepage HTML structure and link patterns
│  ├─ Identify article URL patterns vs non-article pages
│  └─ Create analysis files in data/website/analysis/
│
├─ 3. CREATE BASIC URL-COLLECTING SPIDER
│  ├─ Create spiders/website.py based on inspector findings
│  ├─ Use restrictive rules targeting ONLY article URLs
│  ├─ Focus ONLY on collecting article URLs (not content extraction)
│  ├─ Use homepage crawling to find articles (sitemap only if user requests)
│  └─ Save URLs to data/website/urls.json
│
├─ 4. RUN URL COLLECTION
│  ├─ ./scrapai test --project X website --limit 5
│  └─ Collect representative article URLs for analysis
│
├─ 5. INSPECT COLLECTED URLS & ITERATIVE FILTERING
│  ├─ Review collected URLs in projects/X/outputs/spider/latest.json
│  ├─ If navigation/category pages are found instead of actual articles:
│  │  ├─ Add specific deny patterns to spider rules for those nav/category URLs
│  │  ├─ Re-run URL collection: ./scrapai test --project X website --limit 5
│  │  └─ Repeat until only actual article URLs are captured
│  ├─ Ensure only articles are captured (no categories, static pages, etc.)
│  └─ Continue iterating until spider collects real article content
│
PHASE 2: CONTENT ANALYSIS & PARSER CREATION
│
├─ 6. ANALYZE SAMPLE ARTICLES
│  ├─ Take 3-5 URLs from collected data/website/urls.json
│  ├─ Show Claude Code the actual article URLs for inspection
│  ├─ Claude analyzes HTML structure and content patterns
│  └─ Identify extraction requirements (title, content, author, date, etc.)
│
├─ 7. USE SHARED NEWSPAPER4K PARSER
│  ├─ Import and use utils.newspaper_parser.parse_article() in spider
│  ├─ Shared parser handles proxies, retries, and standardized output automatically
│  ├─ No need to create domain-specific parser files
│  ├─ Custom metadata extraction only if shared parser misses site-specific data
│  └─ Focus on spider URL collection rules, not parsing logic
│
├─ 8. TEST PARSER ON SAMPLE URLS
│  ├─ Test parser against 5-10 collected URLs (using existing framework)
│  ├─ Validate extraction: title, content, authors, publish_date, images
│  ├─ Check newspaper4k's automatic extraction quality
│  ├─ Use existing CLI commands for testing (no custom scripts)
│  └─ Refine parser if needed for missing metadata
│
PHASE 3: INTEGRATION & DEPLOYMENT
│
├─ 9. INTEGRATE SHARED PARSER INTO SPIDER
│  ├─ Update spiders/website.py to use utils.newspaper_parser.parse_article()
│  ├─ Replace URL collection logic with content parsing
│  ├─ Import from utils.newspaper_parser import parse_article
│  └─ Maintain Scrapy framework for URL discovery
│
├─ 10. FINAL TESTING
│  ├─ ./scrapai test --project X website --limit 5
│  ├─ Verify complete article extraction (not just URLs)
│  └─ Ensure 100% success rate for content extraction
│
├─ 11. ADD TO PROJECT CONFIG
│  ├─ Edit projects/X/config.yaml
│  ├─ Add "website" to spiders list
│  └─ Configure any site-specific settings
│
└─ 12. READY FOR PRODUCTION
   ├─ ./scrapai crawl --project X website --limit 100
   └─ Full article content extraction with reliable newspaper4k
```

## Why newspaper4k Over CSS Selectors?

**Problems with Traditional CSS Selectors:**

- Break when sites update HTML structure
- Miss content from varying layouts
- Extract wrong content (ads, navigation)
- Require manual selector maintenance
- Fragile and site-specific

**Benefits of newspaper4k:**

- Automatic content extraction using ML
- Handles layout variations automatically
- Extracts clean article text reliably
- Provides metadata (authors, dates, images)
- Minimal custom code needed
- Works across different site structures

## Quick Start

### 1. Setup Environment

```bash
# Activate virtual environment (ALWAYS use this in the repo)
source .venv/bin/activate  # Linux/Mac

# Install dependencies if not already installed
pip install newspaper4k

# Install Playwright browsers (required for inspector, if not already installed)
playwright install

# Check available projects
./scrapai projects list
```

### 2. Project Management

**Create a new project:**

```bash
./scrapai projects create --name client-team-a --spiders ""
```

**List all projects:**

```bash
./scrapai projects list
```

**Check project status:**

```bash
./scrapai projects status --project client-team-a
```

### 3. Example: Adding a New Website

**User request:** "Add https://example-news-site.com/ to our system"

**Phase 1 - URL Collection:**

```bash
# Check if project exists or create new one
./scrapai projects list
./scrapai projects create --name MyProject --spiders ""

# Claude creates spiders/example_news.py (URL collection only)
# Run URL collection
./scrapai test --project MyProject example_news --limit 5
```

**Phase 2 - Parser Creation:**

```bash
# Claude analyzes sample URLs and creates parsers/example_news.py
# Test parser on sample URLs
./scrapai test --project MyProject example_news --limit 5
```

**Phase 3 - Integration:**

```bash
# Claude integrates parser into spider
# Final production test
./scrapai crawl --project MyProject example_news --limit 100
```

## Project Structure

```
scrapai-cli/
├── spiders/                            # Shared spider library
│   ├── __init__.py
│   ├── base_spider.py                  # Base class with common functionality
│   ├── politifact.py                   # Domain-specific spiders
├── parsers/                            # newspaper4k-based parsers
│   ├── __init__.py
│   ├── politifact.py                   # Domain-specific parsers
├── projects/                           # Project instances (client isolation)
│   ├── client-team-a/
│   │   ├── config.yaml                 # Project configuration
│   │   ├── outputs/                    # Project-specific outputs
│   │   │   ├── politifact/
│   │   │   └── desmog/
│   │   └── logs/                       # Project-specific logs
│   ├── client-team-b/
│   │   ├── config.yaml
│   │   ├── outputs/
│   │   └── logs/
│   └── internal-research/
│       ├── config.yaml
│       ├── outputs/
│       └── logs/
├── data/                               # URL collection and analysis
│   └── politifact/
│       ├── urls.json
│       └── analysis/
├── core/                               # Analysis and project management
│   ├── project_manager.py              # Project creation and management
│   ├── config_loader.py                # YAML configuration handling
│   ├── sitemap.py                      # Sitemap discovery
│   └── analyzer.py                     # Site structure analysis
├── utils/                              # Utilities (http, logging, etc.)
├── bin/                               # Analysis tools
├── settings.py                        # Default Scrapy configuration
├── scrapai                           # Enhanced CLI with project support
└── scrapy.cfg                        # Scrapy configuration
```

## Shared Parser Implementation

**utils/newspaper_parser.py** (already created):

The system now uses a shared newspaper4k parser with built-in proxy support, retry logic, and standardized output. Key features:

- **Automatic proxy handling**: Integrates with existing `utils/http.py` proxy infrastructure
- **Retry logic**: Built-in retry with exponential backoff for failed requests
- **Content cleaning**: Automatic cleaning of titles and content
- **Standardized output**: Consistent data structure across all sites
- **Multiple proxy types**: Supports 'none', 'static', 'residential', and 'auto' modes

```python
from utils.newspaper_parser import parse_article

# Simple usage - auto proxy selection
article_data = parse_article(url, source_name='desmog')

# Advanced usage with specific proxy type
from utils.newspaper_parser import NewspaperParser
parser = NewspaperParser(proxy_type='residential')
article_data = parser.parse_article(url, source_name='desmog')
```

**Benefits:**
- ✅ No duplicate parser code across domains
- ✅ Centralized proxy configuration and retry logic
- ✅ Consistent output format for all sites
- ✅ Easy to maintain and update parsing logic
- ✅ Built-in content cleaning and validation

**spiders/website.py (integrated with shared parser):**

```python
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article

class WebsiteSpider(BaseSpider):
    name = 'website'
    allowed_domains = ['website.com', 'www.website.com']
    start_urls = ['https://www.website.com/']
    
    # Define crawling rules - liberal approach with deny rules only
    rules = (
        # Follow all article links, only excluding static/non-article pages
        Rule(LinkExtractor(
            deny=r'/(about|contact|donate|privacy|terms|advertise|careers|subscribe|help|support|login|register)/?$'
        ), callback='parse_article', follow=True),
        # Follow pagination and navigation pages
        Rule(LinkExtractor(
            allow=r'/(page|category|tag|archive)/',
            deny=r'/(about|contact|donate|privacy|terms)/'
        ), follow=True),
    )

    def parse_article(self, response):
        """Parse article using shared newspaper4k parser"""
        # Use the shared newspaper4k parser with automatic proxy handling
        article_data = parse_article(response.url, source_name=self.name)
        
        if article_data:
            # Create enhanced item using newspaper4k extracted data
            item = self.create_item(response, **article_data)
            yield item
        else:
            # Fallback for failed parsing
            self.logger.warning(f"Failed to parse article: {response.url}")
            item = self.create_item(response, 
                url=response.url,
                title=response.css('title::text').get(),
                status='parse_failed'
            )
            yield item
```

## Project Configuration

Each project has a `config.yaml` file:

```yaml
project_name: "client-team-a"
spiders:
  - politifact

settings:
  download_delay: 2
  concurrent_requests: 4
  concurrent_requests_per_domain: 2
  robotstxt_obey: true
  # newspaper4k settings
  newspaper_config:
    memoize_articles: false
    fetch_images: true
output_format: json
```

## CLI Commands

### Project Management

```bash
# Create project with spiders
./scrapai projects create --name BrownU --spiders politifact,desmog

# Create project without spiders (add later)
./scrapai projects create --name ClientA --spiders ""

# List all projects
./scrapai projects list

# Project status
./scrapai projects status --project client-team-a

# Delete project (with confirmation)
./scrapai projects delete --project client-team-a
```

### Spider Operations

```bash
# List all available spiders
./scrapai list

# List spiders for specific project
./scrapai list --project client-team-a

# Run specific spider
./scrapai crawl --project client-team-a website --limit 100

# Run all project spiders
./scrapai crawl-all --project client-team-a

# Test spider
./scrapai test --project client-team-a website --limit 5
```

### Monitoring

```bash
# Project status
./scrapai status --project client-team-a

# View logs
./scrapai logs --project client-team-a
./scrapai logs --project client-team-a --spider website
```

## Output Format

```json
{
  "url": "https://www.example-news-site.com/2025/07/08/sample-article/",
  "title": "Sample News Article Title",
  "content": "The full article content extracted by newspaper4k...",
  "author": "John Doe, Jane Smith",
  "published_date": "2025-07-08T10:30:00",
  "top_image": "https://www.example-news-site.com/images/article.jpg",
  "meta_data": {
    "viewport": "width=device-width, initial-scale=1",
    "author": "John Doe",
    "description": "Article description from meta tags",
    "og:site_name": "Example News"
  },
  "source": "example_news",
  "project": "MyProject",
  "scraped_at": "2025-07-12T15:45:00",
  "extracted_at": "2025-07-12T15:45:00"
}
```

## Analysis Tools

### 1. Inspector Tool

```bash
# Analyze single URL
bin/inspector --url https://www.example-news-site.com/2025/07/08/some-article/
# Creates analysis files in data/example_news/analysis/
```

### 2. Sitemap Discovery

```python
from core.sitemap import SitemapDiscovery

discovery = SitemapDiscovery('https://www.example-news-site.com')
sitemaps = discovery.discover_sitemaps()
article_urls = discovery.get_all_article_urls()[:10]
```

### 3. Browser Client (for JavaScript sites)

```python
from utils.browser import BrowserClient

browser = BrowserClient()
html = browser.get_rendered_html('https://www.example-news-site.com')
```

## IMPORTANT CONSTRAINTS FOR CLAUDE CODE

**Decision Making Philosophy:**

- 🔄 **Be Liberal by Default**: For any spiders and parsers, be liberal in implementation choices unless explicitly told by users
- 🚫 **Minimal Restrictions**: Don't make too many decisions or impose unnecessary constraints
- 👤 **User-Driven**: Only apply specific restrictions when explicitly requested by users

**⚠️ CRITICAL: What "Liberal by Default" Means:**

- ❌ **DON'T** filter by date ranges (like `/2024/`, `/2023/`) unless user specifies
- ❌ **DON'T** limit content types arbitrarily 
- ❌ **DON'T** restrict URL patterns beyond basic article detection
- ❌ **DON'T** add unnecessary conditions or filters
- ❌ **DON'T** use sitemap crawling unless user explicitly requests it
- ✅ **DO** collect ALL available content from the site
- ✅ **DO** use broad URL patterns that capture maximum content
- ✅ **DO** let users specify restrictions if they want them
- ✅ **DO** focus on homepage crawling for article discovery

**⚠️ SYSTEMATIC APPROACH: Liberal with Website-Specific Deny Rules**

Follow this systematic approach for creating spiders:

1. **ALLOW ALL by default** - No restrictive allow patterns
2. **INSPECT the actual website** - Look at real URL patterns from inspector and collected data
3. **CREATE SERIOUS DENY RULES** - Based on actual website structure, not guessing
4. **WEBSITE-SPECIFIC RULES** - Each site has unique patterns, don't copy/paste

**Common deny patterns (but always inspect first):**
- ❌ **DENY**: `/about/`, `/contact/`, `/donate/`, `/privacy/`, `/terms/`, `/advertise/`, `/careers/`, `/subscribe/`, `/help/`, `/support/`, `/login/`, `/register/`
- ❌ **DENY**: Navigation pages like `/category/$`, `/tag/$`, `/author/$`, `/search/$`
- ❌ **DENY**: Archive pages like `/news/$`, `/articles/$` (but allow `/news/article-slug/`)
- ✅ **INSPECT**: `data/website/urls.json` and `data/website/analysis/page.html` to identify patterns
- ✅ **SYSTEMATIC**: Never guess patterns - always base on real website inspection

**Examples of Liberal vs Restrictive Code:**

```python
# ❌ RESTRICTIVE (Don't do this unless user asks)
Rule(LinkExtractor(allow=r'/fact-check/[^/]+/$'), callback='parse_article', follow=True)

# ✅ LIBERAL (Default approach - allow all, deny only static pages)
Rule(LinkExtractor(
    deny=r'/(about|contact|donate|privacy|terms|advertise|careers|subscribe)/?$'
), callback='parse_article', follow=True)
```

```python
# ❌ RESTRICTIVE 
Rule(LinkExtractor(allow=r'/\d{4}/\d{2}/\d{2}/[^/]+/$'), callback='parse_article')

# ✅ LIBERAL
Rule(LinkExtractor(
    deny=r'/(about|contact|donate|help|support|login)/?$'
), callback='parse_article', follow=True)
```

**What Claude Code CAN create/modify:**

- ✅ `spiders/website.py` (domain-specific spiders using shared parser)
- ✅ `projects/X/config.yaml` (project configurations)
- ✅ Domain-specific data files in `data/website/`
- ✅ `utils/newspaper_parser.py` (shared parsing logic - already created)

**What Claude Code CANNOT modify:**

- ❌ `core/` directory files (framework code)
- ❌ `utils/` directory files (utility functions) - except newspaper_parser.py
- ❌ `bin/` directory files (CLI tools)
- ❌ `settings.py`, `scrapy.cfg` (framework config)
- ❌ Create new custom execution scripts
- ❌ Modify existing framework functionality

**Testing approach:**

- Use existing `./scrapai test` commands
- Use existing inspector tools
- No custom testing scripts

## Benefits of This System

### Code Reuse

- Write parser once in `parsers/`
- Use across multiple projects
- newspaper4k handles content extraction universally

### Client Isolation

- Separate outputs per project
- Independent configurations
- Isolated logging

### Reliability

- newspaper4k's ML-based extraction
- Handles site updates automatically
- Consistent output format

### Easy Management

- Track crawls by client
- Different spider combinations per project
- Project-specific settings

### Scalability

- Add new clients easily
- Organize hundreds of websites
- Clear billing/usage tracking

## Common Patterns

### News/Article Sites

- Create URL-collecting spider first
- Use newspaper4k for content extraction
- Add custom metadata extraction only if needed
- Test thoroughly before deployment

### Crawl Strategy

- **Homepage Crawling**: Default approach - follow navigation links from homepage
- **Sitemap Spider**: Only when user explicitly requests sitemap crawling
- **Mixed Strategy**: Use both only if user specifically asks for sitemap + crawling

## Troubleshooting

### Project Issues

- **Project not found**: Use `./scrapai projects list` to check available projects
- **Spider not configured**: Check project's `config.yaml` file
- **No outputs**: Check `projects/[name]/outputs/` directory

### Spider Issues

- **No Articles Found**: Check URL collection phase first
- **Poor Content Extraction**: newspaper4k usually handles this automatically
- **Missing Metadata**: Add custom extraction to parser if needed
- **JavaScript-Heavy Sites**: Use BrowserClient for proper rendering

### Parser Issues

- **Empty Content**: Check if newspaper4k can access the URL
- **Missing Authors/Dates**: newspaper4k extracts these automatically, add custom logic only if needed
- **Proxy Issues**: Pass proxy configuration to newspaper4k

### Permission/Access

- **Spider not found**: Ensure spider exists in `spiders/` directory
- **Parser not found**: Ensure parser exists in `parsers/` directory
- **Config errors**: Validate YAML syntax in project config
- **Output permission**: Check write access to project directories
