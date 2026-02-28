import click
import subprocess
import sys
import os
import shutil
import pickle
import shlex
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
@click.option("--browser", is_flag=True, help="Use browser for JS-rendered sites and Cloudflare bypass")
@click.option("--scrapy-args", default=None, help="Additional Scrapy arguments (e.g., '-s SETTING=value -L DEBUG')")
@click.option("--reset-deltafetch", is_flag=True, help="Clear DeltaFetch cache to re-crawl all URLs")
@click.option("--save-html", is_flag=True, help="Save raw HTML in output (makes files larger)")
def crawl(spider, project, output, limit, timeout, proxy_type, browser, scrapy_args, reset_deltafetch, save_html):
    """Run a spider"""
    _run_spider(project, spider, output, limit, timeout, proxy_type, browser, scrapy_args, reset_deltafetch, save_html)


@click.command()
@click.option("--project", required=True, help="Project name")
@click.option("--limit", "-l", type=int, default=None, help="Limit items per spider")
def crawl_all(project, limit):
    """Run all spiders in a project"""
    from core.db import get_db
    from core.models import Spider

    db = next(get_db())
    spiders = (
        db.query(Spider)
        .filter(Spider.project == project, Spider.active.is_(True))
        .all()
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
        _run_spider(project, s.name, None, limit, None, "auto", False, None, False, False)


def _run_spider(
    project_name,
    spider_name,
    output_file=None,
    limit=None,
    timeout=None,
    proxy_type="datacenter",
    browser=False,
    scrapy_args=None,
    reset_deltafetch=False,
    save_html=False,
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

    # Reset DeltaFetch if requested (per-spider, per-project)
    if reset_deltafetch:
        # Use project-aware path to match DELTAFETCH_DIR setting
        # DeltaFetch middleware prepends ".scrapy/" automatically
        if project_name:
            deltafetch_db = Path(f".scrapy/deltafetch/{project_name}/{spider_name}.db")
        else:
            deltafetch_db = Path(f".scrapy/deltafetch/{spider_name}.db")

        if deltafetch_db.exists():
            deltafetch_db.unlink()
            click.echo(f"🔄 DeltaFetch cache cleared for '{spider_name}' - will re-crawl all URLs")
        else:
            click.echo(f"ℹ️  No DeltaFetch cache found for '{spider_name}' (already clean)")

        # Also clear checkpoint when resetting (otherwise dupefilter has old state)
        if project_name:
            checkpoint_path = Path(DATA_DIR) / project_name / spider_name / "checkpoint"
        else:
            checkpoint_path = Path(DATA_DIR) / spider_name / "checkpoint"

        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            click.echo(f"🗑️  Checkpoint cleared - starting completely fresh")

    if proxy_type == "auto":
        click.echo("🔄 Proxy mode: auto (smart escalation with expert-in-the-loop)")
    elif proxy_type == "residential":
        click.echo("🏠 Proxy mode: residential (explicit, used when blocked)")
    elif proxy_type == "datacenter":
        click.echo("🏢 Proxy mode: datacenter (explicit, used when blocked)")

    # Check if browser mode enabled (CLI flag or spider setting)
    cf_enabled = browser  # CLI flag takes precedence
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
        click.echo("🗺️  Using sitemap spider")
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

    # Set DeltaFetch directory per project to avoid collisions
    # Note: DeltaFetch middleware automatically prepends ".scrapy/" to this path
    if project_name:
        deltafetch_dir = f"deltafetch/{project_name}"
        cmd.extend(["-s", f"DELTAFETCH_DIR={deltafetch_dir}"])

    # Enable browser mode if --browser flag used
    if browser:
        cmd.extend(["-s", "CLOUDFLARE_ENABLED=True"])
        click.echo("🌐 Browser mode enabled (CloakBrowser with JS rendering + CF bypass)")

    # HTML storage configuration
    if save_html:
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=True"])
        html_note = " (includes HTML)"
    else:
        cmd.extend(["-s", "INCLUDE_HTML_IN_OUTPUT=False"])
        html_note = " (extracted data only)"

    # Checkpoint setup for production crawls
    checkpoint_dir = None
    if limit:
        click.echo(f"🧪 Test mode: Saving to database (limit: {limit} items)")
        click.echo(f"   Use './scrapai show {spider_name}' to verify results")
        cmd.extend(["-s", f"CLOSESPIDER_ITEMCOUNT={limit}"])
    else:
        click.echo(f"📁 Production mode: Exporting to files{html_note}")
        cmd.extend(["-s", 'ITEM_PIPELINES={"pipelines.ScrapaiPipeline": 300}'])

        # Enable checkpoint for production crawls
        if project_name:
            checkpoint_dir = str(
                Path(DATA_DIR) / project_name / spider_name / "checkpoint"
            )
        else:
            checkpoint_dir = str(Path(DATA_DIR) / spider_name / "checkpoint")

        # Check for checkpoint corruption (Scrapy bug: dupefilter persists but queue doesn't)
        # See: https://github.com/scrapy/scrapy/issues/4106
        requests_seen = Path(checkpoint_dir) / "requests.seen"
        requests_queue = list(Path(checkpoint_dir).glob("requests.queue*"))

        if requests_seen.exists() and not requests_queue:
            click.echo("⚠️  Detected corrupted checkpoint (dupefilter persisted but queue empty)")
            click.echo("   This is a known Scrapy bug: URLs marked seen but never crawled")
            click.echo("   Clearing dupefilter to allow re-discovery...")
            requests_seen.unlink()
            click.echo("✓ Dupefilter cleared - crawl will resume properly")

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
                        click.echo("♻️  Starting fresh crawl")
            except Exception as e:
                # If we can't read state file, just continue (checkpoint might be corrupted)
                click.echo(f"⚠️  Could not read checkpoint state: {e}")
                click.echo("   Continuing with existing checkpoint")

        cmd.extend(["-s", f"JOBDIR={checkpoint_dir}"])
        click.echo(f"💾 Checkpoint enabled: {checkpoint_dir}")
        click.echo("   Press Ctrl+C to pause, run same command to resume")

        if not output_file:
            # Check if resuming from checkpoint (output file already exists)
            output_file_marker = Path(checkpoint_dir) / "output_file.txt"

            if output_file_marker.exists():
                # Resuming - use same output file
                with open(output_file_marker, "r") as f:
                    output_file = f.read().strip()
                click.echo(f"♻️  Resuming from checkpoint - continuing to same file")
            else:
                # New crawl - use date-based filename (one file per day)
                now = datetime.now()
                timestamp = now.strftime("%d%m%Y")  # Just date, no time

                if project_name:
                    output_dir = str(Path(DATA_DIR) / project_name / spider_name / "crawls")
                else:
                    output_dir = str(Path(DATA_DIR) / spider_name / "crawls")

                os.makedirs(output_dir, exist_ok=True)
                output_file = str(Path(output_dir) / f"crawl_{timestamp}.jsonl")

                # Check if file already exists (multiple crawls on same day will append)
                if Path(output_file).exists():
                    click.echo(f"📝 Appending to existing file for today: {output_file}")
                else:
                    click.echo(f"📝 Creating new file: {output_file}")

                # Save output filename for future resumes
                os.makedirs(checkpoint_dir, exist_ok=True)
                with open(output_file_marker, "w") as f:
                    f.write(output_file)

        cmd.extend(["-o", output_file])
        if save_html:
            click.echo(f"   Output: {output_file} (includes HTML, date-based)")
        else:
            click.echo(f"   Output: {output_file} (extracted data only, date-based)")

    if output_file and limit:
        cmd.extend(["-o", output_file])
        click.echo(f"   Also saving to: {output_file}")

    if timeout:
        cmd.extend(["-s", f"CLOSESPIDER_TIMEOUT={timeout}"])
        hours = timeout / 3600
        click.echo(f"⏱️  Max runtime: {hours:.1f} hours (graceful stop)")

    if cf_enabled:
        # CloakBrowser visible by default (easier debugging)
        # On headless servers: use Xvfb or set CLOUDFLARE_HEADLESS=true
        from utils.display_helper import needs_xvfb, has_xvfb

        if needs_xvfb():
            if has_xvfb():
                click.echo(
                    "🖥️  Headless server detected - using Xvfb for visible browser"
                )
                cmd = ["xvfb-run", "-a"] + cmd
            else:
                click.echo(
                    "⚠️  WARNING: No display available and xvfb not installed"
                )
                click.echo("   Options:")
                click.echo("   1. Install Xvfb: sudo apt-get install xvfb")
                click.echo("   2. Or set CLOUDFLARE_HEADLESS=true in spider settings (headless mode)")
                click.echo("   Attempting to continue anyway...")

        if browser:
            click.echo("🌐 Browser mode enabled via --browser flag")
        else:
            click.echo("🌐 Browser enabled via spider settings")

    # Add custom Scrapy arguments if provided
    if scrapy_args:
        import shlex
        extra_args = shlex.split(scrapy_args)
        cmd.extend(extra_args)
        click.echo(f"🔧 Custom Scrapy args: {scrapy_args}")

    result = subprocess.run(cmd)

    # Cleanup checkpoint on successful completion (production mode only)
    if checkpoint_dir and result.returncode == 0:
        checkpoint_path = Path(checkpoint_dir)
        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            click.echo("✓ Checkpoint cleaned up (successful completion)")
