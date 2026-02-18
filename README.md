# ScrapAI-CLI

**scrapAI** (pronounced scrape-eye)

Agent-agnostic AI orchestration layer for Scrapy web scraping at scale.

## TL;DR

ScrapAI uses AI coding agents to analyze website structure once, generating database-stored configuration rules that enable deterministic scraping without ongoing AI costs. One-time setup (FREE for 10-20 sites with Cursor/Antigravity, or $0.50-1.00/site with Claude Code), then standard Scrapy execution forever. Includes production-ready orchestration via Apache Airflow (scheduling, monitoring, retries, web UI) and flexible storage (database for testing, JSONL/S3 for production scale). Built to manage hundreds to thousands of websites. Best suited for continuous monitoring where setup automation and systematic management matter.

## Table of Contents

- [Overview](#overview)
- [The Problem](#the-problem)
  - [Cost Comparison](#cost-comparison)
- [Solution Architecture](#solution-architecture)
  - [Analysis Phase: AI-Driven](#analysis-phase-ai-driven)
  - [Execution Phase: Deterministic](#execution-phase-deterministic)
  - [Database-First Configuration](#database-first-configuration)
- [Performance Characteristics](#performance-characteristics)
- [Orchestration & Deployment](#orchestration--deployment)
- [Queue System](#queue-system)
- [Storage Modes](#storage-modes)
- [Use Cases](#use-cases)
- [Limitations](#limitations)
- [Philosophy](#philosophy)
- [Getting Started](#getting-started)
- [Management Interface](#management-interface)
- [Project Status](#project-status)

## Overview

ScrapAI addresses the fundamental challenge of managing web scraping infrastructure across hundreds or thousands of websites. Rather than maintaining individual spider files or relying on per-page AI extraction, ScrapAI uses AI to perform comprehensive upfront analysis of website structure, then executes deterministic scraping operations through a database-driven configuration system.

## The Problem

Traditional approaches to large-scale web scraping face significant structural limitations:

**Manual spider development** requires deep expertise in HTML parsing, CSS selectors, XPath expressions, and Scrapy architecture. At scale, maintaining hundreds of individual spider files becomes operationally infeasible. Changes to global scraping policies require manual propagation across entire codebases.

**Existing AI-assisted tools** typically operate on a per-page extraction model, incurring ongoing API costs for every page scraped. Many still require developers to specify selectors, manage pagination logic, and maintain scraper code. The "AI assistance" layer often adds decision overhead without eliminating the underlying complexity.

**Contract development** produces site-specific implementations that become maintenance liabilities the moment external developers disengage. Knowledge becomes siloed in undocumented code, and inevitable website redesigns require re-engagement at consultant rates.

### Cost Comparison

| Metric | ScrapAI (Free Tier) | ScrapAI (Claude Code) | Traditional Development |
|--------|---------------------|----------------------|------------------------|
| **Setup Cost/Site** | FREE* | $0.50-1.00 | $50-150 |
| **Setup Time/Site** | 1-2 minutes | 1-2 minutes | 1-2 hours |
| **100 Sites Setup** | FREE*, ~3 hours | $50-100, ~3 hours | $5K-15K, **250 hours (6 weeks)** |
| **1,000 Sites Setup** | API costs apply* | $500-1K, ~30 hours | $50K-150K, **2,000 hours (1 year)** |
| **Maintenance/Year** | FREE* or $100-200 | $100-200 (20% redesign) | $10K-30K, **400 hours** |
| **Developer Fatigue** | None (AI) | None (AI) | High (repetitive work) |

**\*Free Tier Reality Check:** Cursor and Antigravity free tiers are generous for testing and small-scale use (typically 10-50 sites), but have request limits. For 100+ sites, you'll likely exceed free tier limits and incur API costs.

**Time & Fatigue Reality:**
- **1,000 sites manually:** 1,000-2,000 hours = 6-12 months of repetitive work
- **1,000 sites with ScrapAI:** 16-33 hours = 1-2 weeks of AI-assisted work
- **Ongoing maintenance:** ~20% of sites need updates yearly due to redesigns

**Agent Selection Guide:**
- **Testing or 10-20 sites:** Cursor/Antigravity FREE tier (excellent for getting started)
- **50-100 sites:** Compare API costs (Cursor/Antigravity) vs Claude Code pricing
- **200+ sites:** Claude Code or paid API plans (workflow optimization becomes valuable)
- **Want model choice:** Cursor/Antigravity (switch between OpenAI, Gemini, Claude)
- **Quality difference is negligible** for single-site analysis, but Claude Code's workflow features shine at scale

## Solution Architecture

ScrapAI implements a separation between analysis and execution:

### Analysis Phase: AI-Driven

An AI agent performs comprehensive structural analysis of each target website:

1. **Homepage inspection** to identify primary navigation structure
2. **Iterative exploration** of section and subsection hierarchies  
3. **Pattern recognition** for content pages versus navigation elements
4. **Rule generation** with URL matching patterns and priority levels
5. **Configuration output** of extraction callbacks and crawl parameters

This analysis executes once per website, producing a JSON configuration that encodes the site's structure.

### Execution Phase: Deterministic

A single generic spider loads configurations from database storage and executes deterministic scraping operations. No AI inference occurs during crawling. No per-page API costs are incurred.

### Database-First Configuration

All spider behavior is controlled through database records rather than code:

**What's stored as data:**
- Spider configurations (JSON documents)
- URL extraction rules
- Settings changes
- Version control through database migrations

**Key benefits:**
- Settings propagate through SQL updates, not code edits
- Instant rollback via transaction history
- No deployment required for configuration changes
- Concurrent edits without merge conflicts

This architecture enables systematic operations that are impractical with file-based configurations. Updating crawl delays across all news sites becomes a single SQL UPDATE statement rather than editing dozens of Python files.

> **Key Architectural Advantage: Database vs Files**
> 
> Traditional approach: 100 spider files × manual edits × git commits × code review × deployment
> 
> Database approach: Single SQL UPDATE affecting all spiders instantly
> 
> Example: Changing rate limits across all news sites
> ```sql
> UPDATE spider_settings SET value = '3' 
> WHERE key = 'DOWNLOAD_DELAY' 
> AND spider_id IN (SELECT id FROM spiders WHERE name LIKE '%news%');
> ```
> No deployment. No merge conflicts. Instant rollback via transaction history.

## Performance Characteristics

Based on production deployment managing hundreds to thousands of websites:

| Metric | Cursor/Antigravity | Claude Code |
|--------|-------------------|-------------|
| **Setup Time (per site)** | 1-2 minutes | 1-2 minutes |
| **Setup Cost (per site)** | FREE* then API costs | $0.50-1.00 |
| **Free Tier Limit** | ~10-50 sites (varies) | N/A (always paid) |
| **Analysis Quality** | Excellent | Excellent+ (negligible difference) |
| **Queue Processing** | Good (sequential) | Excellent (parallel, background tasks) |
| **Context Management** | Good | Excellent (better for long sessions) |
| **Ongoing AI Cost** | $0 (deterministic execution) | $0 (deterministic execution) |
| **10-20 Sites Total** | **FREE**, ~30 mins | ~$5-20, ~25 mins* |
| **100 Sites Total** | Likely exceed free tier** | ~$50-100, ~2.5 hours* |
| **1,000 Sites Total** | API costs apply** | ~$500-1,000, ~25 hours* |

*Claude Code's parallel processing and workflow optimization can reduce time by 15-20% for large batches.

**Free tier limits vary by provider. Once exceeded, you pay for API usage (OpenAI, Gemini, etc.). Actual costs depend on which model and pricing tier you choose.

**When each agent makes sense:**
- **Testing or 10-20 sites:** Use Cursor/Antigravity FREE tier (excellent for getting started)
- **50+ sites:** Compare costs - Claude Code predictable, Cursor/Antigravity depends on API provider pricing
- **200+ sites:** Claude Code recommended (predictable pricing, workflow optimization, parallel processing)

These costs reflect one-time setup. Ongoing operational costs are limited to infrastructure (compute, storage, bandwidth) with no per-page AI charges.

## Orchestration & Deployment

At scale, infrastructure management becomes the primary operational challenge. Building spiders is straightforward; running hundreds in production requires:

- **Scheduling**: Configuring execution intervals (daily, weekly, custom cron) per spider
- **Monitoring**: Tracking success/failure rates, execution times, error patterns
- **Retry logic**: Handling transient failures, rate limits, timeouts
- **Storage**: Managing output data across millions of pages
- **Access control**: Multi-user environments with project-based permissions

ScrapAI includes production-ready orchestration via Apache Airflow and Docker Compose.

### What's Included

**Apache Airflow Integration:**
- **Auto-discovery**: DAGs automatically generated from your spider database
- **Scheduling**: Set cron schedules per spider (`@daily`, `0 */6 * * *`, etc.)
- **Monitoring**: Real-time task status, execution time, success/failure rates
- **Retry logic**: Automatic retry on failure with configurable backoff
- **Logs**: Persistent logs for debugging and auditing
- **Web UI**: Visual interface for managing and triggering spiders
- **RBAC**: Project-based access control for teams

**Project Organization:**
- Filter spiders by project tags
- Team-based permissions (Admin, User, Viewer roles)
- Separate namespaces for different use cases

**Storage Integration:**
- S3-compatible storage (Hetzner, DigitalOcean, AWS S3, MinIO, etc.)
- Automatic upload of crawl outputs
- Configurable via environment variables

**Docker Deployment:**
- One-command deployment: `docker-compose up`
- All dependencies bundled (Airflow, PostgreSQL, workers)
- Concurrency controls based on server specs
- Scales from 2-core laptops to production servers

### Quick Start

```bash
# 1. Start Airflow (includes web UI, scheduler, database)
docker-compose -f docker-compose.airflow.yml up -d

# 2. Access UI at http://localhost:8080 (admin/admin)

# 3. Your spiders appear automatically as DAGs
# - Named: {project}_{spider_name}
# - Tagged: scrapai, project:{name}

# 4. Trigger manually or set schedules
```

See [airflow/README.md](airflow/README.md) for full documentation.

### Operational Comparison

**Without integrated orchestration:**
- Manual execution across hundreds of spiders
- Log aggregation through file system inspection
- Custom scheduling infrastructure (cron, systemd, custom code)
- Ad-hoc storage solutions
- Shared credential management

**With ScrapAI's Airflow integration:**
- Centralized dashboard for all spiders
- Visual monitoring, log inspection, execution control
- Declarative scheduling via cron expressions
- Automated S3/object storage integration
- Role-based access control with project isolation

The difference: operational infrastructure included rather than requiring separate implementation.

## Queue System

For batch processing workflows, ScrapAI implements an atomic queue system backed by PostgreSQL.

**Core capabilities:**
- Bulk addition of URLs with associated priority levels
- Asynchronous processing in configurable batch sizes
- Site-specific instructions attached to queue records
- Status tracking: pending, processing, completed, failed
- Concurrent worker support through database locking

**Operational patterns enabled:**

The queue enables workflows like adding 500 websites on Monday and processing them in 50-site batches throughout the week, or distributing processing across multiple team members without coordination overhead.

Example: Add batch of sites today, process 10 tomorrow, process 50 next week. Resume anytime without losing track of progress.

## Storage Modes

**Testing Mode:** Limited crawls write to database for immediate inspection. Appropriate for rule validation and quality assurance workflows.

**Production Mode:** Full crawls export to timestamped JSONL files in the file system, avoiding database storage costs at scale. Suitable for millions of pages.

> **💰 Cost & Time Reality Check**
>
> For a deployment managing hundreds to thousands of sites:
>
> **ScrapAI Setup:**
> - **Cost:** Varies by scale ($0 for small, $500-1,500 for 1,000+ sites)
> - **Time:** Hours to days, not months
> - **Annual maintenance:** ~$100-600 (20% of sites redesign yearly)
>
> **Traditional Development Alternative:**
> - **Cost:** $50-150 per site ($50K-150K for 1,000 sites)
> - **Time:** 1-2 hours per site (1,000-2,000 hours for 1,000 sites)
> - **Annual maintenance:** $10K-60K (400-600 hours/year)
> - **Reality:** Requires dedicated team, high fatigue from repetitive work, error-prone at scale
>
> **The real advantage isn't just cost - it's time, scalability, and maintainability.** Building thousands of spiders manually takes years; ScrapAI does it in weeks.

## Use Cases

**ScrapAI is optimized for:**

- Continuous monitoring of websites (daily/weekly scraping of same sites)
- Projects monitoring even a few sites constantly where setup automation saves time
- Large website portfolios (hundreds to thousands of sites)
- Teams without deep Scrapy expertise seeking AI-driven structural analysis
- Operations requiring systematic changes across entire spider fleets
- Cost-conscious projects avoiding ongoing per-page AI charges

**ScrapAI is not appropriate for:**

- Single-website projects (traditional Scrapy is more direct)
- One-off data extraction (ChatGPT or Claude or similar tools work fine)
- Content requiring complex reasoning rather than structural extraction
- Projects where per-page AI inference provides value worth the cost premium

## Limitations

> **⚠️ Critical Limitation**
> 
> Anti-bot measures (Cloudflare, CAPTCHAs, login walls) are the primary technical barrier.
> 
> ScrapAI currently handles polite, public scraping well. Aggressive anti-bot protection, authenticated content, and CAPTCHA systems require additional tooling. Stealth mode is in development but requires non-headless browsers with GUI, complicating deployment to standard VPS infrastructure.
> 
> This is the fundamental challenge in web scraping at scale, not specific to ScrapAI.

### Anti-Scraping Countermeasures

Standard web scraping limitations apply. Cloudflare challenges, CAPTCHA systems, aggressive rate limiting, and IP blocking affect ScrapAI identically to any Scrapy-based system. The tool respects robots.txt and implements polite crawling with configurable delays.

Stealth mode implementation is in progress to handle more aggressive anti-bot systems. This requires non-headless browser execution with full GUI environments, which complicates deployment to headless VPS infrastructure or remote servers without display capabilities. Until stealth mode is production-ready, highly protected sites remain challenging for all scraping approaches including ScrapAI.

### Structural Brittleness

Website redesigns that alter HTML structure invalidate extraction rules. When a site changes article title selectors or DOM organization, rules must be regenerated. Sites that redesign frequently (more than bi-annually) create ongoing maintenance overhead. Current implementation does not include automatic change detection; failures manifest as empty or incorrect extractions requiring manual intervention.

This limitation applies equally to all scraping approaches. Manual spider development requires developer time to update code when sites change. Per-page AI tools continue to function but incur ongoing costs for every page scraped. Developers must be re-engaged at typical rates ($50-100/hour) to update broken scrapers. ScrapAI's re-analysis takes 1-2 minutes and costs $0.50-1.00 per site (or FREE within tier limits for Cursor/Antigravity). Automatic change detection is planned for future releases.

### JavaScript Rendering Overhead

ScrapAI uses standard HTTP requests by default, enabling maximum performance through Scrapy's concurrent request management, intelligent rate limiting, and efficient connection pooling. This approach handles the majority of websites effectively.

Sites requiring JavaScript execution (single-page applications, dynamic content loading) can use Playwright-based extraction, but this introduces 5-10x latency compared to HTTP scraping. Browser instantiation, JavaScript execution, and rendering create significant overhead. Most websites do not require this; when they do, the performance penalty is inherent to browser automation rather than a ScrapAI limitation.

### Limited Extraction Scope

Current extractors target text content exclusively (title, author, date, body text). Images, videos, tables, embedded media, structured data, and binary documents are not extracted. Custom extractors can be implemented for specific media types, but this requires additional development.

### Content Understanding Requirements

ScrapAI extracts structural patterns, not semantic meaning. Tasks requiring interpretation of content (sentiment analysis, topic classification, methodology extraction from scientific papers, context-dependent clause identification in legal documents) exceed the tool's design scope. These scenarios require per-page LLM inference, which ScrapAI explicitly avoids to maintain cost characteristics.

### Current Extraction Capabilities

| Feature | Status | Notes |
|---------|--------|-------|
| Text content | ✅ Supported | Title, author, date, body text |
| HTML structure | ✅ Saved | Full HTML saved, enables parsing anything without new requests |
| Images | ❌ Not extracted | URLs available in saved HTML, minimal code to add |
| Videos | ❌ Not extracted | Embed codes available in saved HTML, minimal code to add |
| Tables | ❌ Not extracted | Available in saved HTML, minimal code to add |
| PDFs | ❌ Not extracted | Links available in saved HTML |
| Structured data | ❌ Not extracted | JSON-LD, schema.org available in HTML |

Since full HTML is saved, adding extraction for any additional content type requires minimal code changes without re-scraping pages.

### Structural Inconsistency

Websites where each page has unique structure cannot be handled with unified extraction rules. Wikipedia articles with varying infobox schemas, user-generated content platforms where each author applies different styling, and archives mixing multiple content formats require either multiple spider configurations or alternative approaches. Pattern-based extraction assumes structural consistency.

### AI Orchestration Dependency

ScrapAI requires an AI coding agent for site analysis and orchestration. The tool is not a standalone CLI installable via pip.

**Supported AI Agents:**
- **Cursor** - FREE tier, supports OpenAI/Claude/others, excellent quality
- **Antigravity (Gemini)** - FREE tier, supports Gemini/Claude/others, excellent quality
- **Claude Code** - $0.50-1.00/site, Claude models only, excellent+ quality (negligible difference)

**Recommendation:** For most users, Cursor/Antigravity is the obvious choice (FREE, already installed, model flexibility). Consider Claude Code if you're batch processing 50+ sites where workflow optimization provides value, or if you already use Claude Code in your development workflow.

The multi-phase workflow (inspection, verification, import, testing) is orchestrated by ScrapAI through the AI agent rather than requiring user expertise. Organizations preferring self-contained tools without external AI dependencies should evaluate this architectural choice carefully.

### Queue System Database Requirements

Queue operations require PostgreSQL for atomic locking primitives (FOR UPDATE SKIP LOCKED). SQLite deployments cannot use queue features, though all other functionality remains available. Queue-based workflows require running PostgreSQL locally or in production infrastructure.

### AI Analysis Accuracy

ScrapAI's AI-driven analysis can misclassify page types, particularly when distinguishing content pages from navigation or listing pages. Common errors include extracting category listings as articles, missing subsections during exploration, incorrectly scoping URL patterns, or including author biography pages in content extraction. All AI-generated configurations require human verification through limited test crawls before production deployment.

### Redesign Response Time

When websites restructure, rules must be regenerated through AI re-analysis. The process takes 1-2 minutes and costs $0.50-1.00 per site. Automated change detection and alerting is under development to identify when extraction patterns fail and trigger re-analysis workflows.

## Philosophy

ScrapAI represents a specific architectural position: AI should eliminate repetitive analysis work upfront, then execute deterministically without ongoing inference costs. Configuration should be data rather than code. Management operations should scale horizontally through database primitives. Spider proliferation should be solved through centralization, not through better file organization.

This is not the only valid approach to web scraping at scale, but it represents a deliberate set of trade-offs optimized for a particular operational profile.

## Getting Started

ScrapAI is agent-agnostic and works with multiple AI coding assistants. Choose the option that best fits your needs.

### Agent Selection

| Agent | Cost | Model Flexibility | Analysis Quality | Best For |
|-------|------|------------------|------------------|----------|
| **Cursor** | **FREE tier*** | OpenAI, Claude, others | Excellent | Testing, 10-20 sites, popular IDE |
| **Antigravity** | **FREE tier*** | Gemini, Claude, others | Excellent | Testing, 10-20 sites, Gemini users |
| **Claude Code** | $0.50-1.00/site | Claude only | Excellent+ | 50+ sites, predictable pricing, workflows |

*Free tier typically covers 10-50 sites depending on usage. Beyond that, API costs apply.

**Choose based on your use case:**
- **Testing or 10-20 sites?** → Use **Cursor** or **Antigravity** FREE tier
- **50-100 sites?** → Compare costs: Cursor/Antigravity API pricing vs **Claude Code**
- **200+ sites?** → Consider **Claude Code** (predictable pricing, workflow optimization)
- **Want model choice?** → Use **Cursor/Antigravity** (can switch between OpenAI, Gemini, Claude)

### Setup

**Quick Start (5 minutes):**

1. **Clone the repository**

   ```bash
   git clone https://github.com/discourselab/scrapai-cli.git
   cd scrapai-cli
   ```

2. **Run setup**

   ```bash
   ./scrapai setup
   ```

   That's it! This single command:
   - ✅ Creates virtual environment automatically
   - ✅ Installs all dependencies
   - ✅ Initializes SQLite database (no PostgreSQL setup required!)
   - ✅ Configures permissions (if using Claude Code)

   **Note:** Virtual environment activation is automatic - you never need to run `source .venv/bin/activate`!

3. **Verify installation**

   ```bash
   ./scrapai verify
   ```

**For detailed onboarding guide, see [docs/onboarding.md](docs/onboarding.md)**

4. **Choose your AI agent**

   ### Option A: Cursor (FREE)

   1. Install Cursor from [cursor.com](https://cursor.com)
   2. Open the repository in Cursor
   3. The agent will automatically read `agents.md` for instructions
   4. Start chatting: "Add this website: https://example.com"

   **Cost:** FREE | **Quality:** Excellent

   ### Option B: Antigravity (FREE - Gemini)

   1. Install Antigravity (if needed)
   2. Open the repository in Antigravity
   3. **Configure Gemini agent:**
      - Click `...` (three dots) in top-right panel
      - Select "Customizations"
      - Select `.agent/rules/gemini.md`
      - Ensure "Always On" is activated
   4. Start chatting: "Add this website: https://example.com"

   **Cost:** FREE | **Quality:** Excellent

   ### Option C: Claude Code

   1. Install Claude Code: [code.claude.com/docs/en/setup](https://code.claude.com/docs/en/setup)
   2. Run in the repository directory:
      ```bash
      claude
      ```
   3. The agent will automatically read `CLAUDE.md` for instructions
   4. Start chatting: "Add this website: https://example.com"

   **Cost:** $0.50-1.00 per site | **Quality:** Excellent

### Example Usage

Regardless of which agent you choose, the workflow is identical:

```
You: "Add this website: https://example.com"
Agent: [Analyzes site structure, generates rules, imports spider, tests]

You: "Show me what's in the database"
Agent: [Lists all configured spiders]

You: "Process the next item in the queue"
Agent: [Claims and processes next queued website]
```

### Detailed Workflow Documentation

- **Claude Code users:** See [CLAUDE.md](CLAUDE.md)
- **Cursor users:** See [agents.md](agents.md)
- **Antigravity users:** See [.agent/rules/gemini.md](.agent/rules/gemini.md)

All documentation covers:
- Database-first setup procedures
- Website analysis and spider generation
- Queue system usage
- CLI command reference

## Management Interface

A dedicated management UI is currently under development to provide more effective spider administration at scale. The existing ScrapyWeb interface is no longer actively maintained and does not provide adequate user experience for managing hundreds or thousands of sites. The new dashboard, built in TypeScript, will offer streamlined spider configuration, monitoring, and administration capabilities designed specifically for large-scale deployment scenarios.

## Project Status

This tool was developed for internal use to manage a large-scale content monitoring operation. We are sharing it publicly in case others face similar challenges.

ScrapAI is an agent-agnostic AI orchestration layer built on top of Scrapy, an established and battle-tested web scraping framework. It works with Claude Code, Cursor, Antigravity/Gemini, and potentially other AI coding assistants. The same orchestration approach could be applied to other excellent packages in the ecosystem such as Crawl4AI, ScrapeGraphAI, or similar tools. The core concept—using AI for upfront structural analysis followed by deterministic execution—is both framework-agnostic and agent-agnostic.

Contributions addressing operational issues are welcome. Areas particularly suitable for improvement:

- Automatic detection of website structural changes
- More efficient JavaScript rendering strategies  
- Enhanced error recovery and retry logic
- Additional extraction modules for media types
- Internationalization support for non-English content