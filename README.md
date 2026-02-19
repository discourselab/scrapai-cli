# ScrapAI

**scrapAI** (scrape-eye) -- AI-powered web scraping at scale. 540+ websites in production.

You say: *"Get me 100 international news articles from BBC News."*

An AI coding agent analyzes the site, generates extraction rules, tests them, and deploys a scraper -- all from that one sentence. No code to write, no selectors to maintain.

## What This Is

ScrapAI is an orchestration layer built on top of [Scrapy](https://scrapy.org/). It replaces per-site Python spider files with JSON configurations stored in a database. A single generic spider (`DatabaseSpider`) loads its rules from the database at runtime.

The key idea: **AI analyzes each website once and generates a JSON config. From that point on, everything is deterministic Scrapy -- no AI involved, no inference cost per page.**

Here's what an AI-generated spider config looks like:

```json
{
  "name": "oann_com",
  "source_url": "https://www.oann.com/",
  "allowed_domains": ["oann.com"],
  "start_urls": [
    "https://www.oann.com/",
    "https://www.oann.com/category/newsroom/",
    "https://www.oann.com/category/business/"
  ],
  "rules": [
    {
      "allow": ["/(newsroom|business|commentary)/[^/]+/?$"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/category/(newsroom|business|commentary)/?$"],
      "follow": true,
      "priority": 50
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
    "DOWNLOAD_DELAY": 2
  }
}
```

That's not a Python file. It's data. It lives in a SQLite/PostgreSQL database. Adding a new website means adding a new row, not writing new code.

## Architecture

```
You (plain English) → AI Agent → JSON config → Database → DatabaseSpider → Scrapy crawl
                       (once)                                               (forever)
```

**Core components:**

| Component | What it does |
|-----------|-------------|
| `scrapai` | CLI entry point -- setup, crawl, inspect, import, export, queue management |
| `spiders/database_spider.py` | Single generic spider that loads config from database at runtime |
| `core/models.py` | SQLAlchemy models -- `Spider`, `SpiderRule`, `SpiderSetting`, `ScrapedItem` |
| `core/extractors.py` | Extraction chain -- newspaper, trafilatura, custom CSS selectors, Playwright |
| `handlers/cloudflare_handler.py` | Cloudflare bypass with session persistence |
| `pipelines.py` | Scrapy pipeline -- batched database writes and JSONL export |
| `alembic/` | Database migrations |
| `airflow/` | Production orchestration -- scheduling, monitoring, retry logic |

**Extraction pipeline:** Each article passes through a chain of extractors in order. Newspaper and trafilatura handle most sites. If they fail, custom CSS selectors kick in. If the site needs JavaScript rendering, Playwright loads the page first. Output is always the same schema: `url`, `title`, `content`, `author`, `published_date`, `source`.

**Storage modes:**
- **Test mode** (`--limit N`) -- saves to database for inspection via `show` command
- **Production mode** (no limit) -- exports to timestamped JSONL files, skips database

## Quick Start

**Requirements:** Python 3.9+, Git. No database installation needed.

```bash
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli
./scrapai setup
./scrapai verify
```

`./scrapai setup` creates the virtual environment, installs dependencies, initializes SQLite, and configures permissions. One command.

### Using with an AI agent

We recommend **[Claude Code](https://claude.ai/code)**. It reads `CLAUDE.md` automatically and knows the full workflow.

```bash
claude
```

Then talk to it in plain English:

```
You: "Add https://bbc.com to my news project"
Agent: [Analyzes site, generates rules, tests extraction, deploys spider]

You: "Run a test crawl on BBC, just grab 10 articles"
Agent: [Runs spider, shows you the results]

You: "Export everything from BBC as a CSV"
Agent: [Exports structured data to file]
```

You can also say things like:
- *"Create a new project called climate-research and add these 3 sites"*
- *"Here's a CSV with 200 websites, add them all to the queue"*
- *"Show me what we got from Reuters"*
- *"Process the next 5 websites in the queue"*

No Scrapy knowledge required. The agent handles all CLI commands, spider configuration, testing, and deployment.

### Other supported agents

ScrapAI is agent-agnostic:
- **Cursor** -- open the repo and start chatting. Reads `CLAUDE.md` for instructions.
- **Antigravity (Gemini)** -- see `.agent/rules/gemini.md` for setup.

### Manual usage (no AI agent)

You can also create spider configs by hand and use the CLI directly:

```bash
# Import a spider config
./scrapai spiders import spider.json --project myproject

# Test crawl (saves to database)
./scrapai crawl myspider --project myproject --limit 10

# View results
./scrapai show myspider --project myproject

# Production crawl (exports to JSONL)
./scrapai crawl myspider --project myproject

# Export as CSV
./scrapai export myspider --project myproject --format csv
```

## CLI Reference

```bash
# Setup
./scrapai setup                                          # Install everything
./scrapai verify                                         # Check environment

# Projects
./scrapai projects list                                  # List all projects

# Spiders
./scrapai spiders list --project <name>                  # List spiders
./scrapai spiders import <file.json> --project <name>    # Import/update spider
./scrapai spiders delete <name> --project <name>         # Delete spider

# Crawling
./scrapai crawl <spider> --project <name> --limit 5      # Test mode
./scrapai crawl <spider> --project <name>                 # Production mode

# Data
./scrapai show <spider> --project <name>                  # View articles
./scrapai export <spider> --project <name> --format csv   # Export (csv/json/jsonl/parquet)

# Queue (batch processing)
./scrapai queue add <url> --project <name>                # Add single site
./scrapai queue bulk <file.csv> --project <name>          # Bulk add from file
./scrapai queue list --project <name>                     # View queue
./scrapai queue next --project <name>                     # Claim next item

# Inspection
./scrapai inspect <url> --project <name>                  # Fetch and save page HTML

# Database
./scrapai db migrate                                      # Run migrations
./scrapai db current                                      # Show migration version
```

`--project` is required on all spider, queue, crawl, show, and export commands.

## Queue System

For batch processing, ScrapAI has a database-backed queue with atomic locking:

```bash
# Add 200 sites from a CSV
./scrapai queue bulk sites.csv --project research

# Process them -- the AI agent handles the rest
# With Claude Code, it processes 5 sites in parallel per batch
```

Queue tracks status (pending/processing/completed/failed), supports priorities, retry on failure, and bulk cleanup.

## Production Deployment

For running spiders on a schedule, ScrapAI includes Apache Airflow integration:

```bash
docker-compose -f docker-compose.airflow.yml up -d
# Access UI at http://localhost:8080
# Spiders auto-appear as DAGs, named {project}_{spider}
```

Includes scheduling (cron), monitoring, retry logic, S3-compatible storage upload, and role-based access control.

## Who Uses This

- **Researchers** -- collect structured data from hundreds of sources without writing code
- **Journalists** -- monitor news outlets, government websites, public records at scale
- **Threat intelligence teams** -- monitor forums and fringe websites; analysts work with organized data instead of scrolling raw content
- **Competitive intelligence** -- track competitor websites, pricing, product launches across industries
- **Compliance teams** -- monitor regulatory bodies and government websites for changes

## Known Limitations

- **Text-only extraction** -- currently extracts title, author, date, and body text. Full HTML is saved, so adding image/video/table extraction requires minimal code changes.
- **Website redesigns** -- when sites change their layout, rules need regeneration. Re-analysis takes 1-2 minutes per site.

## Documentation

| Doc | What it covers |
|-----|---------------|
| [docs/onboarding.md](docs/onboarding.md) | Detailed setup, troubleshooting, PostgreSQL upgrade |
| [docs/analysis-workflow.md](docs/analysis-workflow.md) | 4-phase workflow: inspect, analyze, generate rules, test, deploy |
| [docs/extractors.md](docs/extractors.md) | Extraction chain, custom selectors, Playwright, infinite scroll |
| [docs/cloudflare.md](docs/cloudflare.md) | Cloudflare bypass and session persistence |
| [docs/queue.md](docs/queue.md) | Queue system for batch processing |
| [docs/projects.md](docs/projects.md) | Project isolation and organization |
| [CLAUDE.md](CLAUDE.md) | Full AI agent instructions (auto-loaded by Claude Code) |

## Contributing

Contributions welcome, particularly in:

- Automatic detection of website structural changes
- JavaScript rendering strategies
- Error recovery and retry logic
- Additional extraction modules for media types

## License

[AGPL-3.0](LICENSE) -- See LICENSE file for details.

Commercial licenses available for organizations that cannot comply with AGPL v3. Contact info@discourselab.ai.
