# ScrapAI-CLI

AI-driven orchestration layer for Scrapy web scraping at scale.

## TL;DR

ScrapAI uses AI to analyze website structure once, generating database-stored configuration rules that enable deterministic scraping without ongoing AI costs. Instead of maintaining hundreds of Python spider files or paying per-page AI extraction fees, you get one-time setup ($0.50-1.00 per site, 1-2 minutes) followed by standard Scrapy execution. Developed to manage a personal use case of monitoring 2,000 websites. Best suited for continuous monitoring of multiple sites where setup time and systematic management matter.

## Overview

ScrapAI addresses the fundamental challenge of managing web scraping infrastructure across hundreds or thousands of websites. Rather than maintaining individual spider files or relying on per-page AI extraction, ScrapAI uses AI to perform comprehensive upfront analysis of website structure, then executes deterministic scraping operations through a database-driven configuration system.

## The Problem

Traditional approaches to large-scale web scraping face significant structural limitations:

**Manual spider development** requires deep expertise in HTML parsing, CSS selectors, XPath expressions, and Scrapy architecture. At scale, maintaining hundreds of individual spider files becomes operationally infeasible. Changes to global scraping policies require manual propagation across entire codebases.

**Existing AI-assisted tools** typically operate on a per-page extraction model, incurring ongoing API costs for every page scraped. Many still require developers to specify selectors, manage pagination logic, and maintain scraper code. The "AI assistance" layer often adds decision overhead without eliminating the underlying complexity.

**Contract development** produces site-specific implementations that become maintenance liabilities the moment external developers disengage. Knowledge becomes siloed in undocumented code, and inevitable website redesigns require re-engagement at consultant rates.

### Cost Comparison

| Approach | Setup Cost/Site | Redesign Cost/Site | 100 Sites | 1,000 Sites |
|----------|----------------|-------------------|-----------|-------------|
| **ScrapAI** | $0.50-1.00 | $0.50-1.00 | $50-100 | $500-1,000 |
| Manual Development | $200-500 | $200-500 | $20K-50K | $200K-500K |
| Contract Developers | $500-2,000 | $500-2,000 | $50K-200K | $500K-2M |
| Per-Page AI Tools | Varies | Ongoing per-page costs | Varies significantly | Varies significantly |

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

Based on production deployment managing 2,000 websites:

| Metric | Value |
|--------|-------|
| **Setup Time** | 1-2 minutes per site |
| **Setup Cost** | $0.50-1.00 per site (AI analysis) |
| **Ongoing AI Cost** | $0 (deterministic execution) |
| **100 Sites Total** | ~$50-100, ~3 hours |
| **1,000 Sites Total** | ~$500-1,000, ~30 hours |
| **2,000 Sites Total** | ~$1,000-2,000, ~60 hours |

These costs reflect one-time setup. Ongoing operational costs are limited to infrastructure (compute, storage, bandwidth) with no per-page AI charges.

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

> **💰 Cost Reality Check**
> 
> Our 2,000-site deployment cost breakdown:
> - Initial setup: ~$1,500 in AI costs, ~60 hours of time
> - Ongoing: Zero AI costs (deterministic Scrapy execution)
> - Alternative quotes we received: $400K+ for contract development
> 
> The math changes dramatically at scale. Even at 50 sites, ScrapAI setup ($25-50) beats manual spider development or per-page AI tools.

## Use Cases

**ScrapAI is optimized for:**

- Continuous monitoring of websites (daily/weekly scraping of same sites)
- Projects monitoring even a few sites constantly where setup automation saves time
- Large website portfolios (our use case: 2,000 sites)
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

This limitation applies equally to all scraping approaches. Manual spider development requires developer time to update code when sites change. Per-page AI tools continue to function but incur ongoing costs for every page scraped. Contract developers must be re-engaged at $50-150/hour to update broken scrapers. ScrapAI's re-analysis takes 1-2 minutes and costs $0.50-1.00 per site when regeneration is needed. Automatic change detection is planned for future releases.

### JavaScript Rendering Overhead

ScrapAI uses standard HTTP requests by default, enabling maximum performance through Scrapy's concurrent request management, intelligent rate limiting, and efficient connection pooling. This approach handles the majority of websites effectively.

