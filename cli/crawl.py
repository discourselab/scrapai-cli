import click
import subprocess
import sys
import os
from datetime import datetime


@click.command()
@click.argument('spider')
@click.option('--project', default=None, help='Project name')
@click.option('--output', '-o', default=None, help='Output file path')
@click.option('--limit', '-l', type=int, default=None, help='Limit number of items')
@click.option('--timeout', '-t', type=int, default=None, help='Max runtime in seconds')
def crawl(spider, project, output, limit, timeout):
    """Run a spider"""
    _run_spider(project, spider, output, limit, timeout)


@click.command()
@click.option('--project', required=True, help='Project name')
@click.option('--limit', '-l', type=int, default=None, help='Limit items per spider')
def crawl_all(project, limit):
    """Run all spiders in a project"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    spiders = db.query(Spider).filter(Spider.project == project, Spider.active == True).all()

    if not spiders:
        click.echo(f"❌ No active spiders found for project '{project}'")
        return

    click.echo(f"🚀 Running all spiders for project: {project}")
    click.echo(f"🕷️  Spiders: {', '.join(s.name for s in spiders)}")

    for s in spiders:
        click.echo(f"\n{'='*50}")
        click.echo(f"Running: {s.name}")
        click.echo(f"{'='*50}")
        _run_spider(project, s.name, None, limit)


def _run_spider(project_name, spider_name, output_file=None, limit=None, timeout=None):
    """Run a Scrapy spider from database"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    db_spider = db.query(Spider).filter(Spider.name == spider_name).first()

    if not db_spider:
        click.echo(f"❌ Spider '{spider_name}' not found in database.")
        return

    click.echo(f"🚀 Running DB spider: {spider_name}")

    cf_enabled = False
    use_sitemap = False
    if db_spider.settings:
        for setting in db_spider.settings:
            if setting.key == "CLOUDFLARE_ENABLED" and str(setting.value).lower() in ["true", "1"]:
                cf_enabled = True
            if setting.key == "USE_SITEMAP" and str(setting.value).lower() in ["true", "1"]:
                use_sitemap = True

    if use_sitemap:
        spider_class = 'sitemap_database_spider'
        click.echo(f"🗺️  Using sitemap spider")
    else:
        spider_class = 'database_spider'

    cmd = [sys.executable, '-m', 'scrapy', 'crawl', spider_class, '-a', f'spider_name={spider_name}']

    if limit:
        click.echo(f"🧪 Test mode: Saving to database (limit: {limit} items)")
        click.echo(f"   Use './scrapai show {spider_name}' to verify results")
        cmd.extend(['-s', f'CLOSESPIDER_ITEMCOUNT={limit}'])
        cmd.extend(['-s', 'INCLUDE_HTML_IN_OUTPUT=False'])
    else:
        click.echo(f"📁 Production mode: Exporting to files (database disabled)")
        cmd.extend(['-s', 'ITEM_PIPELINES={"pipelines.ScrapaiPipeline": 300}'])
        cmd.extend(['-s', 'INCLUDE_HTML_IN_OUTPUT=True'])

        if not output_file:
            now = datetime.now()
            date_folder = now.strftime('%Y-%m-%d')
            output_dir = f'data/{spider_name}/{date_folder}'
            os.makedirs(output_dir, exist_ok=True)
            timestamp = now.strftime('%H%M%S')
            output_file = f'{output_dir}/crawl_{timestamp}.jsonl'

        cmd.extend(['-o', output_file])
        click.echo(f"   Output: {output_file} (includes HTML)")

    if output_file and limit:
        cmd.extend(['-o', output_file])
        click.echo(f"   Also saving to: {output_file}")

    if timeout:
        cmd.extend(['-s', f'CLOSESPIDER_TIMEOUT={timeout}'])
        hours = timeout / 3600
        click.echo(f"⏱️  Max runtime: {hours:.1f} hours (graceful stop)")

    if cf_enabled:
        from utils.display_helper import needs_xvfb, has_xvfb

        if needs_xvfb():
            if has_xvfb():
                click.echo("🖥️  Headless environment detected - using xvfb for Cloudflare bypass")
                cmd = ['xvfb-run', '-a'] + cmd
            else:
                click.echo("⚠️  WARNING: Cloudflare bypass enabled but no display available and xvfb not installed")
                click.echo("   Install xvfb: sudo apt-get install xvfb")
                click.echo("   Continuing anyway - browser may fail to start...")
        else:
            click.echo("🖥️  Display available - using native browser for Cloudflare bypass")

    subprocess.run(cmd)
