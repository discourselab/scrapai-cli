# ScrapAI

A CLI where you describe what you want to scrape in plain English, an AI agent builds the scraper, and [Scrapy](https://scrapy.org/) runs it.

```
You: "Add https://bbc.co.uk to my news project"
```

Minutes later you have a tested, production-ready scraper stored in a database. No Python, no CSS selectors, no Scrapy knowledge. The AI agent analyzes the site, writes extraction rules, verifies quality, and saves a reusable config. Run it tomorrow or next year. Same command, no AI costs.

Built by [DiscourseLab](https://www.discourselab.ai/). Used in production across 500+ websites.

## Who This Is For

**Good fit:**
- Teams that need to scrape many websites and don't want to write individual scrapers
- Non-technical users who can describe what they want in plain English
- Organizations where scraping is a means to an end, not the core competency
- Anyone building datasets from public web content (news, research, documentation)

**Not a good fit:**
- Single-site scraping where you want fine-grained control (use [Scrapling](https://github.com/D4Vinci/Scrapling) or [crawl4ai](https://github.com/unclecode/crawl4ai))
- Sites with hard CAPTCHAs (we handle Cloudflare challenges, not Capsolver-level CAPTCHAs)
- Login-required or paywall content (not supported yet)

See [COMPARISON.md](COMPARISON.md) for a detailed comparison with Scrapling and crawl4ai.

## Why ScrapAI?

We needed data for our work. Hundreds of websites, scraped regularly, structured consistently. We got sick of building and maintaining fleets of scrapers.

There are great crawling frameworks out there. [Scrapy](https://scrapy.org/), [crawl4ai](https://github.com/unclecode/crawl4ai), and [Scrapling](https://github.com/D4Vinci/Scrapling) are our favourites, and ScrapAI is built on top of Scrapy. But even with great frameworks, you hit a wall at scale. You still need to write code for every site, monitor for breakage, and fix things when layouts change. 10 scrapers is fine. 100 is a full-time job. 500 is a team.

We looked at three options:

**Option 1: Web scraping services.** They charge per page, per request, or per API call. Fine for small volumes, but at scale the bills get serious. Stop paying, lose access.

**Option 2: AI-powered scraping with LLMs at runtime.** Call an LLM on every page to extract data. Clever, but the cost scales linearly with volume. 10,000 pages means 10,000 inference calls. That's wasteful for what is ultimately a pattern-matching problem.

**Option 3: AI once, deterministic forever.** Use AI at build time to analyze the site and write extraction rules. Then run those rules with Scrapy: no AI in the loop, no per-page costs. The cost is per *website*, not per page. After that, you own the scraper and run it as many times as you want.

We chose option 3. That's ScrapAI.

**Self-hosted, no vendor lock-in.** You clone the repo, you own everything. No SaaS, no subscription, no per-page billing. Your scrapers are JSON configs in a database. Export them, share them, move them between projects.

## How It Works

ScrapAI is an orchestration layer on top of Scrapy. Instead of writing a Python spider file per website, an AI agent generates a JSON config and stores it in a database. A single generic spider (`DatabaseSpider`) loads any config at runtime.

```
You (plain English) → AI Agent → JSON config → Database → Scrapy crawl
                       (once)                               (forever)
```

**Why JSON configs instead of AI-generated Python?** An agent that writes and executes Python has the same power as an unsupervised developer. If it hallucinates, gets prompt-injected by a malicious page, or loses context, it can do real damage. An agent that writes JSON configs produces data, not code. That data goes through strict validation (Pydantic schemas, SSRF checks, reserved name blocking) before it reaches the database. The worst case is a bad config that extracts wrong fields, caught in the test crawl and trivially fixable. See [Security](#security) for the full picture.

Here's what an AI-generated spider config looks like:

```json
{
  "name": "bbc_co_uk",
  "allowed_domains": ["bbc.co.uk"],
  "start_urls": ["https://www.bbc.co.uk/news"],
  "rules": [
    {
      "allow": ["/news/articles/[^/]+$"],
      "callback": "parse_article",
      "follow": false
    },
    {
      "allow": ["/news/?$"],
      "follow": true
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
    "DOWNLOAD_DELAY": 2
  }
}
```

Adding a new website means adding a new row.

### What's Under the Hood

ScrapAI is glue. These projects do the heavy lifting:

- **[Scrapy](https://scrapy.org/)** for crawling. Everything runs through Scrapy; we just load configs from a database instead of Python files.
- **[newspaper4k](https://github.com/AndyTheFactory/newspaper4k)** and **[trafilatura](https://github.com/adbar/trafilatura)** for article extraction (title, content, author, date). For non-article content (products, jobs, listings), the agent writes custom callbacks with CSS/XPath selectors and data processors.
- **[nodriver](https://github.com/ultrafunkamsterdam/nodriver)** for Cloudflare bypass via browser automation.
- **[Playwright](https://playwright.dev/)** for JavaScript rendering.
- **[SQLAlchemy](https://www.sqlalchemy.org/)** and **[Alembic](https://alembic.sqlalchemy.org/)** for the database layer and migrations.

Our contribution is the orchestration: the CLI, the database-first spider management, the AI agent workflow, Cloudflare cookie caching, smart proxy escalation, and the glue that holds it together.

## Features

**Cloudflare bypass with cookie caching.** Solves the challenge once, extracts session cookies, then switches to fast HTTP requests. The browser shuts down and only comes back every 10 minutes to refresh. Most tools keep the browser open for every request (~5-10s per page). On a 1,000-page Cloudflare-protected crawl, that's roughly 8 minutes vs 2+ hours. Works on headless Linux servers (auto-configures Xvfb).

**Smart proxy escalation.** Starts with direct connections. If a site blocks you (403/429), retries through a datacenter proxy and remembers that domain for next time. Residential proxies require explicit opt-in.

**Checkpoint pause/resume.** Press Ctrl+C to pause a long crawl, run the same command to resume. Built on Scrapy's native JOBDIR. No progress lost.

**Incremental crawling.** DeltaFetch skips already-scraped URLs, reducing bandwidth by 80-90% on routine re-crawls.

**Targeted extraction.** Articles get clean structured fields (title, content, author, date) via newspaper and trafilatura. Non-article content (products, jobs, listings) gets custom callbacks with field-level selectors and data processors. The output is structured data, not a page dump.

**Database-first management.** Spiders are rows in a database, not Python files on disk. Need to change `DOWNLOAD_DELAY` across your whole fleet? One SQL query instead of editing 100 files. Export a spider config as JSON, import it into another project. No code drift, no style inconsistencies.

**Queue and batch processing.** Bulk-add hundreds of URLs into a database-backed queue with priorities, status tracking, and retry on failure. The agent processes them in parallel batches of 5, each through the full build-test-deploy workflow.

**Low-maintenance at scale.** Every spider comes with a test config (5 sample URLs). Set up a cron job to run test crawls monthly and you'll know which spiders are healthy and which broke. When a site redesign breaks extraction, point the agent at the failing spider. It re-analyzes the site, updates the config, and verifies the fix.

## Quick Start

**Requirements:** Python 3.9+, Git

**Supported platforms:** Linux, macOS, Windows

```bash
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli
./scrapai setup
./scrapai verify
```

`./scrapai setup` creates the virtual environment, installs dependencies (including browser drivers), initializes SQLite, and configures permissions. One command, about 2 minutes.

**Manual usage:**

```bash
./scrapai spiders import spider.json --project myproject
./scrapai crawl myspider --project myproject --limit 10
./scrapai show myspider --project myproject
./scrapai export myspider --project myproject --format csv
```

### Using with AI Agents

ScrapAI is designed to work with AI coding agents. The agent reads the workflow instructions, analyzes websites, and produces JSON configs through the CLI.

**Claude Code** is what we use and test with. `CLAUDE.md` contains the complete 4-phase workflow, and `./scrapai setup` configures permission rules that block the agent from modifying framework code. The full agent instructions fit in ~5k tokens. Additional docs (Cloudflare, proxies, callbacks, etc.) are loaded only when needed, not upfront. Most of the context window goes to actual site analysis, not reading a manual.

```bash
claude
```

```
You: "Add https://bbc.com to my news project"
Agent: [Analyzes site, generates rules, tests extraction, deploys spider]

You: "Here's a CSV with 200 websites, add them all to the queue"
Agent: [Queues them, processes in parallel batches]
```

**Other coding agents** (OpenCode, Cursor, Antigravity, etc.) should work with any agent that can read instructions and run shell commands. An `Agents.md` file is included. These agents lack Claude Code's permission enforcement, so review changes carefully.

**Claws.** ScrapAI works with any Claw that can read instructions and execute shell commands. We tested with [NanoClaw](https://github.com/qwibitai/nanoclaw) for autonomous operation via Telegram. More rigorous testing is in progress, and we're excited to try other Claws like PicoClaw, IronClaw, and Nanobot. See [Security](#security) for how the architecture keeps agents safe.

### Migrating Existing Scrapers

Point the agent at your existing Python scripts (Scrapy spiders, BeautifulSoup, Scrapling, whatever) and it'll read them, understand the extraction logic, and write the equivalent ScrapAI JSON config.

```
You: "Migrate my spider at scripts/bbc_spider.py to ScrapAI"
Agent: [Reads Python, extracts URL patterns and selectors, writes JSON config, tests, saves to database]
```

Your existing scrapers keep running while you verify. No big bang migration required.

## For Developers

ScrapAI doesn't replace developers. It removes the repetitive parts so you can focus on the hard problems.

**You're always in the loop.** The agent doesn't just run off and do things. During site analysis, it writes detailed notes in `sections.md`: what URL patterns it found, what sections the site has, what extraction strategy it chose and why. Plain language, easy to read. You can review at any point, correct the agent's assumptions, and bring your expertise into the process.

**Hand-write, edit, or override anything.** Write your own JSON configs from scratch. Edit AI-generated ones. Override settings per spider. Write custom callbacks with your own CSS/XPath selectors and data processors. `./scrapai spiders import my_config.json` works the same whether a human or an agent wrote it. The AI is a tool in your workflow, not a replacement for it.

**Consistency across the fleet.** When 5 developers write 100 spiders, you get 5 different styles, naming conventions, and quality levels. ScrapAI produces uniform configs with the same schema, validation, and structure. Easier to review, easier to debug, easier to onboard new people.

**Small, readable codebase.** ~4,000 lines of code (vs ~6,000 for Scrapling and ~27,000 for crawl4ai). Built on Scrapy, SQLAlchemy, Alembic — tools you already know. Read the whole thing in an afternoon. Easy to extend, easy to contribute to.

## Architecture

| Component | What it does |
|-----------|-------------|
| `scrapai` | Entry point, auto-activates venv, delegates to CLI |
| `cli/` | Click-based CLI: spiders, queue, crawl, show, export, inspect |
| `spiders/database_spider.py` | Generic spider that loads config from database at runtime |
| `spiders/sitemap_spider.py` | Sitemap-based spider for sites with XML sitemaps |
| `core/extractors.py` | Extraction chain: newspaper, trafilatura, custom CSS, Playwright |
| `core/models.py` | SQLAlchemy models: Spider, SpiderRule, SpiderSetting, ScrapedItem |
| `handlers/cloudflare_handler.py` | Cloudflare bypass with cookie caching |
| `middlewares.py` | SmartProxyMiddleware, direct-to-proxy escalation |
| `pipelines.py` | Batched database writes and JSONL export |
| `alembic/` | Database migrations |
| `airflow/` | Production scheduling with Apache Airflow |

**Storage modes:**
- **Test mode** (`--limit N`): saves to database, inspect via `show` command
- **Production mode** (no limit): exports to timestamped JSONL files, enables checkpoint

## Security

All input is validated through [Pydantic](https://docs.pydantic.dev/) schemas before it touches the database or the crawler:

- **Spider configs:** strict schema validation (`extra="forbid"`), spider names restricted to `^[a-zA-Z0-9_-]+$`, callback names validated with reserved names blocked
- **URLs:** HTTP/HTTPS only, private IP and localhost blocking (127.0.0.1, 10.x, 172.16.x, 192.168.x, 169.254.x), 2048-char limit
- **Settings:** whitelisted extractor names, bounded concurrency (1-32), bounded delays (0-60s)
- **SQL:** all queries through SQLAlchemy ORM with parameterized bindings; `db query` validates table names against a whitelist; UPDATE/DELETE require row count confirmation

### Agent Safety

When you pair an AI agent with a scraping framework, the agent can potentially modify code, run arbitrary commands, and interact with untrusted web content. This isn't theoretical. In February 2026, an [OpenClaw agent deleted 200+ emails](https://techcrunch.com/2026/02/23/a-meta-ai-security-researcher-said-an-openclaw-agent-ran-amok-on-her-inbox/) after context compaction caused it to lose safety constraints. Scraping makes this worse: every page you crawl is untrusted input that could contain prompt injections.

ScrapAI's approach: **the agent writes config, not code.**

- With Claude Code, permission rules block `Write(**/*.py)`, `Edit(**/*.py)`, and destructive shell commands at the tool level
- The agent interacts only through a defined CLI (`./scrapai inspect`, `./scrapai spiders import`, etc.)
- JSON configs are validated through Pydantic before import. Malformed configs, SSRF URLs, and injection attempts fail validation
- At runtime, Scrapy executes deterministically with no AI in the loop

The hard enforcement (allow/deny lists) is a Claude Code feature configured via `./scrapai setup`. Other agents get instructions but not enforcement. Only Claude Code guarantees the agent can't sidestep it. For autonomous operation, we pair this with NanoClaw's container isolation. See [COMPARISON.md](COMPARISON.md#ai-agents--scraping-the-security-question) for the full analysis.

Found a vulnerability? See [SECURITY.md](SECURITY.md). Do not use public GitHub issues.

## CLI Reference

`--project` is required on all spider, queue, crawl, show, and export commands.

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
./scrapai crawl <spider> --project <name>                # Production (checkpoint enabled)

# Data
./scrapai show <spider> --project <name>                 # View scraped items
./scrapai export <spider> --project <name> --format csv  # Export (csv/json/jsonl/parquet)

# Queue (batch processing)
./scrapai queue add <url> --project <name>               # Add single site
./scrapai queue bulk <file.csv> --project <name>         # Bulk add from file
./scrapai queue list --project <name>                    # View queue
./scrapai queue next --project <name>                    # Claim next item

# Inspection
./scrapai inspect <url> --project <name>                 # Lightweight HTTP (default)
./scrapai inspect <url> --project <name> --browser       # Browser for JS sites
./scrapai inspect <url> --project <name> --cloudflare    # Cloudflare bypass

# Database
./scrapai db migrate                                     # Run migrations
./scrapai db stats                                       # Show database statistics
./scrapai db query "SELECT * FROM spiders LIMIT 5"       # Read-only SQL queries

# Parallel crawling (requires GNU parallel)
bin/parallel-crawl <project>                             # All spiders in project
```

## Configuration

Create `.env` in project root (see `.env.example`):

```bash
# Data directory (default: ./data)
DATA_DIR=./data

# Database (default: SQLite, no installation needed)
DATABASE_URL=sqlite:///scrapai.db
# For production: postgresql://user:password@localhost:5432/scrapai

# Proxy (optional, any SOCKS5/HTTP proxy provider)
DATACENTER_PROXY_USERNAME=your_username
DATACENTER_PROXY_PASSWORD=your_password
DATACENTER_PROXY_HOST=your-datacenter-proxy.com
DATACENTER_PROXY_PORT=10000

RESIDENTIAL_PROXY_USERNAME=your_username
RESIDENTIAL_PROXY_PASSWORD=your_password
RESIDENTIAL_PROXY_HOST=your-residential-proxy.com
RESIDENTIAL_PROXY_PORT=7000

# S3-compatible storage (optional, for Airflow workflows)
S3_ENDPOINT=https://your-s3-endpoint.com
S3_BUCKET=scrapai-crawls
```

**Switching to PostgreSQL:** Update `DATABASE_URL` in `.env`, run `./scrapai db migrate`, then `./scrapai db transfer sqlite:///scrapai.db` to migrate existing data.

## Limitations

- **Authentication:** No login support, no paywall bypass, no persistent sessions
- **Advanced anti-bot:** We handle Cloudflare. Not DataDome, PerimeterX, Akamai, or CAPTCHA-solving services
- **Interactive content:** No form submission, no click-based pagination

The codebase is designed to be extended. The crawling infrastructure is done; what's missing is mostly parsing logic for additional content types. Pull requests are welcome.

## Documentation

| Doc | What it covers |
|-----|---------------|
| [docs/onboarding.md](docs/onboarding.md) | Setup, troubleshooting, PostgreSQL |
| [docs/analysis-workflow.md](docs/analysis-workflow.md) | 4-phase workflow for building spiders |
| [docs/extractors.md](docs/extractors.md) | Extraction chain, custom selectors, Playwright |
| [docs/cloudflare.md](docs/cloudflare.md) | Cloudflare bypass and cookie caching |
| [docs/callbacks.md](docs/callbacks.md) | Custom fields for non-article content |
| [docs/checkpoint.md](docs/checkpoint.md) | Pause/resume for long crawls |
| [docs/proxies.md](docs/proxies.md) | Smart proxy escalation |
| [docs/queue.md](docs/queue.md) | Batch processing |
| [docs/deltafetch.md](docs/deltafetch.md) | Incremental crawling |
| [docs/s3.md](docs/s3.md) | S3 object storage |
| [docs/sitemap.md](docs/sitemap.md) | Sitemap spider |
| [docs/projects.md](docs/projects.md) | Project organization |

## Contributing

Contributions welcome. Areas where help would be particularly valuable:

- Automatic detection of website structural changes
- Additional extraction modules (images, tables, PDFs)
- Anti-bot support beyond Cloudflare
- Authentication and session management

## Responsible Use

ScrapAI is a tool. What you scrape is your responsibility. Respect robots.txt, check each site's terms of service, and comply with applicable laws in your jurisdiction. Don't scrape personal data without a legal basis. We provide the software; you're responsible for how you use it.

## License

[AGPL-3.0](LICENSE)

Commercial licenses available for organizations that cannot comply with AGPL v3. Contact info@discourselab.ai.
