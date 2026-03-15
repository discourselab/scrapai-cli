"""Core services package - shared logic layer between CLI and library."""

from core.services.setup_service import setup, verify, SetupResult, VerifyResult
from core.services.spiders_service import (
    list_spiders,
    get_spider,
    import_spider,
    export_spider,
    delete_spider,
    SpiderInfo,
    GenerateSpiderResult,
)
from core.services.crawl_service import crawl, crawl_all, CrawlResult
from core.services.data_service import (
    show_items,
    export_items,
    ItemsResult,
    ExportResult,
)
from core.services.health_service import (
    health_check,
    health_check_spider,
    HealthReport,
    SpiderHealthResult,
)
from core.services.queue_service import (
    queue_add,
    queue_bulk,
    queue_list,
    queue_process,
    QueueItem,
    BatchResult,
    FailedQueueItem,
)
from core.services.db_service import db_stats, db_query, DbStats

__all__ = [
    "setup",
    "verify",
    "SetupResult",
    "VerifyResult",
    "list_spiders",
    "get_spider",
    "import_spider",
    "export_spider",
    "delete_spider",
    "SpiderInfo",
    "GenerateSpiderResult",
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
