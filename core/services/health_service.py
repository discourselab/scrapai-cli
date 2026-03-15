"""Health service - spider health checks."""

import subprocess
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from scrapai.exceptions import SpiderNotFoundError


class SpiderHealthResult(BaseModel):
    """Health check result for a single spider."""

    spider: str
    passing: bool
    item_count: int
    failure_type: str | None = None
    error: str | None = None
    duration_ms: int


class HealthReport(BaseModel):
    """Health check report for a project."""

    project: str
    total_spiders: int
    passing: int
    failing: int
    results: list[SpiderHealthResult]
    checked_at: datetime


def health_check(
    project: str,
    sample_size: int = 5,
    min_content_length: int = 50,
) -> HealthReport:
    """Run health check on all spiders in project.

    Args:
        project: Project name.
        sample_size: Number of items to test per spider.
        min_content_length: Minimum content length for passing.

    Returns:
        HealthReport with per-spider results.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem

    db = next(get_db())

    spiders = (
        db.query(Spider)
        .filter(Spider.project == project, Spider.active == True)
        .order_by(Spider.name)
        .all()
    )

    results = []
    for spider in spiders:
        result = _test_spider(spider.name, project, sample_size, min_content_length)
        results.append(result)

    passing = sum(1 for r in results if r.passing)
    failing = len(results) - passing

    return HealthReport(
        project=project,
        total_spiders=len(results),
        passing=passing,
        failing=failing,
        results=results,
        checked_at=datetime.now(),
    )


def health_check_spider(
    name: str,
    project: str,
    sample_size: int = 5,
    min_content_length: int = 50,
) -> SpiderHealthResult:
    """Run health check on a single spider.

    Args:
        name: Spider name.
        project: Project name.
        sample_size: Number of items to test.
        min_content_length: Minimum content length for passing.

    Returns:
        SpiderHealthResult.

    Raises:
        SpiderNotFoundError: If spider not found.
    """
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())

    spider = (
        db.query(Spider).filter(Spider.name == name, Spider.project == project).first()
    )

    if not spider:
        raise SpiderNotFoundError(name, project)

    return _test_spider(name, project, sample_size, min_content_length)


def _test_spider(
    spider_name: str,
    project: str,
    limit: int,
    min_content_length: int,
) -> SpiderHealthResult:
    """Internal function to test a spider."""
    from core.db import get_db
    from core.models import ScrapedItem

    start_time = datetime.now()

    try:
        cmd = [
            "python",
            "-m",
            "scrapy",
            "crawl",
            "database_spider",
            "-a",
            f"spider_name={spider_name}",
            "-s",
            f"CLOSESPIDER_ITEMCOUNT={limit}",
        ]

        subprocess.run(cmd, capture_output=True, timeout=300)

        db = next(get_db())
        try:
            items = (
                db.query(ScrapedItem)
                .filter(ScrapedItem.spider_name == spider_name)
                .order_by(ScrapedItem.scraped_at.desc())
                .limit(limit)
                .all()
            )

            item_count = len(items)

            if item_count < 3:
                return SpiderHealthResult(
                    spider=spider_name,
                    passing=False,
                    item_count=item_count,
                    failure_type="crawling",
                    error=f"Only {item_count} items found (expected {limit})",
                    duration_ms=int(
                        (datetime.now() - start_time).total_seconds() * 1000
                    ),
                )

            sample = items[0]
            content_length = len(sample.content) if sample.content else 0

            if content_length < min_content_length:
                return SpiderHealthResult(
                    spider=spider_name,
                    passing=False,
                    item_count=item_count,
                    failure_type="extraction",
                    error=f"Content too short ({content_length} chars)",
                    duration_ms=int(
                        (datetime.now() - start_time).total_seconds() * 1000
                    ),
                )

            return SpiderHealthResult(
                spider=spider_name,
                passing=True,
                item_count=item_count,
                failure_type=None,
                error=None,
                duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
            )
        finally:
            db.close()

    except Exception as e:
        return SpiderHealthResult(
            spider=spider_name,
            passing=False,
            item_count=0,
            failure_type="error",
            error=str(e),
            duration_ms=int((datetime.now() - start_time).total_seconds() * 1000),
        )
