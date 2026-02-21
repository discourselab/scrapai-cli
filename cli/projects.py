import click


@click.group()
def projects():
    """Project management"""
    pass


@projects.command('list')
def list_projects():
    """List all projects"""
    from core.db import get_db
    from core.models import Spider, CrawlQueue
    from sqlalchemy import func, distinct

    db = next(get_db())

    spider_projects = db.query(distinct(Spider.project)).filter(Spider.project.isnot(None)).all()
    queue_projects = db.query(distinct(CrawlQueue.project_name)).filter(CrawlQueue.project_name.isnot(None)).all()

    all_projects = set()
    for (proj,) in spider_projects:
        all_projects.add(proj)
    for (proj,) in queue_projects:
        all_projects.add(proj)

    if all_projects:
        click.echo("📁 Available Projects:")
        for proj in sorted(all_projects):
            spider_count = db.query(func.count(Spider.id)).filter(Spider.project == proj).scalar()
            queue_count = db.query(func.count(CrawlQueue.id)).filter(CrawlQueue.project_name == proj).scalar()
            click.echo(f"  • {proj}")
            click.echo(f"    Spiders: {spider_count}, Queue items: {queue_count}")
    else:
        click.echo("No projects found.")
