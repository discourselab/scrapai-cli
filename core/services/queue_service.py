"""Queue service - queue management."""

import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.services.spiders_service import SpiderInfo
from scrapai.exceptions import ProjectNotFoundError


class QueueItem(BaseModel):
    """Queue item model."""

    id: int
    url: str
    description: str | None
    project: str
    status: str
    spider_name: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class BatchResult(BaseModel):
    """Result of batch processing."""

    total: int
    succeeded: int
    failed: int
    succeeded_items: list[SpiderInfo]
    failed_items: list["FailedQueueItem"]


class FailedQueueItem(BaseModel):
    """Failed queue item with error."""

    url: str
    description: str | None
    error: str


def queue_add(
    url: str,
    project: str,
    description: str | None = None,
    priority: int = 5,
    **meta,
) -> QueueItem:
    """Add a single URL to the generation queue.

    Args:
        url: Website URL to add.
        project: Project name.
        description: Optional description/instruction.
        priority: Priority (higher = sooner).
        **meta: Additional metadata.

    Returns:
        QueueItem that was added.
    """
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())

    existing = (
        db.query(CrawlQueue)
        .filter(CrawlQueue.project_name == project, CrawlQueue.website_url == url)
        .first()
    )

    if existing:
        return QueueItem(
            id=existing.id,
            url=existing.website_url,
            description=existing.custom_instruction,
            project=existing.project_name,
            status=existing.status,
            spider_name=None,
            error=None,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    queue_item = CrawlQueue(
        project_name=project,
        website_url=url,
        custom_instruction=description,
        priority=priority,
    )
    db.add(queue_item)
    db.commit()

    return QueueItem(
        id=queue_item.id,
        url=queue_item.website_url,
        description=queue_item.custom_instruction,
        project=queue_item.project_name,
        status=queue_item.status,
        spider_name=None,
        error=None,
        created_at=queue_item.created_at,
        updated_at=queue_item.updated_at,
    )


def queue_bulk(
    items: list[dict],
    project: str,
    default_priority: int = 5,
) -> list[QueueItem]:
    """Bulk-add URLs to the queue.

    Args:
        items: List of dicts with "url" and optional "description".
        project: Project name.
        default_priority: Default priority for items without one.

    Returns:
        List of QueueItems that were added.
    """
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())

    added_items = []

    for item in items:
        url = item.get("url")
        if not url:
            continue

        existing = (
            db.query(CrawlQueue)
            .filter(CrawlQueue.project_name == project, CrawlQueue.website_url == url)
            .first()
        )

        if existing:
            continue

        description = item.get("description")
        priority = item.get("priority", default_priority)

        queue_item = CrawlQueue(
            project_name=project,
            website_url=url,
            custom_instruction=description,
            priority=priority,
        )
        db.add(queue_item)
        added_items.append(queue_item)

    db.commit()

    return [
        QueueItem(
            id=q.id,
            url=q.website_url,
            description=q.custom_instruction,
            project=q.project_name,
            status=q.status,
            spider_name=None,
            error=None,
            created_at=q.created_at,
            updated_at=q.updated_at,
        )
        for q in added_items
    ]


def queue_list(
    project: str,
    status: str | None = None,
    limit: int | None = None,
) -> list[QueueItem]:
    """List queue items and their statuses.

    Args:
        project: Project name.
        status: Optional status filter.
        limit: Optional limit.

    Returns:
        List of QueueItems.
    """
    from core.db import get_db
    from core.models import CrawlQueue

    db = next(get_db())

    query = db.query(CrawlQueue).filter(CrawlQueue.project_name == project)

    if status:
        query = query.filter(CrawlQueue.status == status)
    else:
        query = query.filter(CrawlQueue.status.in_(["pending", "processing"]))

    query = query.order_by(CrawlQueue.priority.desc(), CrawlQueue.created_at.asc())

    if limit:
        query = query.limit(limit)

    items = query.all()

    return [
        QueueItem(
            id=i.id,
            url=i.website_url,
            description=i.custom_instruction,
            project=i.project_name,
            status=i.status,
            spider_name=None,
            error=i.error_message,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in items
    ]


def queue_process(
    project: str,
    concurrency: int = 5,
) -> BatchResult:
    """Process all pending queue items - generate a spider for each.

    Args:
        project: Project name.
        concurrency: Number of concurrent generations.

    Returns:
        BatchResult with processing summary.
    """
    from core.db import get_db
    from core.models import CrawlQueue
    from generate.pipeline import resolve_llm_config, run_add_pipeline
    import asyncio

    db = next(get_db())

    pending_items = (
        db.query(CrawlQueue)
        .filter(CrawlQueue.project_name == project, CrawlQueue.status == "pending")
        .order_by(CrawlQueue.priority.desc(), CrawlQueue.created_at.asc())
        .all()
    )

    if not pending_items:
        return BatchResult(
            total=0,
            succeeded=0,
            failed=0,
            succeeded_items=[],
            failed_items=[],
        )

    try:
        llm = resolve_llm_config(None, None, None, None)
    except ValueError:
        return BatchResult(
            total=len(pending_items),
            succeeded=0,
            failed=len(pending_items),
            succeeded_items=[],
            failed_items=[
                FailedQueueItem(
                    url=i.website_url,
                    description=i.custom_instruction,
                    error="LLM not configured",
                )
                for i in pending_items
            ],
        )

    succeeded_items = []
    failed_items = []

    async def process_item(item):
        result = await run_add_pipeline(
            url=item.website_url,
            project=project,
            description=item.custom_instruction or "",
            llm=llm,
            dry_run=False,
            output_path=None,
            backup=True,
        )

        if result.success:
            return {
                "status": "success",
                "item": item,
                "spider_name": result.spider_name,
            }
        return {"status": "failed", "item": item, "error": result.error}

    async def run_batch():
        sem = asyncio.Semaphore(concurrency)

        async def run_with_sem(item):
            async with sem:
                return await process_item(item)

        tasks = [run_with_sem(item) for item in pending_items]
        results = []
        for coro in asyncio.as_completed(tasks):
            results.append(await coro)
        return results

    results = asyncio.run(run_batch())

    for r in results:
        item = r["item"]
        if r["status"] == "success":
            item.status = "completed"
            item.completed_at = datetime.now(timezone.utc)
            item.updated_at = datetime.now(timezone.utc)
            db.commit()

            spider_name = r.get("spider_name")
            if spider_name:
                try:
                    spider_info = get_spider(spider_name, item.project_name)
                    succeeded_items.append(spider_info)
                except SpiderNotFoundError:
                    succeeded_items.append(
                        SpiderInfo(
                            name=spider_name,
                            project=item.project_name,
                            start_urls=[item.website_url],
                            config={},
                            created_at=None,
                            last_crawled_at=None,
                            last_crawl_item_count=None,
                        )
                    )
            else:
                succeeded_items.append(
                    SpiderInfo(
                        name=item.website_url,
                        project=item.project_name,
                        start_urls=[item.website_url],
                        config={},
                        created_at=None,
                        last_crawled_at=None,
                        last_crawl_item_count=None,
                    )
                )
        else:
            item.status = "failed"
            item.error_message = r.get("error", "Unknown error")
            item.updated_at = datetime.now(timezone.utc)
            db.commit()

            failed_items.append(
                FailedQueueItem(
                    url=item.website_url,
                    description=item.custom_instruction,
                    error=r.get("error", "Unknown error"),
                )
            )

    return BatchResult(
        total=len(pending_items),
        succeeded=len(succeeded_items),
        failed=len(failed_items),
        succeeded_items=succeeded_items,
        failed_items=failed_items,
    )
