import click
import json
import csv
import socket
import getpass
from datetime import datetime, timezone
from pathlib import Path


@click.group()
def queue():
    """Queue management"""
    pass


@queue.command("add")
@click.argument("url")
@click.option(
    "-m",
    "--message",
    "custom_instruction",
    default=None,
    help="Custom instruction for processing",
)
@click.option(
    "--priority", type=int, default=5, help="Priority (higher = sooner, default: 5)"
)
@click.option("--project", default="default", help="Project name (default: default)")
def add(url, custom_instruction, priority, project):
    """Add website to queue"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())

    existing = (
        db.query(CrawlQueue)
        .filter(CrawlQueue.project_name == project, CrawlQueue.website_url == url)
        .first()
    )

    if existing:
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄",
            "completed": "✅",
            "failed": "❌",
        }.get(existing.status, "❓")
        click.echo("⚠️  URL already exists in queue")
        click.echo(f"   {status_emoji} ID: {existing.id}")
        click.echo(f"   Status: {existing.status}")
        click.echo(f"   URL: {existing.website_url}")
        click.echo("   Skipping duplicate...")
        return

    queue_item = CrawlQueue(
        project_name=project,
        website_url=url,
        custom_instruction=custom_instruction,
        priority=priority,
    )
    db.add(queue_item)
    db.commit()

    click.echo(f"✅ Added to queue (ID: {queue_item.id})")
    click.echo(f"   URL: {url}")
    click.echo(f"   Project: {project}")
    click.echo(f"   Priority: {priority}")
    if custom_instruction:
        click.echo(f"   Instructions: {custom_instruction}")


@queue.command("list")
@click.option("--project", default="default", help="Project name (default: default)")
@click.option("--status", default=None, help="Filter by status")
@click.option("--limit", type=int, default=5, help="Limit items shown (default: 5)")
@click.option(
    "--all", "show_all", is_flag=True, help="Show all items including failed/completed"
)
@click.option("--count", is_flag=True, help="Show only the count")
def list_queue(project, status, limit, show_all, count):
    """List queue items"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    query = db.query(CrawlQueue).filter(CrawlQueue.project_name == project)

    if status:
        query = query.filter(CrawlQueue.status == status)
    elif not show_all:
        query = query.filter(CrawlQueue.status.in_(["pending", "processing"]))

    if count:
        click.echo(f"{query.count()}")
        return

    query = query.order_by(CrawlQueue.priority.desc(), CrawlQueue.created_at.asc())
    if limit:
        query = query.limit(limit)

    items = query.all()

    if not items:
        status_msg = f" with status '{status}'" if status else ""
        click.echo(f"📋 No items in queue for project '{project}'{status_msg}")
        return

    click.echo(f"📋 Queue for project '{project}':")
    click.echo()

    for item in items:
        status_emoji = {
            "pending": "⏳",
            "processing": "🔄",
            "completed": "✅",
            "failed": "❌",
        }.get(item.status, "❓")
        click.echo(f"{status_emoji} [{item.id}] {item.website_url}")
        click.echo(f"   Status: {item.status} | Priority: {item.priority}")
        if item.custom_instruction:
            click.echo(f"   Instructions: {item.custom_instruction}")
        if item.processing_by:
            locked_time = (
                item.locked_at.strftime("%Y-%m-%d %H:%M")
                if item.locked_at
                else "Unknown"
            )
            click.echo(f"   Processing by: {item.processing_by} (since {locked_time})")
        if item.error_message:
            click.echo(f"   Error: {item.error_message}")
        if item.completed_at:
            click.echo(f"   Completed: {item.completed_at.strftime('%Y-%m-%d %H:%M')}")
        click.echo()


