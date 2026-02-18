# Getting Started with ScrapAI CLI

Welcome! This guide will help you get ScrapAI up and running in minutes.

## What You Need

- **Mac, Linux, or Windows** (with WSL)
- **Python 3.9+** installed
- **Git** (to clone the repository)
- That's it! No database installation required.

## Quick Start (5 Minutes)

### Step 1: Clone the Repository

```bash
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli
```

### Step 2: Run Setup

```bash
./scrapai setup
```

This one command does everything:
- ✅ Creates virtual environment
- ✅ Installs all dependencies
- ✅ Initializes SQLite database
- ✅ Configures permissions (if using Claude Code)

**Note:** You'll see a lot of package installation messages - this is normal! It takes 1-2 minutes.

### Step 3: Verify Installation

```bash
./scrapai verify
```

You should see:
```
✅ Virtual environment exists
✅ Core dependencies installed
✅ Database initialized
🎉 Environment is ready!
```

## That's It!

You're ready to start scraping. No virtual environment activation needed, no PostgreSQL setup required - it just works!

## What's Happening Behind the Scenes?

### SQLite Database (Zero Setup)

By default, ScrapAI uses **SQLite** - a file-based database that requires zero configuration. Your database is just a file (`scrapai.db`) in your project directory.

**Want to use PostgreSQL later?** No problem! Just change `DATABASE_URL` in `.env` and re-run setup.

### Auto-Activating Virtual Environment

When you run `./scrapai`, it automatically:
1. Detects if a virtual environment exists (`.venv` or `venv`)
2. Activates it transparently
3. Runs your command

You **never** need to type `source .venv/bin/activate` - the CLI does it for you!

### Claude Code Permissions (Automatic)

If you're using **Claude Code** (the AI coding assistant), the setup command automatically configures project-specific permissions in `.claude/settings.local.json`:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Write",
      "Edit",
      "Update",
      "Glob",
      "Grep",
      "Bash(./scrapai:*)",
      "Bash(source:*)",
      "Bash(sqlite3:*)"
    ],
    "deny": [
      "WebFetch",
      "WebSearch"
    ]
  }
}
```

**What this does:**
- ✅ **Allows** all file operations (Read, Write, Edit, Update, Glob, Grep)
- ✅ **Allows** all ScrapAI CLI commands (`./scrapai:*`)
- ✅ **Allows** essential system commands (source, sqlite3)
- ❌ **Denies** web tools (WebFetch, WebSearch) - these don't exist in the repo anyway
- 🔄 **Merges with existing** - Won't overwrite your accumulated permissions
- 🔒 **Project-specific** - only applies to this project, not your other Claude Code projects

**Why this matters:**
- Prevents Claude Code from trying to use tools that don't exist
- Pre-approves file operations and all ScrapAI commands
- Preserves any additional permissions you've already granted
- Makes onboarding smoother by avoiding permission prompts

**Note:** If you're using a different AI assistant (Cursor, Windsurf, etc.), this section doesn't apply - it's Claude Code specific.

## Next Steps

### 1. Create a Project

Projects help organize your spiders:

```bash
# View help
./scrapai projects --help

# Create a project (this is optional - "default" project is used if not specified)
./scrapai projects create --name myproject --spiders spider1,spider2
```

### 2. Add Websites to Queue (Optional)

The queue system helps manage multiple websites:

```bash
# Add a website
./scrapai queue add https://example.com --project myproject

# View queue
./scrapai queue list --project myproject

# Get next item to process
./scrapai queue next --project myproject
```

**See [docs/queue.md](queue.md) for full queue documentation.**

### 3. Analyze and Create Spiders

**Option A: Work with Claude Code**

If using Claude Code, follow the [docs/analysis-workflow.md](analysis-workflow.md) to:
1. Analyze website structure
2. Create extraction rules
3. Test and deploy spiders

**Option B: Manual Spider Creation**

Create a spider JSON file:

```json
{
  "name": "example_spider",
  "source_url": "https://example.com",
  "allowed_domains": ["example.com"],
  "start_urls": ["https://example.com"],
  "rules": [
    {
      "allow": ["article/.*"],
      "callback": "parse_article",
      "follow": true
    }
  ],
  "settings": {
    "EXTRACTOR_ORDER": ["newspaper", "trafilatura"]
  }
}
```

Import it:
```bash
./scrapai spiders import spider.json --project myproject
```

### 4. Run Your First Crawl

```bash
# Test mode (saves to database for verification)
./scrapai crawl example_spider --project myproject --limit 5

# View results
./scrapai show example_spider --project myproject --limit 5

# Production mode (exports to files)
./scrapai crawl example_spider --project myproject
```

## Common Commands

```bash
# List all spiders in a project
./scrapai spiders list --project myproject

# Delete a spider
./scrapai spiders delete spider_name --project myproject

# Export data
./scrapai export spider_name --project myproject --format csv

# Database operations
./scrapai db migrate  # Run database migrations
./scrapai db current  # Show current migration version
```

## Troubleshooting

### "No module named 'scrapy'" Error

Run setup again:
```bash
./scrapai setup
```

### Database Issues

Reset the database:
```bash
rm scrapai.db scrapai.db-*
./scrapai setup
```

### Virtual Environment Issues

Delete and recreate:
```bash
rm -rf .venv
./scrapai setup
```

## Upgrading to PostgreSQL (Optional)

If you need PostgreSQL for production or multi-machine deployments:

1. **Install PostgreSQL** (one-time setup)
   ```bash
   # Mac
   brew install postgresql

   # Ubuntu/Debian
   sudo apt-get install postgresql
   ```

2. **Create database**
   ```bash
   createdb scrapai
   ```

3. **Update .env**
   ```bash
   cp .env.example .env
   # Edit .env and change DATABASE_URL to:
   # DATABASE_URL=postgresql://user:password@localhost:5432/scrapai
   ```

4. **Run migrations**
   ```bash
   ./scrapai db migrate
   ```

## Need Help?

- **Documentation:** Check the [docs/](.) folder for detailed guides
- **Issues:** Report bugs at https://github.com/discourselab/scrapai-cli/issues
- **CLAUDE.md:** If using Claude Code, see [CLAUDE.md](../CLAUDE.md) for AI agent instructions

## What's Next?

Ready to dive deeper? Check out:

- **[docs/analysis-workflow.md](analysis-workflow.md)** - Learn the complete workflow for analyzing and scraping websites
- **[docs/extractors.md](extractors.md)** - Understand how content extraction works
- **[docs/queue.md](queue.md)** - Master the queue system for batch processing
- **[docs/projects.md](projects.md)** - Learn about project isolation and organization
- **[README.md](../README.md)** - Full project overview

Happy scraping! 🚀
