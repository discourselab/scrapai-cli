import click
import json
import sys


@click.group()
def spiders():
    """Spider management"""
    pass


@spiders.command('list')
@click.option('--project', default=None, help='Filter by project name (default: show all)')
def list_spiders(project):
    """List all spiders in DB"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())

    query = db.query(Spider)
    if project:
        query = query.filter(Spider.project == project)
        click.echo(f"📋 Available Spiders (DB) - Project: {project}:")
    else:
        click.echo("📋 Available Spiders (DB) - All Projects:")

    spiders = query.all()
    if spiders:
        for s in spiders:
            created = s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else 'Unknown'
            updated = s.updated_at.strftime('%Y-%m-%d %H:%M') if s.updated_at else created
            project_tag = f"[{s.project}]" if s.project else "[default]"

            click.echo(f"  • {s.name} {project_tag} (Active: {s.active}) - Created: {created}, Updated: {updated}")
            if s.source_url:
                click.echo(f"    Source: {s.source_url}")
    else:
        if project:
            click.echo(f"No spiders found in project '{project}'.")
        else:
            click.echo("No spiders found in database.")


@spiders.command('import')
@click.argument('file')
@click.option('--project', default='default', help='Project name (default: default)')
def import_spider(file, project):
    """Import spider from JSON file (use "-" for stdin)"""
    from core.db import get_db
    from core.models import Spider, SpiderRule, SpiderSetting

    db = next(get_db())

    try:
        if file == '-':
            data = json.load(sys.stdin)
        else:
            with open(file, 'r') as f:
                data = json.load(f)

        if 'source_url' not in data or not data['source_url']:
            click.echo("❌ Error: 'source_url' is required in spider JSON")
            click.echo('   Add the original website URL: "source_url": "https://example.com"')
            return

        existing = db.query(Spider).filter(Spider.name == data['name']).first()
        if existing:
            click.echo(f"⚠️  Spider '{data['name']}' already exists. Updating...")
            existing.allowed_domains = data['allowed_domains']
            existing.start_urls = data['start_urls']
            existing.source_url = data.get('source_url')
            existing.project = project

            db.query(SpiderRule).filter(SpiderRule.spider_id == existing.id).delete()
            db.query(SpiderSetting).filter(SpiderSetting.spider_id == existing.id).delete()
            spider = existing
        else:
            spider = Spider(
                name=data['name'],
                allowed_domains=data['allowed_domains'],
                start_urls=data['start_urls'],
                source_url=data.get('source_url'),
                project=project
            )
            db.add(spider)
            db.flush()

        for r_data in data.get('rules', []):
            rule = SpiderRule(
                spider_id=spider.id,
                allow_patterns=r_data.get('allow'),
                deny_patterns=r_data.get('deny'),
                restrict_xpaths=r_data.get('restrict_xpaths'),
                restrict_css=r_data.get('restrict_css'),
                callback=r_data.get('callback'),
                follow=r_data.get('follow', True),
                priority=r_data.get('priority', 0)
            )
            db.add(rule)

        for k, v in data.get('settings', {}).items():
            setting = SpiderSetting(
                spider_id=spider.id,
                key=k,
                value=str(v),
                type=type(v).__name__
            )
            db.add(setting)

        db.commit()
        click.echo(f"✅ Spider '{spider.name}' imported successfully!")

    except Exception as e:
        db.rollback()
        click.echo(f"❌ Error importing spider: {e}")


@spiders.command('delete')
@click.argument('name')
@click.option('--project', default=None, help='Project name')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
def delete_spider(name, project, force):
    """Delete a spider"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    query = db.query(Spider).filter(Spider.name == name)

    if project:
        query = query.filter(Spider.project == project)
        project_msg = f" in project '{project}'"
    else:
        project_msg = ""

    spider = query.first()

    if spider:
        if not force:
            confirm = input(f"Are you sure you want to delete spider '{name}'{project_msg}? (y/N): ")
            if confirm.lower() != 'y':
                click.echo("❌ Delete cancelled")
                return

        db.delete(spider)
        db.commit()
        click.echo(f"🗑️  Spider '{name}'{project_msg} deleted!")
    else:
        click.echo(f"❌ Spider '{name}'{project_msg} not found.")