@queue.command("next")
@click.option("--project", default="default", help="Project name (default: default)")
def next_item(project):
    """Get next item from queue (atomic claim)"""
    from core.db import get_db, is_postgres
    from sqlalchemy import text

    db = next(get_db())
    processing_by = f"{getpass.getuser()}@{socket.gethostname()}"

    if is_postgres():
        result = db.execute(
            text("""
            UPDATE crawl_queue
            SET status = 'processing', processing_by = :processing_by,
                locked_at = NOW(), updated_at = NOW()
            WHERE id = (
                SELECT id FROM crawl_queue
                WHERE status = 'pending' AND project_name = :project_name
                ORDER BY priority DESC, created_at ASC LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, website_url, custom_instruction, priority
        """),
            {"processing_by": processing_by, "project_name": project},
        )
    else:
        result = db.execute(
            text("""
            UPDATE crawl_queue
            SET status = 'processing', processing_by = :processing_by,
                locked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id FROM crawl_queue
                WHERE status = 'pending' AND project_name = :project_name
                ORDER BY priority DESC, created_at ASC LIMIT 1
            ) AND status = 'pending'
            RETURNING id, website_url, custom_instruction, priority
        """),
            {"processing_by": processing_by, "project_name": project},
        )

    row = result.fetchone()
    db.commit()

    if row:
        click.echo("🔄 Claimed item from queue:")
        click.echo(f"   ID: {row[0]}")
        click.echo(f"   URL: {row[1]}")
        if row[2]:
            click.echo(f"   Instructions: {row[2]}")
        click.echo(f"   Priority: {row[3]}")
        click.echo(f"   Locked by: {processing_by}")
    else:
        click.echo(f"📭 No pending items in queue for project '{project}'")


@queue.command("complete")
@click.argument("id", type=int)
@click.option(
    "--spider",
    default=None,
    help="Spider name (auto-detected from URL if not provided)",
)
@click.option("--force", is_flag=True, help="Skip verification checks")
def complete(id, spider, force):
    """Mark item as completed (verifies spider exists in DB and final_spider.json on disk)"""
    from urllib.parse import urlparse
    from core.db import get_db
    from core.models import CrawlQueue, Spider
    from core.config import DATA_DIR

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    if not force:
        # Derive spider name from URL if not provided
        if spider:
            spider_name = spider
        else:
            parsed = urlparse(item.website_url)
            domain = parsed.netloc.lstrip("www.")
            spider_name = domain.replace(".", "_").replace("-", "_")

        # Check 1: spider exists in DB
        db_spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == item.project_name)
            .first()
        )
        if not db_spider:
            click.echo(
                f"❌ Cannot mark complete: spider '{spider_name}' not found in DB"
            )
            click.echo("   Use --spider <name> if spider has a different name")
            click.echo("   Use --force to skip verification")
            db.close()
            return

        # Check 2: final_spider.json exists on disk
        final_json = (
            Path(DATA_DIR)
            / item.project_name
            / spider_name
            / "analysis"
            / "final_spider.json"
        )
        if not final_json.exists():
            click.echo("❌ Cannot mark complete: final_spider.json not found")
            click.echo(f"   Expected: {final_json}")
            click.echo("   Use --force to skip verification")
            db.close()
            return

        click.echo(f"✓ Spider '{spider_name}' verified in DB")
        click.echo("✓ final_spider.json exists")

    now = datetime.now(timezone.utc)
    item.status = "completed"
    item.completed_at = now
    item.updated_at = now
    db.commit()

    click.echo(f"✅ Item {id} marked as completed")
    click.echo(f"   URL: {item.website_url}")


@queue.command("fail")
@click.argument("id", type=int)
@click.option("-m", "--message", "error_message", default=None, help="Error message")
def fail(id, error_message):
    """Mark item as failed"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    item.status = "failed"
    item.error_message = error_message
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    click.echo(f"❌ Item {id} marked as failed")
    click.echo(f"   URL: {item.website_url}")
    if error_message:
        click.echo(f"   Error: {error_message}")


@queue.command("retry")
@click.argument("id", type=int)
def retry(id):
    """Retry a failed item"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    item.status = "pending"
    item.retry_count += 1
    item.error_message = None
    item.processing_by = None
    item.locked_at = None
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    click.echo(f"🔄 Item {id} reset to pending (retry count: {item.retry_count})")
    click.echo(f"   URL: {item.website_url}")


