# scrapai-cli

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites with multi-project isolation and newspaper4k-powered content extraction.

## For Claude Code Instances

**When asked to add any website, follow the 4-phase workflow:**

1. **Phase 1: Analysis** → Inspect site structure and plan approach
2. **Phase 2: Discovery** → Create spider and test URL discovery
3. **Phase 3: Extraction** → Add content parsing and validate quality
4. **Phase 4: Production** → Scale test and deploy

**CORE PRINCIPLES:**

- Write Scrapy rules based on actual site analysis (not templates)
- Use newspaper4k for content extraction (never CSS selectors)
- Filter by content quality, not complex URL patterns
- Always use proxies for production crawling
- Test small, validate quality, then scale

## Claude Code Workflow

**When user says: "Add [website] to our system"**

```
PHASE 1: SITE ANALYSIS
│
├─ 1. CREATE PROJECT (if needed)
│  └─ ./scrapai projects create --name X --spiders ""
│
├─ 2. ANALYZE SITE STRUCTURE
│  ├─ source .venv/bin/activate  # ALWAYS activate venv first
│  ├─ bin/inspector --url https://website.com/
│  ├─ Look at homepage structure and navigation
│  ├─ Find 3-5 sample article URLs manually
│  ├─ Note any obvious patterns (date URLs, category structure, etc.)
│  └─ Document findings in data/website/analysis/
│
└─ 3. PLAN SPIDER APPROACH
   ├─ How should spider discover articles? (follow categories? pagination?)
   ├─ What pages to avoid? (about, contact, search results, etc.)
   └─ Ready for Phase 2

PHASE 2: SPIDER CREATION & DISCOVERY TESTING
│
├─ 4. CREATE SPIDER WITH DISCOVERY RULES
│  ├─ Write Scrapy rules based on Phase 1 analysis
│  ├─ Start with broad discovery, add denys for obvious non-content
│  ├─ Focus on URL discovery first (no content parsing yet)
│  └─ Save spider as spiders/website.py
│
├─ 5. TEST DISCOVERY
│  ├─ source .venv/bin/activate  # ALWAYS activate venv first
│  ├─ ./scrapai test --project X website --limit 20
│  ├─ Check what URLs were discovered
│  └─ Are most URLs actual articles? Or mostly navigation pages?
│
├─ 6. REFINE RULES IF NEEDED
│  ├─ If too many non-articles: add deny patterns for navigation
│  ├─ If missing articles: reduce restrictions
│  ├─ Re-test until >80% discovered URLs are articles
│  └─ Document final rule decisions
│
└─ DISCOVERY QUALITY CHECK: >80% of found URLs are articles

PHASE 3: CONTENT EXTRACTION & VALIDATION
│
├─ 7. ADD CONTENT PARSING
│  ├─ Add parse_article callback to rules
│  ├─ Use newspaper4k via utils.newspaper_parser.parse_article()
│  ├─ Add basic content quality checks (length, title presence)
│  └─ Enable proxy usage for extraction
│
├─ 8. TEST CONTENT EXTRACTION
│  ├─ source .venv/bin/activate  # ALWAYS activate venv first
│  ├─ ./scrapai test --project X website --limit 25
│  ├─ Check extraction success rate and content quality
│  └─ Validate titles, content length, metadata extraction
│
├─ 9. OPTIMIZE QUALITY
│  ├─ Add content filtering for navigation pages
│  ├─ Adjust newspaper4k settings if needed
│  ├─ Fine-tune rules based on extraction results
│  └─ Re-test until >85% extraction success
│
└─ EXTRACTION QUALITY CHECK: >85% successful extractions

PHASE 4: PRODUCTION DEPLOYMENT
│
├─ 10. PRODUCTION TESTING
│  ├─ source .venv/bin/activate  # ALWAYS activate venv first
│  ├─ ./scrapai test --project X website --limit 100
│  ├─ Verify performance at scale
│  ├─ Check for blocking or rate limiting issues
│  └─ Confirm quality remains consistent
│
├─ 11. PROJECT CONFIGURATION
│  ├─ Add spider to projects/X/config.yaml
│  ├─ Configure appropriate delays and proxy settings
│  └─ Set production crawling parameters
│
└─ 12. DEPLOY
   ├─ source .venv/bin/activate  # ALWAYS activate venv first
   ├─ ./scrapai crawl --project X website --limit 500
   └─ Monitor initial production run
```

## Spider Creation Guidelines

### Basic Spider Structure

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

    rules = (
        # Write rules based on your Phase 1 analysis
        # Example approach - customize based on actual site:
        Rule(LinkExtractor(
            deny=r'/(about|contact|privacy|terms|login|register)/?$'
        ), callback='parse_article', follow=True),
    )

    def parse_article(self, response):
        """Extract content with quality validation"""
        # Quick quality check
        if not self._is_article_page(response):
            return

        # Use shared newspaper4k parser (handles proxies automatically)
        article_data = parse_article(response.url, source_name=self.name)

        if article_data and self._validate_content(article_data):
            item = self.create_item(response, **article_data)
            yield item

    def _is_article_page(self, response):
        """Filter out non-article pages"""
        # Content length check
        body_text = ' '.join(response.css('body ::text').getall())
        if len(body_text.strip()) < 500:
            return False

        # Title check
        title = response.css('title::text').get() or ''
        if len(title.strip()) < 10:
            return False

        return True

    def _validate_content(self, article_data):
        """Validate extracted content quality"""
        return (article_data.get('content') and
                len(article_data['content']) > 200 and
                article_data.get('title'))
