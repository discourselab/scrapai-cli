import click


@click.command()
@click.argument('spider_name')
@click.option('--project', required=True, help='Project name (required)')
@click.option('--limit', '-l', type=int, default=5, help='Number of articles to show (default: 5)')
@click.option('--url', default=None, help='Filter by URL pattern')
@click.option('--text', '-t', default=None, help='Search title or content')
@click.option('--title', default=None, help='Search titles only')
def show(spider_name, project, limit, url, text, title):
    """Show scraped articles from database"""
    from core.db import get_db
    from core.models import Spider, ScrapedItem

    db = next(get_db())

    spider = db.query(Spider).filter(
        Spider.name == spider_name,
        Spider.project == project
    ).first()

    if not spider:
        click.echo(f"❌ Spider '{spider_name}' not found in project '{project}'")
        return

    query = db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id)

    filters_applied = []
    if url:
        query = query.filter(ScrapedItem.url.ilike(f'%{url}%'))
        filters_applied.append(f"URL contains '{url}'")
    if title:
        query = query.filter(ScrapedItem.title.ilike(f'%{title}%'))
        filters_applied.append(f"title contains '{title}'")
    if text:
        from sqlalchemy import or_
        query = query.filter(or_(
            ScrapedItem.title.ilike(f'%{text}%'),
            ScrapedItem.content.ilike(f'%{text}%')
        ))
        filters_applied.append(f"title or content contains '{text}'")

    items = query.order_by(ScrapedItem.scraped_at.desc()).limit(limit).all()

    if not items:
        click.echo(f"📭 No articles found for spider '{spider_name}'")
        if filters_applied:
            click.echo(f"   (with filters: {', '.join(filters_applied)})")
        return

    click.echo(f"📰 Showing {len(items)} articles from '{spider_name}':")
    if filters_applied:
        click.echo(f"   (filtered by: {', '.join(filters_applied)})")
    click.echo()

    for i, item in enumerate(items, 1):
        scraped_date = item.scraped_at.strftime('%Y-%m-%d %H:%M') if item.scraped_at else 'Unknown'
        pub_date = item.published_date.strftime('%Y-%m-%d') if item.published_date else 'Unknown'

        click.echo(f"🔸 [{i}] {item.title or 'No Title'}")
        click.echo(f"   📅 Published: {pub_date} | Scraped: {scraped_date}")
        click.echo(f"   🔗 {item.url}")
        if item.author:
            click.echo(f"   ✍️  {item.author}")
        if item.content:
            content_preview = item.content[:150].replace('\n', ' ').strip()
            if len(item.content) > 150:
                content_preview += "..."
            click.echo(f"   📝 {content_preview}")
        click.echo()
