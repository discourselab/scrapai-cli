"""Project service - project management."""

from core.services.models import ProjectInfo


def list_projects() -> list[ProjectInfo]:
    """List all projects in the database.

    Returns:
        List of ProjectInfo objects.
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
        result.append(ProjectInfo(name=proj, spider_count=spider_count))

    return result
