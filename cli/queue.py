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


@queue.command('add')
@click.argument('url')
@click.option('-m', '--message', 'custom_instruction', default=None, help='Custom instruction for processing')
@click.option('--priority', type=int, default=5, help='Priority (higher = sooner, default: 5)')
@click.option('--project', default='default', help='Project name (default: default)')
def add(url, custom_instruction, priority, project):
    """Add website to queue"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())

    existing = db.query(CrawlQueue).filter(
        CrawlQueue.project_name == project,
        CrawlQueue.website_url == url
    ).first()

    if existing:
        status_emoji = {'pending': '⏳', 'processing': '🔄', 'completed': '✅', 'failed': '❌'}.get(existing.status, '❓')
        click.echo(f"⚠️  URL already exists in queue")
        click.echo(f"   {status_emoji} ID: {existing.id}")
        click.echo(f"   Status: {existing.status}")
        click.echo(f"   URL: {existing.website_url}")
        click.echo(f"   Skipping duplicate...")
        return

    queue_item = CrawlQueue(
        project_name=project,
        website_url=url,
        custom_instruction=custom_instruction,
        priority=priority
    )
    db.add(queue_item)
    db.commit()

    click.echo(f"✅ Added to queue (ID: {queue_item.id})")
    click.echo(f"   URL: {url}")
    click.echo(f"   Project: {project}")
    click.echo(f"   Priority: {priority}")
    if custom_instruction:
        click.echo(f"   Instructions: {custom_instruction}")


@queue.command('list')
@click.option('--project', default='default', help='Project name (default: default)')
@click.option('--status', default=None, help='Filter by status')
@click.option('--limit', type=int, default=5, help='Limit items shown (default: 5)')
@click.option('--all', 'show_all', is_flag=True, help='Show all items including failed/completed')
@click.option('--count', is_flag=True, help='Show only the count')
def list_queue(project, status, limit, show_all, count):
    """List queue items"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    query = db.query(CrawlQueue).filter(CrawlQueue.project_name == project)

    if status:
        query = query.filter(CrawlQueue.status == status)
    elif not show_all:
        query = query.filter(CrawlQueue.status.in_(['pending', 'processing']))

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
        status_emoji = {'pending': '⏳', 'processing': '🔄', 'completed': '✅', 'failed': '❌'}.get(item.status, '❓')
        click.echo(f"{status_emoji} [{item.id}] {item.website_url}")
        click.echo(f"   Status: {item.status} | Priority: {item.priority}")
        if item.custom_instruction:
            click.echo(f"   Instructions: {item.custom_instruction}")
        if item.processing_by:
            locked_time = item.locked_at.strftime('%Y-%m-%d %H:%M') if item.locked_at else 'Unknown'
            click.echo(f"   Processing by: {item.processing_by} (since {locked_time})")
        if item.error_message:
            click.echo(f"   Error: {item.error_message}")
        if item.completed_at:
            click.echo(f"   Completed: {item.completed_at.strftime('%Y-%m-%d %H:%M')}")
        click.echo()


@queue.command('next')
@click.option('--project', default='default', help='Project name (default: default)')
def next_item(project):
    """Get next item from queue (atomic claim)"""
    from core.db import get_db, is_postgres
    from sqlalchemy import text

    db = next(get_db())
    processing_by = f"{getpass.getuser()}@{socket.gethostname()}"

    if is_postgres():
        result = db.execute(text("""
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
        """), {'processing_by': processing_by, 'project_name': project})
    else:
        result = db.execute(text("""
            UPDATE crawl_queue
            SET status = 'processing', processing_by = :processing_by,
                locked_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id FROM crawl_queue
                WHERE status = 'pending' AND project_name = :project_name
                ORDER BY priority DESC, created_at ASC LIMIT 1
            ) AND status = 'pending'
            RETURNING id, website_url, custom_instruction, priority
        """), {'processing_by': processing_by, 'project_name': project})

    row = result.fetchone()
    db.commit()

    if row:
        click.echo(f"🔄 Claimed item from queue:")
        click.echo(f"   ID: {row[0]}")
        click.echo(f"   URL: {row[1]}")
        if row[2]:
            click.echo(f"   Instructions: {row[2]}")
        click.echo(f"   Priority: {row[3]}")
        click.echo(f"   Locked by: {processing_by}")
    else:
        click.echo(f"📭 No pending items in queue for project '{project}'")


