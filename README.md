# scrapai-cli

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites with multi-project isolation.

## For Claude Code Instances

**When asked to add any website, follow this systematic process:**

1. **Create/Select Project** → Determine which project this spider belongs to
2. **Analyze site structure** → Use inspector tool (handles JavaScript rendering internally)
3. **Check for sitemaps** → Determine spider strategy  
4. **Generate domain-specific spider** → Create custom extraction code in `spiders/` directory
5. **Test spider** → Verify extraction works for the project
6. **Run spider** → Collect articles with project isolation

**IMPORTANT:** 
- Don't use generic templates. Generate custom spider code based on actual site analysis.
- Always create spiders in the shared `spiders/` directory
- Use project system for client isolation and output organization

## Ideal User Flow

### **Perfect Single Request**
```
User: "Create a project called BrownU and add politifact.com to it"
```

**Claude Code automatically handles:**

1. **Creates the project first**
   ```bash
   ./scrapai projects create --name BrownU --spiders ""
   ```

2. **Analyzes the site structure**
   ```bash
   bin/inspector --url https://politifact.com
   ```

3. **Generates custom spider code**
   - Create `spiders/politifact.py` extending `BaseSpider`
   - Use real selectors from HTML analysis
   - Implement site-specific extraction logic
   - Save the working spider file

4. **Tests the spider**
   ```bash
   ./scrapai test --project BrownU politifact --limit 5
   ```

5. **Fixes any issues found during testing**
   - Update selectors if needed
   - Fix extraction logic
   - Re-test until working

6. **Adds spider to project config**
   - Edit `projects/BrownU/config.yaml`
   - Add `politifact` to the spiders list
   - Now project knows about the spider

7. **Provides ready-to-use commands**
   ```bash
   # Run 100 articles
   ./scrapai crawl --project BrownU politifact --limit 100
   
   # Run all articles
   ./scrapai crawl --project BrownU politifact
   ```

**Result:** Complete working solution from one request!

### **Alternative Flows**

**If user provides just URL:**
```
User: "Add https://politifact.com"
Claude: "Which project should this be added to? Or should I create a new project?"
```

**If user has existing project:**
```
User: "Add reuters.com to my ClientA project"
Claude: [Analyzes reuters.com → Creates spider → Tests → Ready to use]
```

## Quick Start

### 1. Setup Environment

```bash
# Activate virtual environment (ALWAYS use this in the repo)
source .venv/bin/activate  # Linux/Mac

# Install Playwright browsers (required for inspector)
playwright install

# Check available projects
./scrapai projects list
```

### 2. Project Management

**Create a new project:**
```bash
./scrapai projects create --name client-team-a --spiders politifact,snopes
```

**List all projects:**
```bash
./scrapai projects list
```

**Check project status:**
```bash
./scrapai projects status --project client-team-a
```

### 3. Add a Website - Proper Analysis Process

**Step 1: Analyze the actual page structure**
```bash
bin/inspector --url https://example.com
# Inspector automatically handles JavaScript rendering when needed
# Creates analysis files in data/[site]/analysis/
```

**Step 2: Generate domain-specific spider**
- Create spider in `spiders/` directory (shared across projects)
- Extend `BaseSpider` class for common functionality
- Use actual selectors found in HTML analysis
- Implement site-specific URL patterns and extraction logic

**Step 3: Add spider to project configuration**
```bash
# Spider is automatically available to all projects
# Configure which spiders each project uses in their config.yaml
```

### 4. Running Spiders

**Run a specific spider for a project:**
```bash
./scrapai crawl --project client-team-a politifact --limit 10
```

**Run all spiders for a project:**
```bash
./scrapai crawl-all --project client-team-a
```

**Test a spider:**
```bash
./scrapai test --project client-team-a politifact --limit 5
```

## Project Structure

