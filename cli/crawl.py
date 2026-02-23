import click
import subprocess
import sys
import os
import shutil
import pickle
from pathlib import Path
from datetime import datetime
from core.config import DATA_DIR


@click.command()
@click.argument("spider")
@click.option("--project", default=None, help="Project name")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--limit", "-l", type=int, default=None, help="Limit number of items")
@click.option("--timeout", "-t", type=int, default=None, help="Max runtime in seconds")
@click.option(
    "--proxy-type",
    type=click.Choice(["auto", "datacenter", "residential"], case_sensitive=False),
    default="auto",
    help="Proxy strategy: auto (smart escalation), datacenter, or residential (default: auto)",
)
def crawl(spider, project, output, limit, timeout, proxy_type):
    """Run a spider"""
    _run_spider(project, spider, output, limit, timeout, proxy_type)


@click.command()
@click.option("--project", required=True, help="Project name")
@click.option("--limit", "-l", type=int, default=None, help="Limit items per spider")
def crawl_all(project, limit):
    """Run all spiders in a project"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    spiders = (
        db.query(Spider).filter(Spider.project == project, Spider.active == True).all()
    )

    if not spiders:
        click.echo(f"❌ No active spiders found for project '{project}'")
        return

    click.echo(f"🚀 Running all spiders for project: {project}")
    click.echo(f"🕷️  Spiders: {', '.join(s.name for s in spiders)}")

    for s in spiders:
        click.echo(f"\n{'='*50}")
        click.echo(f"Running: {s.name}")
        click.echo(f"{'='*50}")
        _run_spider(project, s.name, None, limit, None, "auto")


def _run_spider(
    project_name,
    spider_name,
    output_file=None,
    limit=None,
    timeout=None,
    proxy_type="datacenter",
):
    """Run a Scrapy spider from database"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    db_spider = db.query(Spider).filter(Spider.name == spider_name).first()

    if not db_spider:
        click.echo(f"❌ Spider '{spider_name}' not found in database.")
        return

    click.echo(f"🚀 Running DB spider: {spider_name}")

    if proxy_type == "auto":
        click.echo(f"🔄 Proxy mode: auto (smart escalation with expert-in-the-loop)")
    elif proxy_type == "residential":
        click.echo(f"🏠 Proxy mode: residential (explicit, used when blocked)")
    elif proxy_type == "datacenter":
        click.echo(f"🏢 Proxy mode: datacenter (explicit, used when blocked)")

    cf_enabled = False
    use_sitemap = False
    if db_spider.settings:
        for setting in db_spider.settings:
            if setting.key == "CLOUDFLARE_ENABLED" and str(setting.value).lower() in [
                "true",
                "1",
            ]:
                cf_enabled = True
            if setting.key == "USE_SITEMAP" and str(setting.value).lower() in [
                "true",
                "1",
            ]:
                use_sitemap = True

    if use_sitemap:
        spider_class = "sitemap_database_spider"
        click.echo(f"🗺️  Using sitemap spider")
    else:
        spider_class = "database_spider"

    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        spider_class,
        "-a",
        f"spider_name={spider_name}",
    ]

    # Pass proxy type to middleware
    cmd.extend(["-s", f"PROXY_TYPE={proxy_type}"])

    # Checkpoint setup for production crawls
    checkpoint_dir = None
    if limit:
        click.echo(f"🧪 Test mode: Saving to database (limit: {limit} items)")
        click.echo(f"   Use './scrapai show {spider_name}' to verify results")
        cmd.extend(["-s", f"CLOSESPIDER_ITEMCOUNT={limit}"])
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=False"])
    else:
        click.echo(f"📁 Production mode: Exporting to files (database disabled)")
        cmd.extend(["-s", 'ITEM_PIPELINES={"pipelines.ScrapaiPipeline": 300}'])
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=True"])

        # Enable checkpoint for production crawls
        if project_name:
            checkpoint_dir = f"{DATA_DIR}/{project_name}/{spider_name}/checkpoint"
        else:
            checkpoint_dir = f"{DATA_DIR}/{spider_name}/checkpoint"

        # Check if proxy type changed and clear checkpoint if needed
        state_file = Path(checkpoint_dir) / "spider.state"
        if state_file.exists():
            try:
                with open(state_file, "rb") as f:
                    state = pickle.load(f)
                    old_proxy = state.get("proxy_type_used")

                    if old_proxy and old_proxy != proxy_type:
                        click.echo(
                            f"⚠️  Proxy type changed: {old_proxy} → {proxy_type}"
                        )
                        click.echo(
                            f"🗑️  Clearing checkpoint to ensure all URLs retried with {proxy_type} proxy"
                        )
                        shutil.rmtree(checkpoint_dir)
                        click.echo(f"♻️  Starting fresh crawl")
            except Exception as e:
                # If we can't read state file, just continue (checkpoint might be corrupted)
                click.echo(f"⚠️  Could not read checkpoint state: {e}")
                click.echo(f"   Continuing with existing checkpoint")

        cmd.extend(["-s", f"JOBDIR={checkpoint_dir}"])
        click.echo(f"💾 Checkpoint enabled: {checkpoint_dir}")
        click.echo(f"   Press Ctrl+C to pause, run same command to resume")

        if not output_file:
            now = datetime.now()
            timestamp = now.strftime("%d%m%Y_%H%M%S")

            if project_name:
                output_dir = f"{DATA_DIR}/{project_name}/{spider_name}/crawls"
            else:
                output_dir = f"{DATA_DIR}/{spider_name}/crawls"

            os.makedirs(output_dir, exist_ok=True)
            output_file = f"{output_dir}/crawl_{timestamp}.jsonl"

        cmd.extend(["-o", output_file])
        click.echo(f"   Output: {output_file} (includes HTML)")

    if output_file and limit:
        cmd.extend(["-o", output_file])
        click.echo(f"   Also saving to: {output_file}")

    if timeout:
        cmd.extend(["-s", f"CLOSESPIDER_TIMEOUT={timeout}"])
        hours = timeout / 3600
        click.echo(f"⏱️  Max runtime: {hours:.1f} hours (graceful stop)")

    if cf_enabled:
        from utils.display_helper import needs_xvfb, has_xvfb

        if needs_xvfb():
            if has_xvfb():
                click.echo(
                    "🖥️  Headless environment detected - using xvfb for Cloudflare bypass"
                )
                cmd = ["xvfb-run", "-a"] + cmd
            else:
                click.echo(
                    "⚠️  WARNING: Cloudflare bypass enabled but no display available and xvfb not installed"
                )
                click.echo("   Install xvfb: sudo apt-get install xvfb")
                click.echo("   Continuing anyway - browser may fail to start...")
        else:
            click.echo(
                "🖥️  Display available - using native browser for Cloudflare bypass"
            )

    result = subprocess.run(cmd)

    # Cleanup checkpoint on successful completion (production mode only)
    if checkpoint_dir and result.returncode == 0:
        checkpoint_path = Path(checkpoint_dir)
        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            click.echo(f"✓ Checkpoint cleaned up (successful completion)")