@queue.command("remove")
@click.argument("id", type=int)
def remove(id):
    """Remove item from queue"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    url = item.website_url
    db.delete(item)
    db.commit()

    click.echo(f"🗑️  Item {id} removed from queue")
    click.echo(f"   URL: {url}")


@queue.command("cleanup")
@click.option("--completed", is_flag=True, help="Remove all completed items")
@click.option("--failed", is_flag=True, help="Remove all failed items")
@click.option(
    "--all", "clean_all", is_flag=True, help="Remove all completed and failed items"
)
@click.option("--project", default="default", help="Project name (default: default)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def cleanup(completed, failed, clean_all, project, force):
    """Bulk cleanup queue items"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    query = db.query(CrawlQueue).filter(CrawlQueue.project_name == project)

    if clean_all:
        query = query.filter(CrawlQueue.status.in_(["completed", "failed"]))
    elif completed:
        query = query.filter(CrawlQueue.status == "completed")
    elif failed:
        query = query.filter(CrawlQueue.status == "failed")
    else:
        click.echo("❌ Please specify --completed, --failed, or --all")
        return

    items = query.all()

    if not items:
        status_filter = (
            "all completed and failed"
            if clean_all
            else ("completed" if completed else "failed")
        )
        click.echo(f"📋 No {status_filter} items to cleanup in project '{project}'")
        return

    click.echo(f"🗑️  Found {len(items)} items to remove:")
    for item in items[:5]:
        status_emoji = "✅" if item.status == "completed" else "❌"
        click.echo(f"   {status_emoji} [{item.id}] {item.website_url}")
    if len(items) > 5:
        click.echo(f"   ... and {len(items) - 5} more")

    if not force:
        confirm = input(f"\nRemove {len(items)} items? (y/N): ")
        if confirm.lower() != "y":
            click.echo("❌ Cleanup cancelled")
            return

    for item in items:
        db.delete(item)
    db.commit()

    click.echo(f"✅ Removed {len(items)} items from queue")