```
scrapai-cli/
├── spiders/                            # Shared spider library
│   ├── __init__.py
│   ├── base_spider.py                  # Base class with common functionality
│   ├── politifact.py                   # Reusable spiders
│   └── snopes.py
├── projects/                           # Project instances (client isolation)
│   ├── client-team-a/
│   │   ├── config.yaml                 # Project configuration
│   │   ├── outputs/                    # Project-specific outputs
│   │   │   ├── politifact/
│   │   │   └── snopes/
│   │   └── logs/                       # Project-specific logs
│   ├── client-team-b/
│   │   ├── config.yaml
│   │   ├── outputs/
│   │   └── logs/
│   └── internal-research/
│       ├── config.yaml
│       ├── outputs/
│       └── logs/
├── core/                               # Analysis and project management
│   ├── project_manager.py              # Project creation and management
│   ├── config_loader.py                # YAML configuration handling
│   ├── sitemap.py                      # Sitemap discovery
│   ├── analyzer.py                     # Site structure analysis  
│   └── add_site.py                     # Automated workflow
├── utils/                              # Utilities (http, logging, etc.)
├── bin/                               # Analysis tools
├── settings.py                        # Default Scrapy configuration
├── scrapai                           # Enhanced CLI with project support
└── scrapy.cfg                        # Scrapy configuration
```

## Project Configuration

Each project has a `config.yaml` file:

```yaml
project_name: "client-team-a"
spiders:
  - politifact
  - snopes
  - factcheck_org
settings:
  download_delay: 2
  concurrent_requests: 4
  concurrent_requests_per_domain: 2
  robotstxt_obey: true
output_format: json
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

### Project Management
```bash
# Create project with spiders
./scrapai projects create --name BrownU --spiders politifact,snopes

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
./scrapai crawl --project client-team-a politifact --limit 100

# Run all project spiders
./scrapai crawl-all --project client-team-a

# Test spider
./scrapai test --project client-team-a politifact --limit 5
```

### Monitoring
```bash
# Project status
./scrapai status --project client-team-a

# View logs
./scrapai logs --project client-team-a
./scrapai logs --project client-team-a --spider politifact
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
  "source": "spider_name",
  "project": "client-team-a",
  "scraped_at": "2024-01-15T10:30:00"
}
```

## Claude Code Decision Process

```
User asks: "Create project X and add [website] to it"
│
├─ 1. CREATE PROJECT FIRST
│  └─ ./scrapai projects create --name X --spiders ""
│
├─ 2. ANALYZE WEBSITE STRUCTURE  
│  ├─ Run inspector: bin/inspector --url https://website.com
│  └─ Check for sitemaps with core/sitemap.py
│
├─ 3. WRITE CUSTOM SPIDER CODE
│  ├─ Create spiders/website.py extending BaseSpider
│  ├─ Use real selectors from HTML analysis  
│  ├─ Implement domain-specific extraction logic
│  └─ Save the working spider file
│
├─ 4. TEST THE SPIDER
│  ├─ ./scrapai test --project X website --limit 5
│  └─ Verify data extraction works correctly
│
├─ 5. FIX ANY ISSUES
│  ├─ Update selectors if extraction fails
│  ├─ Fix extraction logic problems
│  └─ Re-test until working properly
│
├─ 6. ADD SPIDER TO PROJECT CONFIG
│  ├─ Edit projects/X/config.yaml
│  ├─ Add "website" to spiders list  
│  └─ Now project can use the spider
│
└─ 7. PROVIDE USAGE COMMANDS
   ├─ ./scrapai crawl --project X website --limit 100
   └─ Ready for production use
```

## Benefits of Project System

### Code Reuse
- Write spider once in `spiders/`
- Use across multiple projects
- No duplicated code

### Client Isolation
- Separate outputs per project
- Independent configurations
- Isolated logging

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
- Create spider extending `BaseSpider`
- Use `self.create_item()` for standardized output
- Look for article containers, headlines, bylines
- Check for pagination and category pages  
- Analyze date formats and author attribution

### Sitemap vs Crawl Strategy
- **Sitemap Spider**: When site has comprehensive sitemaps
- **Crawl Spider**: When need to follow navigation links
- **Mixed Strategy**: Use both for maximum coverage

## Troubleshooting

### Project Issues
- **Project not found**: Use `./scrapai projects list` to check available projects
- **Spider not configured**: Check project's `config.yaml` file
- **No outputs**: Check `projects/[name]/outputs/` directory

### Spider Issues
- **No Articles Found**: Check selectors match actual page structure
- **Wrong Content Extracted**: Re-run inspector on sample articles
- **JavaScript-Heavy Sites**: Use BrowserClient for proper rendering

### Permission/Access
- **Spider not found**: Ensure spider exists in `spiders/` directory
- **Config errors**: Validate YAML syntax in project config
- **Output permission**: Check write access to project directories