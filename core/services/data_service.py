"""Data service - retrieving and exporting scraped items."""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.config import DATA_DIR
from scrapai.exceptions import SpiderNotFoundError, ExportError


class ItemsResult(BaseModel):
    """Result of show_items operation."""

    spider: str | None
    project: str
    items: list[dict]
    total_count: int
    limit: int
    offset: int


class ExportResult(BaseModel):
    """Result of export_items operation."""

    spider: str | None
    project: str
    format: str
    item_count: int
    output_path: Path | None
    data: bytes | None


def show_items(
    project: str,
    spider: str | None = None,
    limit: int = 10,
    offset: int = 0,
    url: str | None = None,
    title: str | None = None,
    text: str | None = None,
) -> ItemsResult:
    """Retrieve scraped items.

    Args:
        project: Project name.
        spider: Optional spider name filter.
        limit: Number of items to retrieve.
        offset: Offset for pagination.
        url: Optional URL filter.
        title: Optional title filter.
        text: Optional title/content search.

    Returns:
        ItemsResult with items and metadata.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem
    from sqlalchemy import or_

    db = next(get_db())

    spider_query = db.query(Spider).filter(Spider.project == project)
    if spider:
        spider_query = spider_query.filter(Spider.name == spider)

    spiders = spider_query.all()
    spider_ids = [s.id for s in spiders]

    if not spider_ids:
        return ItemsResult(
            spider=spider,
            project=project,
            items=[],
            total_count=0,
            limit=limit,
            offset=offset,
        )

    query = db.query(ScrapedItem).filter(ScrapedItem.spider_id.in_(spider_ids))

    if url:
        query = query.filter(ScrapedItem.url.ilike(f"%{url}%"))
    if title:
        query = query.filter(ScrapedItem.title.ilike(f"%{title}%"))
    if text:
        query = query.filter(
            or_(
                ScrapedItem.title.ilike(f"%{text}%"),
                ScrapedItem.content.ilike(f"%{text}%"),
            )
        )

    total_count = query.count()
    items = (
        query.order_by(ScrapedItem.scraped_at.desc()).offset(offset).limit(limit).all()
    )

    spider_map = {s.id: s for s in spiders}

    result_items = []
    for item in items:
        spider_obj = spider_map.get(item.spider_id)
        spider_name = spider_obj.name if spider_obj else None
        callbacks_config = spider_obj.callbacks_config if spider_obj else {}

        item_dict = {
            "id": item.id,
            "url": item.url,
            "title": item.title,
            "content": item.content,
            "author": item.author,
            "published_date": item.published_date.isoformat()
            if item.published_date
            else None,
            "scraped_at": item.scraped_at.isoformat() if item.scraped_at else None,
            "spider_name": spider_name,
        }

        if item.metadata_json:
            item_dict["metadata"] = item.metadata_json

        result_items.append(item_dict)

    return ItemsResult(
        spider=spider,
        project=project,
        items=result_items,
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


def export_items(
    project: str,
    spider: str | None = None,
    fmt: str = "jsonl",
    output_path: Path | None = None,
    url: str | None = None,
    title: str | None = None,
    text: str | None = None,
    limit: int | None = None,
) -> ExportResult:
    """Export scraped data.

    Args:
        project: Project name.
        spider: Optional spider name filter.
        fmt: Export format (csv, json, jsonl, parquet).
        output_path: Optional output file path.
        url: Optional URL filter.
        title: Optional title filter.
        text: Optional title/content search.
        limit: Optional item limit.

    Returns:
        ExportResult with exported data info.

    Raises:
        ExportError: If export fails.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem
    from sqlalchemy import or_

    db = next(get_db())

    spider_query = db.query(Spider).filter(Spider.project == project)
    if spider:
        spider_query = spider_query.filter(Spider.name == spider)

    spiders = spider_query.all()
    spider_ids = [s.id for s in spiders]

    if not spider_ids:
        return ExportResult(
            spider=spider,
            project=project,
            format=fmt,
            item_count=0,
            output_path=output_path,
            data=None,
        )

    query = db.query(ScrapedItem).filter(ScrapedItem.spider_id.in_(spider_ids))

    if url:
        query = query.filter(ScrapedItem.url.ilike(f"%{url}%"))
    if title:
        query = query.filter(ScrapedItem.title.ilike(f"%{title}%"))
    if text:
        query = query.filter(
            or_(
                ScrapedItem.title.ilike(f"%{text}%"),
                ScrapedItem.content.ilike(f"%{text}%"),
            )
        )

    if limit:
        items = query.order_by(ScrapedItem.scraped_at.desc()).limit(limit).all()
    else:
        items = query.order_by(ScrapedItem.scraped_at.desc()).all()

    spider_map = {s.id: s for s in spiders}

    items_data = []
    for item in items:
        spider_obj = spider_map.get(item.spider_id)
        callbacks_config = spider_obj.callbacks_config if spider_obj else {}

        callback_name = None
        if item.metadata_json and isinstance(item.metadata_json, dict):
            callback_name = item.metadata_json.get("_callback")

        row = {
            "id": item.id,
            "url": item.url,
            "scraped_at": item.scraped_at.isoformat() if item.scraped_at else None,
        }

        if callback_name and callbacks_config:
            row["callback"] = callback_name
            extract_config = callbacks_config.get(callback_name, {}).get("extract", {})
            for field_name in extract_config.keys():
                if field_name == "title":
                    row[field_name] = item.title
                elif field_name == "content":
                    row[field_name] = item.content
                elif field_name == "author":
                    row[field_name] = item.author
                elif field_name == "published_date":
                    row[field_name] = (
                        item.published_date.isoformat() if item.published_date else None
                    )
                else:
                    row[field_name] = (
                        item.metadata_json.get(field_name)
                        if item.metadata_json
                        else None
                    )
        else:
            row["title"] = item.title
            row["content"] = item.content
            row["author"] = item.author
            row["published_date"] = (
                item.published_date.isoformat() if item.published_date else None
            )

        if item.metadata_json:
            row["metadata"] = item.metadata_json

        items_data.append(row)

    if not output_path:
        timestamp = datetime.now().strftime("%d%m%Y_%H%M%S")
        if spider:
            output_dir = Path(DATA_DIR) / project / spider / "exports"
        else:
            output_dir = Path(DATA_DIR) / project / "exports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"export_{timestamp}.{fmt}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    data_bytes = None

    try:
        if fmt == "csv":
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                if items_data:
                    all_fields = set()
                    for row in items_data:
                        all_fields.update(row.keys())

                    standard_fields = [
                        "id",
                        "url",
                        "title",
                        "content",
                        "author",
                        "published_date",
                        "scraped_at",
                        "callback",
                        "metadata",
                    ]
                    ordered_fields = [f for f in standard_fields if f in all_fields]
                    custom_fields = sorted(all_fields - set(standard_fields))
                    fieldnames = ordered_fields + custom_fields

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(items_data)

        elif fmt == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(items_data, f, indent=2, ensure_ascii=False)

        elif fmt == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for item in items_data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        elif fmt == "parquet":
            try:
                import pandas as pd

                df = pd.DataFrame(items_data)
                df.to_parquet(output_path, index=False)
            except ImportError:
                raise ExportError(
                    "Parquet export requires pandas and pyarrow libraries."
                )

    except ExportError:
        raise
    except Exception as e:
        raise ExportError(f"Export failed: {e}")

    return ExportResult(
        spider=spider,
        project=project,
        format=fmt,
        item_count=len(items_data),
        output_path=output_path,
        data=data_bytes,
    )
