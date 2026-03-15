"""Validation and test crawl helpers for generated spiders."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from core.schemas import SpiderConfigSchema


def validate_config(data: Dict) -> SpiderConfigSchema:
    return SpiderConfigSchema(**data)


def run_test_crawl(spider_name: str, project: str, limit: int = 3) -> int:
    """Run a test crawl and return number of items scraped since start."""
    from cli.crawl import _run_spider
    from core.db import get_db
    from core.models import Spider, ScrapedItem

    db = next(get_db())
    try:
        spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
        )
        if not spider:
            return 0
        initial_count = (
            db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id).count()
        )
    finally:
        db.close()

    _run_spider(
        project_name=project,
        spider_name=spider_name,
        output_file=None,
        limit=limit,
        timeout=None,
        proxy_type="auto",
        browser=False,
        scrapy_args=None,
        reset_deltafetch=True,
        save_html=False,
    )

    db = next(get_db())
    try:
        spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project)
            .first()
        )
        if not spider:
            return 0

        count = db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id).count()
        return int(count - initial_count)
    finally:
        db.close()
