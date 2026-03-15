"""Crawl service - running spiders."""

import subprocess
import sys
import os
import shutil
import pickle
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.config import DATA_DIR
from scrapai.exceptions import SpiderNotFoundError, CrawlError


class CrawlResult(BaseModel):
    """Result of a crawl operation."""

    spider: str
    project: str
    item_count: int
    duration_ms: int
    success: bool
    error: str | None = None
    started_at: datetime
    finished_at: datetime


def crawl(
    spider: str,
    project: str | None = None,
    limit: int | None = None,
    concurrency: int | None = None,
    proxy_type: str = "auto",
    browser: bool = False,
    scrapy_args: str | None = None,
    reset_deltafetch: bool = False,
    save_html: bool = False,
) -> CrawlResult:
    """Run a spider.

    Args:
        spider: Spider name.
        project: Project name.
        limit: Limit number of items (test mode).
        concurrency: Concurrency setting.
        proxy_type: Proxy type (auto, datacenter, residential).
        browser: Use browser mode.
        scrapy_args: Additional Scrapy arguments.
        reset_deltafetch: Clear DeltaFetch cache.
        save_html: Save raw HTML in output.

    Returns:
        CrawlResult with crawl details.

    Raises:
        SpiderNotFoundError: If spider not found.
    """
    from core.db import get_db
    from core.models import Spider, ScrapedItem
    from sqlalchemy import func

    db = next(get_db())
    db_spider = db.query(Spider).filter(Spider.name == spider).first()

    if not db_spider:
        db.close()
        raise SpiderNotFoundError(spider, project)

    spider_settings = list(db_spider.settings) if db_spider.settings else []

    if project is None:
        project = db_spider.project or "default"

    db.close()

    started_at = datetime.now()

    result = _run_spider(
        project_name=project,
        spider_name=spider,
        limit=limit,
        proxy_type=proxy_type,
        browser=browser,
        scrapy_args=scrapy_args,
        reset_deltafetch=reset_deltafetch,
        save_html=save_html,
    )

    finished_at = datetime.now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    db = next(get_db())
    item_count = (
        db.query(func.count(ScrapedItem.id))
        .join(Spider)
        .filter(Spider.name == spider, Spider.project == project)
        .scalar()
    ) or 0
    db.close()

    return CrawlResult(
        spider=spider,
        project=project,
        item_count=item_count,
        duration_ms=duration_ms,
        success=result.returncode == 0,
        error=None if result.returncode == 0 else f"Exit code: {result.returncode}",
        started_at=started_at,
        finished_at=finished_at,
    )


def crawl_all(
    project: str,
    limit: int | None = None,
    concurrency: int = 4,
) -> list[CrawlResult]:
    """Run all spiders in a project.

    Args:
        project: Project name.
        limit: Limit items per spider.
        concurrency: Concurrency setting.

    Returns:
        List of CrawlResult for each spider.
    """
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    spiders = (
        db.query(Spider)
        .filter(Spider.project == project, Spider.active.is_(True))
        .all()
    )
    db.close()

    results = []
    for s in spiders:
        result = crawl(
            spider=s.name, project=project, limit=limit, concurrency=concurrency
        )
        results.append(result)

    return results


def _run_spider(
    project_name: str,
    spider_name: str,
    limit: int | None = None,
    proxy_type: str = "datacenter",
    browser: bool = False,
    scrapy_args: str | None = None,
    reset_deltafetch: bool = False,
    save_html: bool = False,
) -> subprocess.CompletedProcess:
    """Internal function to run a Scrapy spider."""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    db_spider = db.query(Spider).filter(Spider.name == spider_name).first()
    spider_settings = list(db_spider.settings) if db_spider.settings else []
    db.close()

    if reset_deltafetch:
        if project_name:
            deltafetch_db = Path(f".scrapy/deltafetch/{project_name}/{spider_name}.db")
        else:
            deltafetch_db = Path(f".scrapy/deltafetch/{spider_name}.db")

        if deltafetch_db.exists():
            deltafetch_db.unlink()

        if project_name:
            checkpoint_path = Path(DATA_DIR) / project_name / spider_name / "checkpoint"
        else:
            checkpoint_path = Path(DATA_DIR) / spider_name / "checkpoint"

        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)

    cf_enabled = browser
    use_sitemap = False
    if spider_settings:
        for setting in spider_settings:
            if setting.key in ["CLOUDFLARE_ENABLED", "BROWSER_ENABLED"]:
                if str(setting.value).lower() in ["true", "1"]:
                    cf_enabled = True
            if setting.key == "USE_SITEMAP":
                if str(setting.value).lower() in ["true", "1"]:
                    use_sitemap = True

    if use_sitemap:
        spider_class = "sitemap_database_spider"
    else:
        spider_class = "database_spider"

    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        spider_class,
        "-a",
        f"spider_name={spider_name}",
    ]

    cmd.extend(["-s", f"PROXY_TYPE={proxy_type}"])

    if project_name:
        deltafetch_dir = f"deltafetch/{project_name}"
        cmd.extend(["-s", f"DELTAFETCH_DIR={deltafetch_dir}"])

    if browser:
        cmd.extend(["-s", "CLOUDFLARE_ENABLED=True"])

    if save_html:
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=True"])
    else:
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=False"])

    if limit:
        cmd.extend(["-s", f"CLOSESPIDER_ITEMCOUNT={limit}"])
    else:
        cmd.extend(["-s", 'ITEM_PIPELINES={"pipelines.ScrapaiPipeline": 300}'])

        if project_name:
            checkpoint_dir = str(
                Path(DATA_DIR) / project_name / spider_name / "checkpoint"
            )
        else:
            checkpoint_dir = str(Path(DATA_DIR) / spider_name / "checkpoint")

        requests_seen = Path(checkpoint_dir) / "requests.seen"
        requests_queue = list(Path(checkpoint_dir).glob("requests.queue*"))

        if requests_seen.exists() and not requests_queue:
            requests_seen.unlink()

        cmd.extend(["-s", f"JOBDIR={checkpoint_dir}"])

    if scrapy_args:
        extra_args = shlex.split(scrapy_args)
        cmd.extend(extra_args)

    result = subprocess.run(cmd)
    return result
