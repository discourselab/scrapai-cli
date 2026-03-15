# ScrapAI Python Library API

ScrapAI provides a programmatic Python API for web scraping operations, in addition to its CLI interface.

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from scrapai import setup, list_spiders, crawl, show_items

# Initialize environment
setup()

# List spiders in a project
spiders = list_spiders(project="news")

# Run a crawl
result = crawl(spider="bbc_news", project="news", limit=10)

# Retrieve scraped items
items = show_items(spider="bbc_news", project="news", limit=5)
```

## API Reference

### Setup & Verification

#### `setup() -> SetupResult`
Initialize .env, database, and DATA_DIR.

```python
from scrapai import setup, SetupResult

result = setup()
print(result.success)  # True
print(result.db_url)  # sqlite:///scrapai.db
```

#### `verify() -> VerifyResult`
Verify environment is correctly configured.

```python
from scrapai import verify, VerifyResult

result = verify()
print(result.success)  # True/False
print(result.checks)   # Dict of check results
```

### Project Management

#### `list_projects() -> list[ProjectInfo]`
List all projects in the database.

```python
from scrapai import list_projects, ProjectInfo

projects: list[ProjectInfo] = list_projects()
for p in projects:
    print(f"{p.name}: {p.spider_count} spiders")
    print(f"  Last crawled: {p.last_crawled_at}")
```

### Spider Management

#### `list_spiders(project: str | None = None) -> list[SpiderInfo]`
List all spiders, optionally filtered by project.

```python
from scrapai import list_spiders, SpiderInfo

spiders: list[SpiderInfo] = list_spiders(project="news")
for s in spiders:
    print(f"{s.name}: {s.last_crawl_item_count} items")
```

#### `get_spider(name: str, project: str) -> SpiderInfo`
Get a single spider's configuration.

```python
from scrapai import get_spider, SpiderInfo

spider: SpiderInfo = get_spider("bbc_news", "news")
print(spider.config)  # Full spider config dict
```

#### `import_spider(config: dict | Path, project: str) -> SpiderInfo`
Import a spider from dict or JSON file.

```python
from scrapai import import_spider, SpiderInfo

spider: SpiderInfo = import_spider("spiders/bbc.json", project="news")
```

#### `export_spider(name: str, project: str) -> dict`
Export a spider's configuration as dict.

```python
from scrapai import export_spider

config = export_spider("bbc_news", "news")
```

#### `delete_spider(name: str, project: str) -> None`
Delete a spider and its scraped data.

```python
from scrapai import delete_spider

delete_spider("bbc_news", "news")
```

### Spider Generation

#### `generate_spider(url: str, project: str, description: str | None = None, ...) -> GenerateSpiderResult`
Generate and import a spider via LLM.

```python
from scrapai import generate_spider, GenerateSpiderResult

result: GenerateSpiderResult = generate_spider(
    url="https://www.bbc.com/news",
    project="news",
    description="Extract article headlines, dates, and summaries"
)
print(f"Created spider: {result.name}")
```

#### `repair_spider(name: str, project: str) -> GenerateSpiderResult`
Re-generate a broken spider's config using LLM.

```python
from scrapai import repair_spider

result = repair_spider("bbc_news", "news")
```

### Crawling

#### `crawl(spider: str, project: str | None = None, limit: int | None = None, ...) -> CrawlResult`
Run a spider.

```python
from scrapai import crawl, CrawlResult

result: CrawlResult = crawl(
    spider="bbc_news",
    project="news",
    limit=10,           # Test mode: crawl 10 items
    browser=False,      # Use browser for JS-rendered sites
    proxy_type="auto"   # auto, datacenter, or residential
)
print(f"Crawled {result.item_count} items in {result.duration_ms}ms")
```

#### `crawl_all(project: str, limit: int | None = None, concurrency: int = 4) -> list[CrawlResult]`
Run all spiders in a project in parallel.

```python
from scrapai import crawl_all

results = crawl_all(project="news", limit=10, concurrency=4)
for r in results:
    print(f"{r.spider}: {r.item_count} items ({'success' if r.success else 'failed'})")
```

### Data Retrieval

#### `show_items(spider: str, project: str, limit: int = 10, ...) -> ItemsResult`
Retrieve scraped items from database.

```python
from scrapai import show_items, ItemsResult

result: ItemsResult = show_items(
    spider="bbc_news",
    project="news",
    limit=10,
    url="https://example.com"  # Optional: filter by URL
)
for item in result.items:
    print(item.title, item.url)
```

#### `export_items(spider: str, project: str, output: Path, ...) -> ExportResult`
Export items to file.

```python
from scrapai import export_items, ExportResult
from pathlib import Path

result: ExportResult = export_items(
    spider="bbc_news",
    project="news",
    output=Path("exports/bbc.jsonl"),
    fmt="jsonl"
)
print(f"Exported {result.item_count} items to {result.file_path}")
```

### Health Checks

#### `health_check(project: str, sample_size: int = 5) -> HealthReport`
Run health check on all spiders in a project.

```python
from scrapai import health_check, HealthReport

