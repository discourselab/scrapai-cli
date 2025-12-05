# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Project-based Scrapy spider management for large-scale web scraping. Built for Claude Code to intelligently analyze and scrape websites using a database-first approach.

## For Claude Code Instances

**When asked to add any website, follow this Database-First Workflow:**

### 1. Setup (First Time Only)
Ensure the database is initialized with migrations:
```bash
# Check .env for DB credentials, then run migrations
./init_db.py
```

**Database Management:**
- `./scrapai db migrate` - Run pending migrations
- `./scrapai db current` - Show current migration state  
- All schema changes are handled safely via Alembic migrations

### 2. Workflow

#### Phase 1: Analysis
Inspect the site structure to understand how to extract content.
```bash
source .venv/bin/activate
bin/inspector --url https://website.com/
```
-   Look for article URL patterns (e.g., `/article/`, `/2024/`).
-   Identify navigation elements to follow or ignore.
-   Determine CSS selectors for content (though `newspaper4k` handles most).

#### Phase 2: Definition (JSON Payload)
Construct a JSON payload defining the spider. **Do not create Python files.**

**Payload Structure:**
```json
{
  "name": "website_name",
  "allowed_domains": ["website.com"],
  "start_urls": ["https://www.website.com/"],
  "rules": [
    {
      "allow": ["/article/.*", "/2024/.*"],
      "deny": ["/login", "/signup"],
      "callback": "parse_article",
      "follow": true,
      "priority": 10
    },
    {
      "restrict_css": [".nav-links", ".pagination"],
      "follow": true
    }
  ],
  "settings": {
    "DOWNLOAD_DELAY": 2,
    "CONCURRENT_REQUESTS": 2,
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura", "playwright"]
  }
}
```

#### Phase 3: Import
Import the JSON payload directly into the database via stdin.
```bash
echo '{...json content...}' | ./scrapai spiders import -
```

#### Phase 4: Execution & Verification
Run the spider directly from the database.
```bash
./scrapai crawl website_name --limit 10
```
-   **Verify Data**: Data is saved directly to the `scraped_items` table in the database.
-   **Check Logs**: Ensure no extraction errors occurred.
-   If adjustments are needed, update the JSON payload and re-import (it will update the existing spider).

### 3. CLI Reference

**Spider Management:**
-   `./scrapai spiders list` - List all spiders in the DB.
-   `./scrapai spiders import <file>` - Import/Update a spider from JSON.
-   `./scrapai spiders delete <name>` - Delete a spider.

**Crawling:**
-   `./scrapai crawl <name>` - Run a specific spider.
-   `./scrapai crawl <name> --limit 10` - Test with a limit.

**Database Management:**
-   `./scrapai db migrate` - Run database migrations.
-   `./scrapai db current` - Show current migration revision.

**Data Inspection:**
-   `./scrapai show <spider_name>` - Show recent articles from spider (default: 5).
-   `./scrapai show <spider_name> --limit 10` - Show specific number of articles.
-   `./scrapai show <spider_name> --url pattern` - Filter by URL pattern (case-insensitive).
-   `./scrapai show <spider_name> --text "climate"` - Search title or content for text (case-insensitive).
-   `./scrapai show <spider_name> --title "climate"` - Search only article titles (case-insensitive).

## Extractor Options

The system uses a **Smart Extractor** that tries multiple strategies in order. You can configure the order via `EXTRACTOR_ORDER` in settings.

**Available Strategies:**
1.  `newspaper`: Uses `newspaper4k` on the static HTML (Fast, Default).
2.  `trafilatura`: Uses `trafilatura` on the static HTML (Good for text-heavy sites).
3.  `playwright`: Uses a headless browser to fetch rendered HTML, then extracts with `trafilatura` (Slow, handles JS).

**Default Order:** `["newspaper", "trafilatura", "playwright"]`

## Core Principles
-   **Database First**: All configuration lives in the database.
-   **Agent Driven**: Agents use CLI tools to manage the DB.
-   **Generic Spider**: The system uses a single `DatabaseSpider` that loads rules dynamically.
-   **Smart Extraction**: Content extraction is handled automatically with multiple fallback strategies.
-   **Database Persistence**: Scraped items are batched and saved efficiently to the PostgreSQL database.

## What Claude Code Can Modify
-   **✅ Allowed**:
    -   Creating/Editing JSON payloads.
    -   Running CLI commands (`scrapai`, `init_db.py`).
    -   Updating `.env` (if requested).
-   **❌ Not Allowed**:
    -   Creating `.py` spider files (Legacy).
    -   Modifying core framework code.

## Architecture Notes

**Database Schema:**
- `spiders` - Spider definitions (domains, start URLs)
- `spider_rules` - Link extraction rules (allow/deny patterns, selectors)  
- `spider_settings` - Custom Scrapy settings per spider
- `scraped_items` - Extracted content storage

**Key Framework Files:**
- `spiders/database_spider.py` - Generic spider loads config from DB
- `core/db.py` - Database connection and session management
- `core/models.py` - SQLAlchemy ORM models with timestamps (created_at, updated_at)
- `core/extractors.py` - Smart content extraction system
- `alembic/` - Database migration files for safe schema evolution

**Database Migration System:**
- Uses Alembic for safe schema changes without data loss
- `./init_db.py` now runs migrations instead of create_all()
- Migration history tracked for rollback capability
- Automatic timestamp tracking for spider configurations