```

### Rule Writing Principles

**Start Simple:**

```python
# Begin with broad discovery
Rule(LinkExtractor(), callback='parse_article', follow=True)
```

**Add Denys Based on Actual Site:**

```python
# After testing, add specific denys for what you actually found
Rule(LinkExtractor(
    deny=r'/(about|contact|search|tag|category)/?$'  # Based on inspection
), callback='parse_article', follow=True)
```

**Common Patterns (Adapt to Your Site):**

```python
# News sites with categories
Rule(LinkExtractor(deny=r'/(about|contact)/?$'), callback='parse_article', follow=True)

# Blogs with date structure
Rule(LinkExtractor(allow=r'/\d{4}/\d{2}/'), callback='parse_article', follow=True)

# Sites with clear article sections
Rule(LinkExtractor(allow=r'/(news|articles|posts)/'), callback='parse_article', follow=True)
```

**Don't Overthink URL Patterns:**

- Let content validation do the heavy lifting
- Most sites work with simple deny patterns
- Complex allow patterns often miss content

## Content Extraction

### Newspaper4k Parser

The system uses a shared newspaper4k parser that handles proxies automatically:

```python
def parse_article(self, response):
    """Extract content using shared parser"""
    # Parser handles proxy selection automatically
    article_data = parse_article(response.url, source_name=self.name)

    if article_data and self._validate_content(article_data):
        item = self.create_item(response, **article_data)
        yield item
```

**Parser features:**

- Automatic proxy handling (none → static → residential)
- Built-in retry logic and error handling
- Standardized output format across all sites
- Content cleaning and validation

### Handling Blocking

If sites start blocking requests:

1. **Increase delays** in project config:

```yaml
settings:
  download_delay: 4 # Increase from default 2
  concurrent_requests: 2 # Lower concurrency
```

2. **Parser automatically escalates** proxy usage internally
3. **Monitor logs** for extraction success rates
4. **No code changes needed** - parser handles proxy escalation

## Quality Validation

### Discovery Quality (Phase 2)

```bash
# After testing discovery:
source .venv/bin/activate
./scrapai test --project X website --limit 20
# Check: Are >80% of URLs actual articles?
# If no: Add deny patterns for navigation pages
# If yes: Proceed to Phase 3
```

### Extraction Quality (Phase 3)

```bash
# Check extraction results:
source .venv/bin/activate
./scrapai test --project X website --limit 25
# Title extraction: >95% success
# Content extraction: >85% success
# Content length: >200 chars average
# No navigation text in content
```

### Production Quality (Phase 4)

```bash
# Production scale validation:
source .venv/bin/activate
./scrapai test --project X website --limit 100
# Consistent quality at 100+ articles
# No blocking or rate limiting
# Reasonable crawl performance
# Clean extracted content
```

## Common Site Patterns

### News Sites

```python
# Most news sites: follow everything, filter by content
Rule(LinkExtractor(
    deny=r'/(about|contact|advertise|subscribe)/?$'
), callback='parse_article', follow=True)
```

### Blogs

```python
# Blog sites: often have clear post patterns
Rule(LinkExtractor(
    deny=r'/(about|contact|page)/?$'
), callback='parse_article', follow=True)
```

### Academic/Research

```python
# Focus on specific content sections
Rule(LinkExtractor(
    allow=r'/(research|publications|news)/',
    deny=r'/(faculty|admin|courses)/?$'
), callback='parse_article', follow=True)
```

## Project Management

### Create Project

```bash
source .venv/bin/activate  # ALWAYS activate first
./scrapai projects create --name ClientA --spiders ""
```

### Add Spider to Project

```yaml
# Edit projects/ClientA/config.yaml
spiders:
  - website_name
```

### Run Commands

```bash
source .venv/bin/activate  # ALWAYS activate first

# Development testing
./scrapai test --project ClientA website --limit 20

# Production crawling
./scrapai crawl --project ClientA website --limit 1000
```

## Error Handling

### Common Issues

**Too many navigation pages discovered:**

- Add deny patterns for `/category/`, `/tag/`, `/archive/`
- Strengthen content length requirements in `_is_article_page`

**Missing articles:**

- Check if deny patterns are too restrictive
- Verify spider can follow category/section pages
- Look for pagination patterns

**Poor extraction quality:**

- Check if site requires JavaScript rendering
- Verify proxy configuration
- Adjust newspaper4k settings

**Getting blocked or rate limited:**

- Increase download delays to 3-5 seconds in project config
- Lower concurrent requests (2-3 instead of 4+)
- Parser automatically handles proxy escalation internally
- Monitor extraction success rates in logs

## Output Format

```json
{
  "url": "https://website.com/article-slug/",
  "title": "Article Title",
  "content": "Full article content...",
  "author": "Author Name",
  "published_date": "2025-07-13T10:30:00",
  "top_image": "https://website.com/image.jpg",
  "source": "website",
  "project": "ClientA",
  "scraped_at": "2025-07-13T15:45:00"
}
```

## What Claude Code Can Modify

**✅ Allowed:**

- `spiders/[domain].py` - Create domain-specific spiders
- `projects/[name]/config.yaml` - Project configurations
- `data/[domain]/` - Analysis and discovery data

**❌ Not Allowed:**

- `core/`, `utils/`, `bin/` directories
- `settings.py`, `scrapy.cfg`
- Framework code or base classes

## Development Process

1. **Analyze the specific site** - Don't assume patterns
2. **Write rules based on analysis** - Not generic templates
3. **Test discovery first** - Get URLs before parsing
4. **Add content parsing** - Use newspaper4k with proxies
5. **Validate quality** - Meet success criteria before scaling
6. **Use proxies always** - Especially for production crawling

The goal is reliable, quality article extraction at scale with proper proxy usage to avoid blocking.