Sites requiring JavaScript execution (single-page applications, dynamic content loading) can use Playwright-based extraction, but this introduces 5-10x latency compared to HTTP scraping. Browser instantiation, JavaScript execution, and rendering create significant overhead. Most websites do not require this; when they do, the performance penalty is inherent to browser automation rather than a ScrapAI limitation.

### Limited Extraction Scope

Current extractors target text content exclusively (title, author, date, body text). Images, videos, tables, embedded media, structured data, and binary documents are not extracted. Custom extractors can be implemented for specific media types, but this requires additional development.

### Anti-Scraping Countermeasures

Standard web scraping limitations apply. Cloudflare challenges, CAPTCHA systems, aggressive rate limiting, and IP blocking affect ScrapAI identically to any Scrapy-based system. The tool respects robots.txt and implements polite crawling with configurable delays.

Stealth mode implementation is in progress to handle more aggressive anti-bot systems. This requires non-headless browser execution with full GUI environments, which complicates deployment to headless VPS infrastructure or remote servers without display capabilities. Until stealth mode is production-ready, highly protected sites remain challenging for all scraping approaches including ScrapAI.

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

Initial setup requires Claude Code for site analysis. The tool is not a standalone CLI installable via pip. The setup costs mentioned previously ($0.50-1.00 per site) reflect Claude API consumption during analysis; no separate subscription beyond API usage is required. The multi-phase workflow (inspection, verification, import, testing) is handled by the AI agent rather than requiring user expertise. Organizations preferring self-contained tools without external AI dependencies should evaluate this architectural choice carefully.

### Queue System Database Requirements

Queue operations require PostgreSQL for atomic locking primitives (FOR UPDATE SKIP LOCKED). SQLite deployments cannot use queue features, though all other functionality remains available. Queue-based workflows require running PostgreSQL locally or in production infrastructure.

### AI Analysis Accuracy

Claude Code can misclassify page types, particularly distinguishing content pages from navigation or listing pages. Common errors include extracting category listings as articles, missing subsections during exploration, incorrectly scoping URL patterns, or including author biography pages in content extraction. All AI-generated configurations require human verification through limited test crawls before production deployment.

### Redesign Response Time

When websites restructure, rules must be regenerated through AI re-analysis. The process takes 1-2 minutes and costs $0.50-1.00 per site. Automated change detection and alerting is under development to identify when extraction patterns fail and trigger re-analysis workflows.

## Philosophy

ScrapAI represents a specific architectural position: AI should eliminate repetitive analysis work upfront, then execute deterministically without ongoing inference costs. Configuration should be data rather than code. Management operations should scale horizontally through database primitives. Spider proliferation should be solved through centralization, not through better file organization.

This is not the only valid approach to web scraping at scale, but it represents a deliberate set of trade-offs optimized for a particular operational profile.

## Getting Started

Refer to CLAUDE.md for detailed setup procedures and workflow documentation. Site addition and configuration occurs through Claude Code interaction as documented in that file.

## Management Interface

A dedicated management UI is currently under development to provide more effective spider administration at scale. The existing ScrapyWeb interface is no longer actively maintained and does not provide adequate user experience for managing hundreds or thousands of sites. The new dashboard, built in TypeScript, will offer streamlined spider configuration, monitoring, and administration capabilities designed specifically for large-scale deployment scenarios.

## Project Status

This tool was developed for internal use to manage 2,000 websites for content monitoring. We are sharing it publicly in case others face similar challenges.

ScrapAI is an AI orchestration layer built on top of Scrapy, an established and battle-tested web scraping framework. The same orchestration approach could be applied to other excellent packages in the ecosystem such as Crawl4AI, ScrapeGraphAI, or similar tools. The core concept—using AI for upfront structural analysis followed by deterministic execution—is framework-agnostic.

Contributions addressing operational issues are welcome. Areas particularly suitable for improvement:

- Automatic detection of website structural changes
- More efficient JavaScript rendering strategies  
- Enhanced error recovery and retry logic
- Additional extraction modules for media types
- Internationalization support for non-English content