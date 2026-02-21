# Getting Started

## Requirements

- Python 3.9+
- Git

## Setup

```bash
git clone https://github.com/discourselab/scrapai-cli.git
cd scrapai-cli
./scrapai setup
./scrapai verify
```

`./scrapai setup` creates venv, installs dependencies, initializes SQLite database, and configures Claude Code permissions.

## Troubleshooting

**"No module named 'scrapy'":**
```bash
./scrapai setup
```

**Database issues:**
```bash
rm scrapai.db scrapai.db-*
./scrapai setup
```

**Virtual environment issues:**
```bash
rm -rf .venv
./scrapai setup
```

## Upgrading to PostgreSQL (Optional)

```bash
# Install PostgreSQL
brew install postgresql    # Mac
sudo apt-get install postgresql  # Ubuntu/Debian

# Create database
createdb scrapai

# Update .env
DATABASE_URL=postgresql://user:password@localhost:5432/scrapai

# Run migrations
./scrapai db migrate

# Transfer existing data from SQLite
./scrapai db transfer sqlite:///scrapai.db

# Or skip scraped articles
./scrapai db transfer sqlite:///scrapai.db --skip-items
```

Update `DATABASE_URL` in `.env` before running transfer. Reads from source URL, writes to current `DATABASE_URL`.
