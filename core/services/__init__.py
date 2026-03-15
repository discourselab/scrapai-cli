"""Core services package - shared logic layer between CLI and library.

This module uses lazy imports to avoid circular import issues.
"""

__all__ = [
    "setup",
    "verify",
    "SetupResult",
    "VerifyResult",
    "list_projects",
    "inspect_url",
    "list_spiders",
    "get_spider",
    "import_spider",
    "export_spider",
    "delete_spider",
    "SpiderInfo",
    "GenerateSpiderResult",
    "ProjectInfo",
    "InspectionResult",
    "crawl",
    "crawl_all",
    "CrawlResult",
    "show_items",
    "export_items",
    "ItemsResult",
    "ExportResult",
    "health_check",
    "health_check_spider",
    "HealthReport",
    "SpiderHealthResult",
    "queue_add",
    "queue_bulk",
    "queue_list",
    "queue_process",
    "QueueItem",
    "BatchResult",
    "FailedQueueItem",
    "db_stats",
    "db_query",
    "DbStats",
]


def __getattr__(name: str):
    """Lazy import of services to avoid circular imports."""
    if name in ("setup", "verify", "SetupResult", "VerifyResult"):
        from core.services.setup_service import setup, verify, SetupResult, VerifyResult

        return locals()[name]
    elif name == "list_projects":
        from core.services.project_service import list_projects

        return list_projects
    elif name == "inspect_url":
        from core.services.inspection_service import inspect_url

        return inspect_url
    elif name in (
        "list_spiders",
        "get_spider",
        "import_spider",
        "export_spider",
        "delete_spider",
        "SpiderInfo",
        "GenerateSpiderResult",
    ):
        from core.services import spiders_service

        return getattr(spiders_service, name)
    elif name in ("crawl", "crawl_all", "CrawlResult"):
        from core.services import crawl_service

        return getattr(crawl_service, name)
    elif name in ("show_items", "export_items", "ItemsResult", "ExportResult"):
        from core.services import data_service

        return getattr(data_service, name)
    elif name in (
        "health_check",
        "health_check_spider",
        "HealthReport",
        "SpiderHealthResult",
    ):
        from core.services import health_service

        return getattr(health_service, name)
    elif name in (
        "queue_add",
        "queue_bulk",
        "queue_list",
        "queue_process",
        "QueueItem",
        "BatchResult",
        "FailedQueueItem",
    ):
        from core.services import queue_service

        return getattr(queue_service, name)
    elif name in ("db_stats", "db_query", "DbStats"):
        from core.services import db_service

        return getattr(db_service, name)
    elif name in ("ProjectInfo", "InspectionResult"):
        from core.services import models

        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
