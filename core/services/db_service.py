"""Database service - database operations."""

import re
from typing import Any

from pydantic import BaseModel

from core.services.models import ProjectInfo
from scrapai.exceptions import QueryNotAllowedError


class DbStats(BaseModel):
    """Database statistics."""

    total_spiders: int
    total_items: int
    db_size_bytes: int
    projects: list[ProjectInfo]


def db_stats() -> DbStats:
    """Get database statistics.

    Returns:
        DbStats with counts.
    """
    from core.db import get_db
    from sqlalchemy import text, func
    from core.models import Spider, CrawlQueue

    db = next(get_db())

    spider_count = db.execute(text("SELECT COUNT(*) FROM spiders")).scalar() or 0
    item_count = db.execute(text("SELECT COUNT(*) FROM scraped_items")).scalar() or 0

    project_count = (
        db.query(func.count(func.distinct(Spider.project)))
        .filter(Spider.project.isnot(None))
        .scalar()
    ) or 0

    try:
        db_size = (
            db.execute(
                text(
                    "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
                )
            ).scalar()
            or 0
        )
    except Exception:
        db_size = 0

    spider_projects = (
        db.query(Spider.project, func.count(Spider.id))
        .filter(Spider.project.isnot(None))
        .group_by(Spider.project)
        .all()
    )

    projects = [ProjectInfo(name=p[0], spider_count=p[1]) for p in spider_projects]

    return DbStats(
        total_spiders=spider_count,
        total_items=item_count,
        db_size_bytes=db_size,
        projects=projects,
    )


def db_query(sql: str) -> list[dict]:
    """Execute a read-only SQL query.

    Args:
        sql: SQL SELECT query.

    Returns:
        List of result rows as dicts.

    Raises:
        QueryNotAllowedError: If query is not a SELECT.
    """
    from core.db import get_db
    from sqlalchemy import text

    sql_upper = sql.strip().upper()

    if not sql_upper.startswith("SELECT"):
        raise QueryNotAllowedError()

    db = next(get_db())
    result = db.execute(text(sql))
    rows = result.fetchall()

    return [dict(zip(result.keys(), row)) for row in rows]