report: HealthReport = health_check(project="news")
print(f"Passed: {report.passing}/{report.total_spiders}")
for result in report.results:
    status = "✓" if result.passing else "✗"
    print(f"{status} {result.spider}: {result.item_count} items")
```

#### `health_check_spider(name: str, project: str) -> SpiderHealthResult`
Run health check on a single spider.

```python
from scrapai import health_check_spider

result = health_check_spider("bbc_news", "news")
print(f"Passing: {result.passing}, Items: {result.item_count}")
```

### Queue Management

#### `queue_add(url: str, project: str, description: str | None = None, priority: int = 5) -> QueueItem`
Add a URL to the crawl queue.

```python
from scrapai import queue_add, QueueItem

item: QueueItem = queue_add(
    url="https://example.com",
    project="news",
    description="Extract product prices",
    priority=10  # Higher = more urgent
)
```

#### `queue_bulk(file: Path, project: str, priority: int = 5) -> BatchResult`
Bulk import URLs from file.

```python
from scrapai import queue_bulk, BatchResult
from pathlib import Path

result: BatchResult = queue_bulk(
    file=Path("urls.txt"),
    project="news"
)
print(f"Added {result.succeeded} URLs, {result.failed} failed")
```

#### `queue_list(project: str, status: str | None = None, limit: int = 10) -> list[QueueItem]`
List queue items.

```python
from scrapai import queue_list

items = queue_list(project="news", status="pending", limit=50)
```

#### `queue_process(project: str, max_items: int = 5) -> BatchResult`
Process queue items (generate + crawl).

```python
from scrapai import queue_process, BatchResult

result: BatchResult = queue_process(project="news", max_items=5)
print(f"Succeeded: {result.succeeded}, Failed: {result.failed}")
for item in result.succeeded_items:
    print(f"  Created spider: {item.name}")
```

### Database Operations

#### `db_stats() -> DbStats`
Get database statistics.

```python
from scrapai import db_stats, DbStats

stats: DbStats = db_stats()
print(f"Total spiders: {stats.total_spiders}")
print(f"Total items: {stats.total_items}")
print(f"Database size: {stats.db_size_bytes / 1024 / 1024:.2f} MB")
for p in stats.projects:
    print(f"  {p.name}: {p.spider_count} spiders")
```

#### `db_query(sql: str) -> list[dict]`
Execute a read-only SQL query.

```python
from scrapai import db_query

rows = db_query("SELECT * FROM scraped_items LIMIT 10")
```

### URL Inspection

#### `inspect_url(url: str, browser: bool = False) -> InspectionResult`
Inspect a URL to get page info.

```python
from scrapai import inspect_url, InspectionResult

result: InspectionResult = inspect_url(
    url="https://example.com",
    browser=False  # Use browser mode for JS-rendered sites
)
print(f"URL: {result.url}")
print(f"Status: {result.status_code}")
print(f"JS Rendered: {result.js_rendered}")
print(f"Selectors: {result.detected_selectors}")
```

## Return Types

### Pydantic Models

```python
# SetupResult
class SetupResult:
    success: bool
    db_url: str
    data_dir: str
    message: str

# VerifyResult
class VerifyResult:
    success: bool
    checks: dict[str, bool]
    errors: list[str]

# ProjectInfo
class ProjectInfo:
    name: str
    spider_count: int
    last_crawled_at: datetime | None

# SpiderInfo
class SpiderInfo:
    name: str
    project: str
    start_urls: list[str]
    config: dict
    created_at: datetime | None
    last_crawled_at: datetime | None
    last_crawl_item_count: int | None

# CrawlResult
class CrawlResult:
    spider: str
    project: str
    item_count: int
    duration_ms: int
    success: bool
    error: str | None
    started_at: datetime
    finished_at: datetime

# InspectionResult
class InspectionResult:
    url: str
    status_code: int | None
    detected_selectors: list[str] | None
    js_rendered: bool | None
    cloudflare_protected: bool | None
    url_params: dict[str, str] | None
    output_dir: str | None
    html_snapshot: str | None
    title: str | None
    description: str | None
    links: list[str] | None
    headers: dict[str, str] | None
    inspected_at: datetime | None

# BatchResult
class BatchResult:
    total: int
    succeeded: int
    failed: int
    succeeded_items: list[SpiderInfo]
    failed_items: list[FailedQueueItem]
```

## Exceptions

```python
from scrapai import (
    SpiderNotFoundError,
    ProjectNotFoundError,
    GenerationFailedError,
    LLMNotConfiguredError,
    CrawlError,
    ExportError,
    QueryNotAllowedError,
    ValidationError,
    ScrapAIConfigError,
)

try:
    spider = get_spider("nonexistent", "default")
except SpiderNotFoundError as e:
    print(f"Spider not found: {e}")
```

## Environment Variables

```bash
# Database
DATABASE_URL=sqlite:///scrapai.db
DATA_DIR=./data

# LLM Configuration
SCRAPAI_LLM_API=https://api.openrouter.ai/v1
SCRAPAI_LLM_KEY=your-api-key
SCRAPAI_LLM_MODEL=anthropic/claude-3-sonnet

# Optional: S3 Upload
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=my-scrapes
```