@queue.command('complete')
@click.argument('id', type=int)
def complete(id):
    """Mark item as completed"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    now = datetime.now(timezone.utc)
    item.status = 'completed'
    item.completed_at = now
    item.updated_at = now
    db.commit()

    click.echo(f"✅ Item {id} marked as completed")
    click.echo(f"   URL: {item.website_url}")


@queue.command('fail')
@click.argument('id', type=int)
@click.option('-m', '--message', 'error_message', default=None, help='Error message')
def fail(id, error_message):
    """Mark item as failed"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    item.status = 'failed'
    item.error_message = error_message
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    click.echo(f"❌ Item {id} marked as failed")
    click.echo(f"   URL: {item.website_url}")
    if error_message:
        click.echo(f"   Error: {error_message}")


@queue.command('retry')
@click.argument('id', type=int)
def retry(id):
    """Retry a failed item"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    item = db.query(CrawlQueue).filter(CrawlQueue.id == id).first()

    if not item:
        click.echo(f"❌ Queue item {id} not found")
        return

    item.status = 'pending'
    item.retry_count += 1
    item.error_message = None
    item.processing_by = None
    item.locked_at = None
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    click.echo(f"🔄 Item {id} reset to pending (retry count: {item.retry_count})")
    click.echo(f"   URL: {item.website_url}")


@queue.command('remove')
@click.argument('id', type=int)
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


@queue.command('cleanup')
@click.option('--completed', is_flag=True, help='Remove all completed items')
@click.option('--failed', is_flag=True, help='Remove all failed items')
@click.option('--all', 'clean_all', is_flag=True, help='Remove all completed and failed items')
@click.option('--project', default='default', help='Project name (default: default)')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
def cleanup(completed, failed, clean_all, project, force):
    """Bulk cleanup queue items"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    query = db.query(CrawlQueue).filter(CrawlQueue.project_name == project)

    if clean_all:
        query = query.filter(CrawlQueue.status.in_(['completed', 'failed']))
    elif completed:
        query = query.filter(CrawlQueue.status == 'completed')
    elif failed:
        query = query.filter(CrawlQueue.status == 'failed')
    else:
        click.echo("❌ Please specify --completed, --failed, or --all")
        return

    items = query.all()

    if not items:
        status_filter = "all completed and failed" if clean_all else ("completed" if completed else "failed")
        click.echo(f"📋 No {status_filter} items to cleanup in project '{project}'")
        return

    click.echo(f"🗑️  Found {len(items)} items to remove:")
    for item in items[:5]:
        status_emoji = '✅' if item.status == 'completed' else '❌'
        click.echo(f"   {status_emoji} [{item.id}] {item.website_url}")
    if len(items) > 5:
        click.echo(f"   ... and {len(items) - 5} more")

    if not force:
        confirm = input(f"\nRemove {len(items)} items? (y/N): ")
        if confirm.lower() != 'y':
            click.echo("❌ Cleanup cancelled")
            return

    for item in items:
        db.delete(item)
    db.commit()

    click.echo(f"✅ Removed {len(items)} items from queue")


@queue.command('bulk')
@click.argument('file')
@click.option('--project', default='default', help='Project name (default: default)')
@click.option('--priority', type=int, default=5, help='Default priority (default: 5)')
def bulk(file, project, priority):
    """Bulk add URLs from JSON or CSV file"""
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())
    file_path = Path(file)

    try:
        if file_path.suffix.lower() == '.csv':
            with open(file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                data = list(reader)
                if not data:
                    click.echo("❌ CSV file is empty")
                    return
                if 'url' not in data[0]:
                    click.echo("❌ CSV file must have a 'url' column")
                    click.echo("   See templates/queue-template.csv for example format")
                    return
        elif file_path.suffix.lower() == '.json':
            with open(file, 'r', encoding='utf-8') as f:
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
        url = item.get('url')
        if not url:
            click.echo(f"⚠️  Skipping item without URL: {item}")
            skipped += 1
            continue

        existing = db.query(CrawlQueue).filter(
            CrawlQueue.project_name == project,
            CrawlQueue.website_url == url
        ).first()

        if existing:
            skipped += 1
            continue

        custom_instruction = item.get('custom_instruction')
        item_priority = item.get('priority')
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
            priority=item_priority
        )
        db.add(queue_item)
        added += 1

    db.commit()

    click.echo(f"✅ Bulk add complete:")
    click.echo(f"   Added: {added}")
    click.echo(f"   Skipped (duplicates/invalid): {skipped}")
    click.echo(f"   Project: {project}")
    click.echo(f"   Format: {file_path.suffix.upper()}")
