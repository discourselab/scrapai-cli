# ScrapAI

**scrapAI** (scrape-eye) -- AI-powered web scraping at scale. Battle-tested on hundreds of production websites.

You say: *"Get me 100 international news articles from BBC News."*

An AI coding agent analyzes the site, generates extraction rules, tests them, and deploys a scraper -- all from that one sentence. No code to write, no selectors to maintain.

## What This Is

ScrapAI is an orchestration layer built on top of [Scrapy](https://scrapy.org/). It replaces per-site Python spider files with JSON configurations stored in a database. A single generic spider (`DatabaseSpider`) loads its rules from the database at runtime.

The key idea: **AI analyzes each website once and generates a JSON config. From that point on, everything is deterministic Scrapy -- no AI involved, no inference cost per page.**

Here's what an AI-generated spider config looks like:

```json
{
  "name": "bbc_co_uk",
  "source_url": "https://www.bbc.co.uk/",
  "allowed_domains": ["bbc.co.uk"],
  "start_urls": [
    "https://www.bbc.co.uk/",
    "https://www.bbc.co.uk/news",
    "https://www.bbc.co.uk/business"
  ],
  "rules": [
    {
      "allow": ["/news/articles/[^/]+$", "/business/articles/[^/]+$"],
      "callback": "parse_article",
      "follow": false,
      "priority": 100
    },
    {
      "allow": ["/news/?$", "/business/?$"],
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

## Why ScrapAI?

**The problem with traditional scraping:**
- 100 websites = 100 custom Python scripts to write and maintain
- Websites change layouts → developers manually fix each broken script
- Human inconsistency grows with volume (different field names, conventions, quality)
- Per-page AI services ($$$) or rebuild scrapers repeatedly

**ScrapAI's approach:**
- **AI once, code forever** — AI analyzes site and writes JSON config (stored in database), then deterministic Scrapy executes (no AI cost per page)
- **Database-first** — Spiders are data rows, not code files. 100 websites = 100 rows. Query, update, audit your entire operation.
- **Self-hosted** — Own your infrastructure. No per-page API costs. Works with SQLite (local) or PostgreSQL (production).
- **Production-ready** — Checkpoint pause/resume, smart proxy management, Cloudflare bypass, queue system for batch processing

**Economics:**
- Traditional: Developer time per site + ongoing maintenance
- AI APIs: Low setup cost + expensive per-page scaling
- ScrapAI: One-time AI setup + cheap deterministic execution at any scale

**Built for scale:**
- 10 websites: convenience
- 100 websites: competitive advantage
- 1000 websites: different category of capability

## Key Features

### 🚀 Production-Ready Infrastructure

**Cloudflare Bypass (Hybrid Mode)**
- Most scrapers fail on Cloudflare or render every page (slow, expensive, 2-5 seconds per page)
- ScrapAI solves the browser once per 10 minutes, caches session cookies
- Then makes fast HTTP requests with those cookies -- same speed as non-Cloudflare sites
- 16 concurrent requests, hundreds of pages per minute (20-100x faster than browser-only)
- Works on Linux servers (VPS) - auto-detects missing display and uses Xvfb (virtual display)

**Checkpoint Pause/Resume**
- Long crawls (hours/days) can be paused with Ctrl+C and resumed later
- Automatic checkpoint on production crawls
- No progress lost on crashes or interruptions
- Built on Scrapy's native JOBDIR support

**SmartProxyMiddleware with Expert-in-the-Loop**
- Starts with direct connections (fast, free)
- Automatically retries with datacenter proxy when blocked (403/429)
- Learns which domains need proxies
- **Expert-in-the-loop cost control:** Residential proxies require explicit approval
- No surprise costs -- expensive proxies need human opt-in

**Incremental Crawling (DeltaFetch)**
- Only scrapes new/changed pages
- Skips already-scraped URLs
- Can reduce bandwidth and time by 80-90% for routine monitoring
- Perfect for daily/weekly re-crawls of the same sites

**S3 Object Storage (Optional)**
- Upload to S3-compatible storage (Hetzner, AWS S3, DigitalOcean Spaces, etc.)
- Configure in `.env` to enable automatic uploads
- Background uploads after crawl completes
- Perfect for backup, archiving, and multi-system access
- Works with Airflow workflows

### 🎯 Smart Extraction

**Multi-Extractor Pipeline**
- newspaper and trafilatura handle most sites (generic extractors)
- Custom CSS selectors for sites with unique layouts
- Playwright for JavaScript-rendered content
- Infinite scroll support for dynamic pages
- Always outputs same schema: url, title, content, author, date, source

**Sitemap Support**
- Fast crawling for sites with XML sitemaps
- Automatically discovers all content pages
- No URL pattern rules needed
- Perfect for blogs, news sites, documentation

### 📊 Batch Processing

**Queue System**
- Database-backed queue with atomic locking
- Process hundreds of sites in parallel
- Priority support, retry on failure, bulk operations
- Track status: pending → processing → completed/failed

**Airflow Integration**
- Production orchestration and scheduling
- Spiders auto-appear as DAGs
- Monitoring and retry logic
- Role-based access control

## Architecture

```
You (plain English) → AI Agent → JSON config → Database → DatabaseSpider → Scrapy crawl
                       (once)                                               (forever)
```

**Design principle: Separation of concerns**

ScrapAI has a clean separation between orchestration and implementation:

- **AI Agent (Claude Code):** Knows WHAT CLI command to run WHEN. Handles workflow orchestration, decides which commands to execute based on user intent. Doesn't need to understand how commands work internally.

- **Developers (Us):** Ensure CLI commands actually WORK. Handle implementation details, edge cases, database logic, Python code. The CLI is the contract.

This separation means:
- ✅ CLAUDE.md stays concise (~370 lines) - just orchestration logic
- ✅ AI can't break Python code - it only calls CLI commands
- ✅ You can refactor internals freely - as long as CLI interface stays consistent
- ✅ AI is powerful without knowing implementation details

**Core components:**

| Component | What it does |
|-----------|-------------|
| `scrapai` | Entry point -- auto-activates venv, delegates to `cli/` |
| `cli/` | Click-based CLI modules -- spiders, queue, crawl, show, export, inspect, etc. |
| `spiders/database_spider.py` | Generic spider that loads config from database at runtime |
| `spiders/sitemap_spider.py` | Sitemap-based spider for sites with XML sitemaps |
| `spiders/base.py` | Shared mixin -- settings loading, CF setup, article extraction |
| `core/models.py` | SQLAlchemy models -- `Spider`, `SpiderRule`, `SpiderSetting`, `ScrapedItem` |
| `core/extractors.py` | Extraction chain -- newspaper, trafilatura, custom CSS selectors, Playwright |
| `handlers/cloudflare_handler.py` | Cloudflare bypass with session persistence |
| `middlewares.py` | SmartProxyMiddleware with expert-in-the-loop cost control |
| `pipelines.py` | Scrapy pipeline -- batched database writes and JSONL export |
| `bin/parallel-crawl` | GNU parallel wrapper for running multiple spiders concurrently |
| `alembic/` | Database migrations |
| `airflow/` | Production orchestration -- scheduling, monitoring, retry logic |

**Extraction pipeline:** Each article passes through a chain of extractors in order. Newspaper and trafilatura handle most sites. If they fail, custom CSS selectors kick in. If the site needs JavaScript rendering, Playwright loads the page first. Output is always the same schema: `url`, `title`, `content`, `author`, `published_date`, `source`.

**Storage modes:**
- **Test mode** (`--limit N`) -- saves to database for inspection via `show` command
- **Production mode** (no limit) -- exports to timestamped JSONL files, skips database, enables checkpoint

## Quick Start

**Requirements:** Python 3.9+, Git. No database installation needed.

```bash
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli
./scrapai setup
./scrapai verify
```

`./scrapai setup` creates the virtual environment, installs dependencies (including Playwright browser drivers), initializes SQLite, and configures permissions. One command.

**Switching to PostgreSQL:** Update `DATABASE_URL` in `.env` to PostgreSQL, run `./scrapai db migrate` to initialize schema, then `./scrapai db transfer sqlite:///scrapai.db` to migrate your existing data. PostgreSQL handles concurrent writes better and scales to millions of scraped items.

### Using with an AI agent

We recommend **[Claude Code](https://claude.ai/code)** for several reasons:

1. **Reads `CLAUDE.md` automatically** - Contains the complete 4-phase workflow and all operational knowledge
2. **Protected framework** - `./scrapai setup` configures `.claude/settings.local.json` with permission rules that block Python file modifications at the tool level. Agents can only work with JSON configs and CLI commands - they cannot modify core code (spiders, pipelines, extractors, handlers).
3. **Why this matters:** AI agents are powerful but can break production systems if they modify framework code. ScrapAI's architecture keeps agents at the data layer (JSON configs) while the framework code (Python) remains stable and tested.

**Token-efficient & scales with subagents:**

CLAUDE.md is deliberately concise (currently ~370 lines). Agent can complete most tasks from CLAUDE.md alone, only reading detailed docs (extractors.md, cloudflare.md) when needed. This keeps context small and API costs low.

**The real advantage: subagent parallelization.** Claude Code uses a main orchestrator agent + worker subagents for batch processing. Each subagent handles one website (3-6 minutes per site), processes in parallel, then reports back to main agent with just a summary.

**Context window impact:**
- **Without subagents:** Processing 5-8 websites fills context → conversation compaction required → lose detailed history
- **With subagents:** We've processed 40+ websites in one queue without compaction. Main agent only stores summaries, not full spider analysis details.

Real example: Queue of 40 news sites → main agent spawns subagents → they work in parallel → main agent gets "spider X completed" updates → no context bloat.

**Why CLAUDE.md should stay small:** Each subagent loads CLAUDE.md when initialized. Creating 5 parallel subagents = 5 CLAUDE.md reads. Keeping it concise (vs thousands of lines) means lower cost per subagent and more context space left for actual work.

**Cost tradeoff:** Subagents have upfront token cost (each reads CLAUDE.md), but parallel processing is much faster and avoids context compaction. For batch jobs, the speed and scalability benefits outweigh the initial cost.

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

### Other AI coding agents

Works with OpenCode, Cursor, Antigravity (Gemini), and other AI coding agents via `Agents.md`.

**Warning:** These agents lack Claude Code's permission enforcement and may modify framework code. Review all changes carefully.

### Manual usage (no AI agent)

You can also create spider configs by hand and use the CLI directly:

```bash
# Import a spider config
./scrapai spiders import spider.json --project myproject

# Test crawl (saves to database)
./scrapai crawl myspider --project myproject --limit 10

# View results
./scrapai show myspider --project myproject

# Production crawl (exports to JSONL, enables checkpoint)
./scrapai crawl myspider --project myproject

# Press Ctrl+C to pause, run same command to resume

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
./scrapai crawl <spider> --project <name> --limit 5      # Test mode (no checkpoint)
./scrapai crawl <spider> --project <name>                # Production (checkpoint enabled)
./scrapai crawl <spider> --project <name> --proxy-type residential  # Force residential proxy

# Proxy modes: auto (default), datacenter, residential
# Auto mode: Direct → Datacenter → Expert prompt for residential

# Data
./scrapai show <spider> --project <name>                  # View articles
./scrapai export <spider> --project <name> --format csv   # Export (csv/json/jsonl/parquet)

# Queue (batch processing)
./scrapai queue add <url> --project <name>                # Add single site
./scrapai queue bulk <file.csv> --project <name>          # Bulk add from file
./scrapai queue list --project <name>                     # View queue
./scrapai queue next --project <name>                     # Claim next item

# Inspection (smart resource usage)
./scrapai inspect <url> --project <name>                  # Lightweight HTTP (default, fast)
./scrapai inspect <url> --project <name> --browser        # Browser for JS sites
./scrapai inspect <url> --project <name> --cloudflare     # Cloudflare bypass

# Database
./scrapai db migrate                                      # Run migrations
./scrapai db current                                      # Show migration version
./scrapai db transfer sqlite:///scrapai.db               # Transfer data from SQLite to PostgreSQL (set DATABASE_URL first)
./scrapai db stats                                        # Show database statistics
./scrapai db tables                                       # List all tables with row counts
./scrapai db inspect spiders                              # Show schema for specific table
./scrapai db query "SELECT * FROM spiders LIMIT 5"       # Read-only SQL queries (supports --format json/csv)

# Parallel crawling (requires GNU parallel)
bin/parallel-crawl <project>                              # All spiders in project
bin/parallel-crawl <project> spider1 spider2              # Selected spiders
```

`--project` is required on all spider, queue, crawl, show, and export commands.

## Configuration

Create `.env` in project root (see `.env.example`):

```bash
# Data directory (default: ./data)
# Store on cheaper spinning disk if you have large crawls
DATA_DIR=./data

# Database (default: SQLite)
DATABASE_URL=sqlite:///scrapai.db
# For production: postgresql://user:password@localhost:5432/scrapai

# Proxy (SmartProxyMiddleware)
DATACENTER_PROXY_USERNAME=your_username
DATACENTER_PROXY_PASSWORD=your_password
DATACENTER_PROXY_HOST=dc.decodo.com
DATACENTER_PROXY_PORT=10000  # Rotating datacenter IPs

RESIDENTIAL_PROXY_USERNAME=your_username
RESIDENTIAL_PROXY_PASSWORD=your_password
RESIDENTIAL_PROXY_HOST=gate.decodo.com
RESIDENTIAL_PROXY_PORT=7000  # Rotating residential IPs

# S3-Compatible Object Storage (optional)
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_ENDPOINT=https://fsn1.your-objectstorage.com
S3_BUCKET=scrapai-crawls
```

## Queue System

For batch processing, ScrapAI has a database-backed queue with atomic locking:

```bash
# Add 200 sites from a CSV
./scrapai queue bulk sites.csv --project research

# Process them -- the AI agent handles the rest
# With Claude Code, it processes 5-10 sites in parallel per batch
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

## Use Cases

- **Media monitoring** -- track news articles, blog posts, and announcements across hundreds of public sources
- **Threat intelligence** -- monitor underground forums and threat actor sites without exposing analysts to malware, exploits, or illegal content; automated scraping from isolated environments delivers clean, structured data for analysis
- **Price monitoring, competitive intelligence, content aggregation, and many more**

## What It Doesn't Do (Yet)

We built ScrapAI to solve article scraping - news sites, blogs, research papers, documentation. It works well for this use case. But there's a lot we haven't tackled yet.

**Not currently supported:**

**Authentication & Sessions:**
- ❌ Login-required content (username/password, MFA/2FA)
- ❌ Paywall bypass
- ❌ Persistent browser sessions across crawls
- ❌ Cookie consent/GDPR banner handling

**Advanced Anti-Bot:**
- ✅ Cloudflare (we handle this)
- ❌ DataDome, PerimeterX, Akamai, custom anti-bot systems

**Interactive Content:**
- ❌ Form submission and complex UI interaction
- ❌ Click-based pagination and navigation flows

**Content Types:**
- ✅ Text extraction (title, author, date, body text)
- ❌ Images, tables, PDFs as structured data
- ❌ Real-time feeds (WebSocket/SSE)

**Important:** We already **capture full HTML** for every page. The limitation is in the **parsing/extraction layer**, not data collection. Images, tables, and embedded content are in the saved HTML - we just don't extract them as structured data yet.

**Extending ScrapAI:**

The framework is small (~4,600 lines) and designed to be extended:

- **Image extraction?** Add an extractor to `core/extractors.py` that parses `<img>` tags
- **Table parsing?** Extend the extraction chain for `<table>` elements
- **E-commerce scraping?** Build extractors for product data
- **Login support?** Add session management to `handlers/`

The hard part (crawling infrastructure) is done. What's missing is mostly parsing logic.

If you build something useful, we'd love to see it. Pull requests welcome - if it's well-tested and helps others, we'll merge it.

**Currently works great for:** News sites, blogs, research papers, documentation, government websites, public content archives.

## Documentation

| Doc | What it covers |
|-----|---------------|
| [docs/onboarding.md](docs/onboarding.md) | Detailed setup, troubleshooting, PostgreSQL upgrade |
| [docs/analysis-workflow.md](docs/analysis-workflow.md) | 4-phase workflow: inspect, analyze, generate rules, test, deploy |
| [docs/extractors.md](docs/extractors.md) | Extraction chain, custom selectors, Playwright, infinite scroll |
| [docs/cloudflare.md](docs/cloudflare.md) | Cloudflare bypass and session persistence (hybrid mode) |
| [docs/checkpoint.md](docs/checkpoint.md) | Pause/resume support for long-running crawls |
| [docs/proxies.md](docs/proxies.md) | SmartProxyMiddleware with expert-in-the-loop cost control |
| [docs/s3.md](docs/s3.md) | S3-compatible object storage for backup and archiving |
| [docs/deltafetch.md](docs/deltafetch.md) | Incremental crawling (only scrape new/changed pages) |
| [docs/queue.md](docs/queue.md) | Queue system for batch processing hundreds of sites |
| [docs/sitemap.md](docs/sitemap.md) | Sitemap spider setup and usage |
| [docs/projects.md](docs/projects.md) | Project isolation and organization |
| [CLAUDE.md](CLAUDE.md) | Full AI agent instructions (auto-loaded by Claude Code) |

## Security

Found a security vulnerability? Please see our [Security Policy](SECURITY.md) for responsible disclosure guidelines.

**Do not report security issues through public GitHub issues.** Email: dev@discourselab.ai

## Contributing

Contributions welcome, particularly in:

- Automatic detection of website structural changes
- JavaScript rendering strategies
- Error recovery and retry logic
- Additional extraction modules for media types
- Expert-in-the-loop patterns for other cost/risk decisions

## License

[AGPL-3.0](LICENSE) -- See LICENSE file for details.

Commercial licenses available for organizations that cannot comply with AGPL v3. Contact info@discourselab.ai.
