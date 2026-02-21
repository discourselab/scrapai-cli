import click
import json
import csv
from pathlib import Path
from datetime import datetime
from core.config import DATA_DIR


@click.command()
@click.argument('spider_name')
@click.option('--project', default=None, help='Project name')
@click.option('--format', '-f', 'fmt', required=True,
              type=click.Choice(['csv', 'json', 'jsonl', 'parquet']), help='Export format')
@click.option('--output', '-o', default=None, help='Output file path')
@click.option('--limit', '-l', type=int, default=None, help='Limit number of articles')
@click.option('--url', default=None, help='Filter by URL pattern')
@click.option('--text', '-t', default=None, help='Search title or content')
@click.option('--title', default=None, help='Search titles only')
def export(spider_name, project, fmt, output, limit, url, text, title):
    """Export scraped articles from database"""
    from core.db import get_db
    from core.models import Spider, ScrapedItem

    db = next(get_db())

    query = db.query(Spider).filter(Spider.name == spider_name)
    if project:
        query = query.filter(Spider.project == project)
        project_msg = f" in project '{project}'"
    else:
        project_msg = ""

    spider = query.first()
    if not spider:
        click.echo(f"❌ Spider '{spider_name}'{project_msg} not found in database.")
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

    if limit:
        items = query.order_by(ScrapedItem.scraped_at.desc()).limit(limit).all()
    else:
        items = query.order_by(ScrapedItem.scraped_at.desc()).all()

    if not items:
        click.echo(f"📭 No articles found for spider '{spider_name}'")
        if filters_applied:
            click.echo(f"   (with filters: {', '.join(filters_applied)})")
        return

    if output:
        output_path = Path(output)
    else:
        timestamp = datetime.now().strftime('%d%m%Y_%H%M%S')

        if project:
            output_dir = Path(DATA_DIR) / project / spider_name / 'exports'
        else:
            output_dir = Path(DATA_DIR) / spider_name / 'exports'

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"export_{timestamp}.{fmt}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    items_data = []
    for item in items:
        items_data.append({
            'id': item.id,
            'url': item.url,
            'title': item.title,
            'content': item.content,
            'author': item.author,
            'published_date': item.published_date.isoformat() if item.published_date else None,
            'scraped_at': item.scraped_at.isoformat() if item.scraped_at else None,
            'metadata': item.metadata_json
        })

    try:
        if fmt == 'csv':
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if items_data:
                    writer = csv.DictWriter(f, fieldnames=items_data[0].keys())
                    writer.writeheader()
                    writer.writerows(items_data)
            click.echo(f"✅ Exported {len(items_data)} articles to CSV: {output_path}")
        elif fmt == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(items_data, f, indent=2, ensure_ascii=False)
            click.echo(f"✅ Exported {len(items_data)} articles to JSON: {output_path}")
        elif fmt == 'jsonl':
            with open(output_path, 'w', encoding='utf-8') as f:
                for item in items_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            click.echo(f"✅ Exported {len(items_data)} articles to JSONL: {output_path}")
        elif fmt == 'parquet':
            try:
                import pandas as pd
                df = pd.DataFrame(items_data)
                df.to_parquet(output_path, index=False)
                click.echo(f"✅ Exported {len(items_data)} articles to Parquet: {output_path}")
            except ImportError:
                click.echo("❌ Parquet export requires pandas and pyarrow libraries.")
                click.echo("   Run: pip install pandas pyarrow")
                return

        if filters_applied:
            click.echo(f"   (filtered by: {', '.join(filters_applied)})")

    except Exception as e:
        click.echo(f"❌ Error exporting data: {e}")