@queue.command("bulk")
@click.argument("file")
@click.option("--project", default="default", help="Project name (default: default)")
@click.option("--priority", type=int, default=5, help="Default priority (default: 5)")
def bulk(file, project, priority):
    """Bulk add URLs from JSON or CSV file"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    file_path = Path(file)

    try:
        if file_path.suffix.lower() == ".csv":
            with open(file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                data = list(reader)
                if not data:
                    click.echo("❌ CSV file is empty")
                    return
                if "url" not in data[0]:
                    click.echo("❌ CSV file must have a 'url' column")
                    click.echo("   See templates/queue-template.csv for example format")
                    return
        elif file_path.suffix.lower() == ".json":
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                click.echo("❌ JSON file must contain an array of objects")
                return
        else:
            click.echo(f"❌ Unsupported file format: {file_path.suffix}")
            click.echo("   Supported formats: .json, .csv")
            return
    except FileNotFoundError:
        click.echo(f"❌ File not found: {file}")
        return
    except json.JSONDecodeError as e:
        click.echo(f"❌ Invalid JSON: {e}")
        return
    except csv.Error as e:
        click.echo(f"❌ Invalid CSV: {e}")
        return
    except Exception as e:
        click.echo(f"❌ Error reading file: {e}")
        return

    added = 0
    skipped = 0

    for item in data:
        url = item.get("url")
        if not url:
            click.echo(f"⚠️  Skipping item without URL: {item}")
            skipped += 1
            continue

        existing = (
            db.query(CrawlQueue)
            .filter(CrawlQueue.project_name == project, CrawlQueue.website_url == url)
            .first()
        )

        if existing:
            skipped += 1
            continue

        custom_instruction = item.get("custom_instruction")
        item_priority = item.get("priority")
        if item_priority is not None:
            try:
                item_priority = int(item_priority)
            except (ValueError, TypeError):
                item_priority = priority
        else:
            item_priority = priority

        queue_item = CrawlQueue(
            project_name=project,
            website_url=url,
            custom_instruction=custom_instruction,
            priority=item_priority,
        )
        db.add(queue_item)
        added += 1

    db.commit()

    click.echo("✅ Bulk add complete:")
    click.echo(f"   Added: {added}")
    click.echo(f"   Skipped (duplicates/invalid): {skipped}")
    click.echo(f"   Project: {project}")
    click.echo(f"   Format: {file_path.suffix.upper()}")


@queue.command("add-with-generate")
@click.argument("file")
@click.option("--project", required=True, help="Project name (required)")
@click.option("--url-column", default="url", help="CSV column for URLs")
@click.option(
    "--description-column", default="description", help="CSV column for descriptions"
)
@click.option(
    "--concurrency",
    type=int,
    default=5,
    help="Number of concurrent generations (default: 5)",
)
@click.option(
    "--failed-output",
    default=None,
    help="CSV path for failed rows (default: failed_spiders.csv next to input)",
)
@click.option("--llm-api", default=None, help="LLM API base URL")
@click.option("--llm-key", default=None, help="LLM API key")
@click.option("--llm-model", default=None, help="LLM model name")
@click.option(
    "--llm-timeout",
    type=int,
    default=None,
    help="Per-call LLM timeout in seconds (default: 30)",
)
@click.option("--dry-run", is_flag=True, help="Skip DB write and test crawl")
def add_with_generate(
    file,
    project,
    url_column,
    description_column,
    concurrency,
    failed_output,
    llm_api,
    llm_key,
    llm_model,
    llm_timeout,
    dry_run,
):
    """Generate spiders from a CSV file (LLM-driven)."""
    import asyncio

    from generate.pipeline import resolve_llm_config, run_add_pipeline

    if concurrency < 1:
        click.echo("❌ --concurrency must be at least 1")
        return

    file_path = Path(file)
    if not file_path.exists():
        click.echo(f"❌ File not found: {file}")
        return

    try:
        with open(file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception as e:
        click.echo(f"❌ Error reading CSV: {e}")
        return

    if not rows:
        click.echo("❌ CSV file is empty")
        return

    if url_column not in rows[0] or description_column not in rows[0]:
        click.echo("❌ CSV missing required columns")
        click.echo(f"   Required: {url_column}, {description_column}")
        return

    try:
        primary = resolve_llm_config(llm_api, llm_key, llm_model, llm_timeout)
    except ValueError as exc:
        click.echo(f"❌ {exc}")
        return

    if failed_output:
        failed_path = Path(failed_output)
    else:
        failed_path = file_path.parent / "failed_spiders.csv"

    async def run_batch():
        sem = asyncio.Semaphore(concurrency)
        results = []

        async def handle_row(row):
            url = (row.get(url_column) or "").strip()
            desc = (row.get(description_column) or "").strip()
            if not url or not desc:
                return {"status": "skipped", "row": row, "error": "missing url/description"}

            async with sem:
                result = await run_add_pipeline(
                    url=url,
                    project=project,
                    description=desc,
                    llm=primary,
                    dry_run=dry_run,
                    output_path=None,
                    backup=True,
                )
                if result.success:
                    return {"status": "succeeded", "row": row}
                error_text = (result.error or "unknown error").replace("\n", " | ")
                return {"status": "failed", "row": row, "error": error_text}

        tasks = [handle_row(r) for r in rows]
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)
        return results

    results = asyncio.run(run_batch())

    succeeded = sum(1 for r in results if r["status"] == "succeeded")
    failed = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skipped"]

    click.echo("\nSummary")
    click.echo(f"  Succeeded: {succeeded}")
    click.echo(f"  Failed:    {len(failed)}")
    click.echo(f"  Skipped:   {len(skipped)}")

    failed_rows = failed + skipped
    if failed_rows:
        fieldnames = list(rows[0].keys()) + ["error"]
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        with open(failed_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in failed_rows:
                row = dict(item["row"])
                row["error"] = item.get("error", "unknown error")
                writer.writerow(row)
        click.echo(f"Failed rows written to: {failed_path}")
