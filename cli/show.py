import click


@click.command()
@click.argument("spider_name")
@click.option("--project", required=True, help="Project name (required)")
@click.option(
    "--limit", "-l", type=int, default=5, help="Number of articles to show (default: 5)"
)
@click.option("--url", default=None, help="Filter by URL pattern")
@click.option("--text", "-t", default=None, help="Search title or content")
@click.option("--title", default=None, help="Search titles only")
def show(spider_name, project, limit, url, text, title):
    """Show scraped articles from database"""
    from core.db import get_db
    from core.models import Spider, ScrapedItem

    db = next(get_db())

    spider = (
        db.query(Spider)
        .filter(Spider.name == spider_name, Spider.project == project)
        .first()
    )

    if not spider:
        click.echo(f"❌ Spider '{spider_name}' not found in project '{project}'")
        return

    query = db.query(ScrapedItem).filter(ScrapedItem.spider_id == spider.id)

    filters_applied = []
    if url:
        query = query.filter(ScrapedItem.url.ilike(f"%{url}%"))
        filters_applied.append(f"URL contains '{url}'")
    if title:
        query = query.filter(ScrapedItem.title.ilike(f"%{title}%"))
        filters_applied.append(f"title contains '{title}'")
    if text:
        from sqlalchemy import or_

        query = query.filter(
            or_(
                ScrapedItem.title.ilike(f"%{text}%"),
                ScrapedItem.content.ilike(f"%{text}%"),
            )
        )
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

    # Load spider callbacks config (source of truth for field definitions)
    callbacks_config = spider.callbacks_config or {}

    for i, item in enumerate(items, 1):
        scraped_date = (
            item.scraped_at.strftime("%Y-%m-%d %H:%M") if item.scraped_at else "Unknown"
        )

        # Check if this item was extracted using a callback
        callback_name = (
            item.metadata_json.get("_callback")
            if item.metadata_json and isinstance(item.metadata_json, dict)
            else None
        )

        if callback_name and callback_name in callbacks_config:
            # Callback item: show fields defined in spider config
            click.echo(f"🔸 [{i}] {callback_name} item")
            click.echo(f"   📅 Scraped: {scraped_date}")
            click.echo(f"   🔗 {item.url}")

            # Get field definitions from spider config
            extract_config = callbacks_config[callback_name].get("extract", {})

            # Show only fields defined in spider config (in definition order)
            # Check both database columns (for standard fields) and metadata_json (for custom fields)
            for field_name in extract_config.keys():
                # Standard fields are stored in database columns
                if field_name == "title":
                    field_value = item.title
                elif field_name == "content":
                    field_value = item.content
                elif field_name == "author":
                    field_value = item.author
                elif field_name == "published_date":
                    field_value = (
                        item.published_date.isoformat() if item.published_date else None
                    )
                else:
                    # Custom fields are stored in metadata_json
                    field_value = item.metadata_json.get(field_name)

                # Truncate long values for display
                if isinstance(field_value, str) and len(field_value) > 100:
                    display_value = field_value[:100] + "..."
                elif isinstance(field_value, list):
                    if len(field_value) > 3:
                        display_value = f"[{len(field_value)} items]"
                    elif len(str(field_value)) > 100:
                        display_value = str(field_value)[:100] + "...]"
                    else:
                        display_value = field_value
                else:
                    display_value = field_value
                click.echo(f"   • {field_name}: {display_value}")
        else:
            # Article item: show standard article fields
            pub_date = (
                item.published_date.strftime("%Y-%m-%d")
                if item.published_date
                else "Unknown"
            )

            click.echo(f"🔸 [{i}] {item.title or 'No Title'}")
            click.echo(f"   📅 Published: {pub_date} | Scraped: {scraped_date}")
            click.echo(f"   🔗 {item.url}")
            if item.author:
                click.echo(f"   ✍️  {item.author}")
            if item.content:
                content_preview = item.content[:150].replace("\n", " ").strip()
                if len(item.content) > 150:
                    content_preview += "..."
                click.echo(f"   📝 {content_preview}")

        click.echo()
