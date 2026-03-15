"""ScrapAI Python Library API.

This module provides a programmatic interface to ScrapAI, allowing you to:
- Manage spiders and projects
- Run crawls
- Retrieve and export scraped data
- Monitor spider health
- Process queue items

Example usage:
    from scrapai import setup, list_spiders, crawl, show_items

    setup()
    spiders = list_spiders(project="news")
    result = crawl(spider="bbc_co_uk", project="news", limit=10)
    items = show_items(spider="bbc_co_uk", project="news", limit=5)
"""

from pathlib import Path
from datetime import datetime
from typing import Any

from core.services import (
    setup as _setup,
    verify as _verify,
    SetupResult,
    VerifyResult,
    list_spiders,
    get_spider,
    import_spider,
    export_spider,
    delete_spider,
    SpiderInfo,
    GenerateSpiderResult,
    crawl,
    crawl_all,
    CrawlResult,
    show_items,
    export_items,
    ItemsResult,
    ExportResult,
    health_check,
    health_check_spider,
    HealthReport,
    SpiderHealthResult,
    queue_add,
    queue_bulk,
    queue_list,
    queue_process,
    QueueItem,
    BatchResult,
    FailedQueueItem,
    db_stats,
    db_query,
    DbStats,
)
from scrapai.exceptions import (
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


def setup() -> SetupResult:
    """Initialize .env, database, and DATA_DIR.

    Mirrors ./scrapai setup.

    Returns:
        SetupResult with operation status and details.
    """
    return _setup()


def verify() -> VerifyResult:
    """Verify environment is correctly configured.

    Mirrors ./scrapai verify.

    Returns:
        VerifyResult with check results and any errors.
    """
    return _verify()


def list_projects() -> list[dict]:
    """List all projects in the database.

    Returns:
        List of project info dicts with name, spider_count.
    """
    from core.db import get_db
    from core.models import Spider, CrawlQueue
    from sqlalchemy import func, distinct

    db = next(get_db())

    spider_projects = (
        db.query(distinct(Spider.project)).filter(Spider.project.isnot(None)).all()
    )
    queue_projects = (
        db.query(distinct(CrawlQueue.project_name))
        .filter(CrawlQueue.project_name.isnot(None))
        .all()
    )

    all_projects = set()
    for (proj,) in spider_projects:
        all_projects.add(proj)
    for (proj,) in queue_projects:
        all_projects.add(proj)

    result = []
    for proj in sorted(all_projects):
        spider_count = (
            db.query(func.count(Spider.id)).filter(Spider.project == proj).scalar()
        ) or 0
        result.append({"name": proj, "spider_count": spider_count})

    return result


def generate_spider(
    url: str,
    project: str,
    description: str | None = None,
    llm_api: str | None = None,
    llm_key: str | None = None,
    llm_model: str | None = None,
    llm_fallback: list[dict] | None = None,
    dry_run: bool = False,
    output: Path | None = None,
) -> GenerateSpiderResult:
    """Generate + import a spider via LLM pipeline.

    Mirrors ./scrapai add command (PRD-001).

    Args:
        url: Target website URL.
        project: Project name.
        description: Description of what to extract.
        llm_api: LLM API base URL (falls back to SCRAPAI_LLM_API env var).
        llm_key: LLM API key (falls back to SCRAPAI_LLM_KEY env var).
        llm_model: LLM model name (falls back to SCRAPAI_LLM_MODEL env var).
        llm_fallback: Fallback LLM configs to try on failure.
        dry_run: If True, skip import and test crawl.
        output: Optional path to save spider config.

    Returns:
        GenerateSpiderResult with spider details.

    Raises:
        LLMNotConfiguredError: If LLM not configured.
        GenerationFailedError: If generation fails.
    """
    import asyncio
    from generate.pipeline import resolve_llm_config, run_add_pipeline

    try:
        llm = resolve_llm_config(llm_api, llm_key, llm_model, None)
    except ValueError as e:
        raise LLMNotConfiguredError(str(e))

    async def run():
        result = await run_add_pipeline(
            url=url,
            project=project,
            description=description or "",
            llm=llm,
            dry_run=dry_run,
            output_path=output,
            backup=True,
        )
        return result

    result = asyncio.run(run())

    if not result.success:
        raise GenerationFailedError(url, result.error)

    return GenerateSpiderResult(
        name=result.spider_name,
        project=project,
        config=result.config,
        imported=not dry_run,
        generated_at=datetime.now(),
        test_crawl_item_count=result.test_item_count if not dry_run else None,
    )


def repair_spider(
    name: str,
    project: str,
    llm_api: str | None = None,
    llm_key: str | None = None,
    llm_model: str | None = None,
) -> GenerateSpiderResult:
    """Re-generate a broken spider's config using LLM.

    Fetches existing spider's URL + description, runs full generation pipeline.

    Args:
        name: Spider name to repair.
        project: Project name.
        llm_api: LLM API base URL.
        llm_key: LLM API key.
        llm_model: LLM model name.

    Returns:
        GenerateSpiderResult with new spider details.

    Raises:
        SpiderNotFoundError: If spider not found.
        LLMNotConfiguredError: If LLM not configured.
        GenerationFailedError: If generation fails.
    """
    spider_info = get_spider(name, project)

    url = spider_info.config.get("source_url")
    if not url:
        raise GenerationFailedError(url, "Spider has no source_url to repair")

    description = "Repair existing spider - re-extract all content"

    return generate_spider(
        url=url,
        project=project,
        description=description,
        llm_api=llm_api,
        llm_key=llm_key,
        llm_model=llm_model,
    )


def inspect_url(
    url: str,
    browser: bool = False,
) -> dict:
    """Inspect a URL to get page info.

    Mirrors ./scrapai inspect <url>.

    Args:
        url: URL to inspect.
        browser: Use browser mode for JS-rendered sites.

    Returns:
        InspectionResult dict with page details.
    """
    from utils.inspector import inspect_page
    from core.config import get_data_dir
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project = "inspect"
    output_dir = get_data_dir(project) / "inspections" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    if browser:
        raise NotImplementedError("Browser inspection not supported in library API yet")

    inspect_page(url, str(output_dir), "auto", True, mode="http", project=project)

    html_file = output_dir / "page.html"
    selectors_file = output_dir / "selectors.json"

    result = {
        "url": url,
        "output_dir": str(output_dir),
    }

    if html_file.exists():
        result["html_snapshot"] = html_file.read_text()[:5000]

    if selectors_file.exists():
        import json

        result["detected_selectors"] = json.loads(selectors_file.read_text())

    return result


__all__ = [
    "setup",
    "verify",
    "list_projects",
    "list_spiders",
    "get_spider",
    "import_spider",
    "export_spider",
    "delete_spider",
    "generate_spider",
    "repair_spider",
    "crawl",
    "crawl_all",
    "show_items",
    "export_items",
    "health_check",
    "health_check_spider",
    "queue_add",
    "queue_bulk",
    "queue_list",
    "queue_process",
    "db_stats",
    "db_query",
    "inspect_url",
    "SpiderInfo",
    "GenerateSpiderResult",
    "CrawlResult",
    "ItemsResult",
    "ExportResult",
    "HealthReport",
    "SpiderHealthResult",
    "QueueItem",
    "BatchResult",
    "FailedQueueItem",
    "DbStats",
    "SetupResult",
    "VerifyResult",
    "SpiderNotFoundError",
    "ProjectNotFoundError",
    "GenerationFailedError",
    "LLMNotConfiguredError",
    "CrawlError",
    "ExportError",
    "QueryNotAllowedError",
    "ValidationError",
    "ScrapAIConfigError",
]
