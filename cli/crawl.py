import click
import subprocess
import sys
import os
import shutil
import pickle
import shlex
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
from core.config import DATA_DIR


def _crawl_stats(jsonl_path):
    """(downloaded, with_content, content_eligible) for a crawl jsonl.

    PDF URLs are collected (links_only mode) but have no content by design, so
    they count as downloaded yet are NOT content-eligible — otherwise they'd
    drag the with-content % down misleadingly. The % is taken over eligible.
    """
    total = with_content = eligible = 0
    try:
        with open(jsonl_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                total += 1
                is_pdf = urlsplit(item.get("url") or "").path.lower().endswith(".pdf")
                if not is_pdf:
                    eligible += 1
                if str(item.get("content") or "").strip():
                    with_content += 1
    except FileNotFoundError:
        return (0, 0, 0)
    return (total, with_content, eligible)


def _pueue_state(status):
    """Pueue's nested status dict -> one lowercase word. `Done` unwraps to its
    result (Success->done, Killed->killed, anything else->failed)."""
    key = next(iter(status), "unknown")
    if key != "Done":
        return key.lower()
    result = status["Done"].get("result")
    if result == "Success":
        return "done"
    if result == "Killed":
        return "killed"
    return "failed"


def _pueue_times(status):
    """(start, end) ISO strings from a pueue status dict, or None where absent
    (Running has start but no end; Queued has neither)."""
    inner = next(iter(status.values()), {})
    if not isinstance(inner, dict):
        return (None, None)
    return (inner.get("start"), inner.get("end"))


def _short_ts(ts):
    """Compact an ISO timestamp to 'hh:mm dd-mm-yy' (string-sliced, tz-safe). '-' if None."""
    if not ts:
        return "-"
    return f"{ts[11:16]} {ts[8:10]}-{ts[5:7]}-{ts[2:4]}"


def _ago(seconds):
    """A duration in seconds -> compact relative string: 4s / 5m / 2h / 1d."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _latest_crawl_file(project, spider):
    """Most recently modified crawl_*.jsonl for a spider, or None."""
    base = Path(DATA_DIR) / project / spider if project else Path(DATA_DIR) / spider
    files = sorted(
        (base / "crawls").glob("crawl_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _build_detached_cmd(
    scrapai_path,
    spider,
    project,
    *,
    proxy_type="auto",
    browser=False,
    scrapy_args=None,
    reset_deltafetch=False,
    save_html=False,
    timeout=None,
    output=None,
):
    """The `scrapai crawl ... --detached` invocation the Pueue task runs.
    --detached makes that inner run skip resubmission and crawl in foreground."""
    cmd = [scrapai_path, "crawl", spider, "--project", project, "--detached"]
    if proxy_type and proxy_type != "auto":
        cmd += ["--proxy-type", proxy_type]
    if browser:
        cmd.append("--browser")
    if reset_deltafetch:
        cmd.append("--reset-deltafetch")
    if save_html:
        cmd.append("--save-html")
    if timeout:
        cmd += ["--timeout", str(timeout)]
    if output:
        cmd += ["--output", output]
    if scrapy_args:
        cmd += ["--scrapy-args", scrapy_args]
    return cmd


@click.command()
@click.argument("spider")
@click.option("--project", required=True, help="Project name")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--limit", "-l", type=int, default=None, help="Limit number of items")
@click.option("--timeout", "-t", type=int, default=None, help="Max runtime in seconds")
@click.option(
    "--proxy-type",
    default="auto",
    help=(
        "Proxy to use: auto (smart escalation), none, or any name configured in "
        ".env (datacenter, residential, isp, mobile, …). Default: auto"
    ),
)
@click.option(
    "--browser",
    is_flag=True,
    help="Use browser for JS-rendered sites and Cloudflare bypass",
)
@click.option(
    "--scrapy-args",
    default=None,
    help="Additional Scrapy arguments (e.g., '-s SETTING=value -L DEBUG')",
)
@click.option(
    "--reset-deltafetch",
    is_flag=True,
    help="Clear DeltaFetch cache to re-crawl all URLs",
)
@click.option(
    "--save-html", is_flag=True, help="Save raw HTML in output (makes files larger)"
)
@click.option(
    "--detached",
    is_flag=True,
    hidden=True,
    help="Internal: run in the foreground of a Pueue task (no resubmit)",
)
def crawl(
    spider,
    project,
    output,
    limit,
    timeout,
    proxy_type,
    browser,
    scrapy_args,
    reset_deltafetch,
    save_html,
    detached,
):
    """Run a spider"""
    _run_spider(
        project,
        spider,
        output,
        limit,
        timeout,
        proxy_type,
        browser,
        scrapy_args,
        reset_deltafetch,
        save_html,
        detached,
    )


@click.command()
@click.option("--project", required=True, help="Project name")
@click.option("--limit", "-l", type=int, default=None, help="Limit items per spider")
def crawl_all(project, limit):
    """Run all spiders in a project"""
    from core.db import get_db
    from core.models import Spider

    with get_db() as db:
        spiders = (
            db.query(Spider)
            .filter(Spider.project == project, Spider.active.is_(True))
            .all()
        )

        if not spiders:
            click.echo(f"❌ No active spiders found for project '{project}'")
            return

        # Materialize spider names before exiting the session so we can call
        # _run_spider (which opens its own session) outside the with-block.
        spider_names = [s.name for s in spiders]

    click.echo(f"🚀 Running all spiders for project: {project}")
    click.echo(f"🕷️  Spiders: {', '.join(spider_names)}")

    for name in spider_names:
        click.echo(f"\n{'='*50}")
        click.echo(f"Running: {name}")
        click.echo(f"{'='*50}")
        # detached=True keeps crawl_all running each spider inline, unchanged.
        _run_spider(
            project, name, None, limit, None, "auto", False, None, False, False, True
        )


@click.command("crawl-status")
@click.option("--project", default=None, help="Only show crawls in this project")
def crawl_status(project):
    """Show each scrapai crawl's run state + how much it has downloaded.

    Joins Pueue's run state (running/queued/done/...) with the crawl file:
    items downloaded, and how many have content text (extraction worked).
    """
    if not shutil.which("pueue"):
        click.echo("Pueue not installed - no detached crawls to report.")
        return
    res = subprocess.run(["pueue", "status", "--json"], capture_output=True, text=True)
    if res.returncode != 0:
        click.echo(f"Could not read Pueue status: {res.stderr.strip()}")
        return

    tasks = json.loads(res.stdout).get("tasks", {})
    # One row per spider: a spider may have several Pueue tasks (re-runs); keep
    # the newest (highest task id) so "status" shows its current state.
    latest = {}
    for tid, task in tasks.items():
        label = task.get("label") or ""
        if not label.startswith("scrapai:"):
            continue
        parts = label.split(":")
        proj, spider = (parts[1], parts[2]) if len(parts) == 3 else (None, parts[1])
        if project and proj != project:
            continue
        key = (proj, spider)
        if key not in latest or int(tid) > latest[key][0]:
            latest[key] = (int(tid), task)

    rows = []
    for (proj, spider), (_tid, task) in latest.items():
        status = task.get("status") or {}
        state = _pueue_state(status)
        start, end = _pueue_times(status)
        f = _latest_crawl_file(proj, spider)
        downloaded, with_content, eligible = _crawl_stats(str(f)) if f else (0, 0, 0)
        # last-item: time since the crawl file was last written = liveness signal
        last = _ago(time.time() - f.stat().st_mtime) if f else "-"
        rows.append(
            (
                spider,
                proj or "-",
                state,
                downloaded,
                with_content,
                eligible,
                start,
                end,
                last,
            )
        )

    if not rows:
        click.echo("No scrapai crawls found in Pueue.")
        return

    from rich import box
    from rich.console import Console
    from rich.table import Table

    # Color is shown in a terminal; rich auto-strips it when output is captured
    # (e.g. by the agent), so piped output stays clean plain text.
    state_color = {
        "running": "bold green",
        "queued": "cyan",
        "paused": "yellow",
        "done": "green",
        "killed": "yellow",
        "failed": "red",
    }

    table = Table(box=box.SIMPLE)
    table.add_column("spider")
    table.add_column("project")
    table.add_column("state")
    table.add_column("downloaded", justify="right")
    table.add_column("with-content", justify="right")
    table.add_column("start")
    table.add_column("end")
    table.add_column("last-item")

    for row in sorted(rows):
        spider, proj, state, downloaded, with_content, eligible, start, end, last = row
        # % is over content-eligible items (PDFs excluded), so links-only PDFs
        # don't make a healthy crawl look like it's missing content.
        pct = (
            f"{with_content} ({with_content * 100 // eligible}%)"
            if eligible
            else str(with_content)
        )
        color = state_color.get(state, "white")
        table.add_row(
            spider,
            proj,
            f"[{color}]{state}[/{color}]",
            f"{downloaded:,}",
            pct,
            _short_ts(start),
            _short_ts(end),
            last,
        )

    # Interactive terminal: fit to its real width (with color). Captured/piped
    # (e.g. the agent): force a wide width so columns aren't truncated to 80.
    console = Console(width=None if sys.stdout.isatty() else 140)
    console.print(table)


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
    detached=False,
):
    """Run a Scrapy spider from database"""
    from core.db import get_db
    from core.models import Spider

    with get_db() as db:
        db_spider = (
            db.query(Spider)
            .filter(Spider.name == spider_name, Spider.project == project_name)
            .first()
        )

        if not db_spider:
            click.echo(
                f"❌ Spider '{spider_name}' not found in project '{project_name}'."
            )
            return

        # Extract all needed info from db_spider before exiting the session
        # so the subprocess work below can run without a live DB connection.
        spider_settings = list(db_spider.settings) if db_spider.settings else []

    # No --limit = production crawl: hand it to Pueue so it survives an SSH
    # disconnect. The Pueue task re-runs this command with --detached, which
    # falls through to the foreground crawl below instead of resubmitting.
    if not limit and not detached:
        if not shutil.which("pueue"):
            click.echo("Pueue not installed - needed to run full crawls detached.")
            click.echo(
                "Install it (README: 'Long-running crawls'), or test with --limit N."
            )
            sys.exit(1)
        scrapai_path = str(Path(__file__).resolve().parent.parent / "scrapai")
        inner = _build_detached_cmd(
            scrapai_path,
            spider_name,
            project_name,
            proxy_type=proxy_type,
            browser=browser,
            scrapy_args=scrapy_args,
            reset_deltafetch=reset_deltafetch,
            save_html=save_html,
            timeout=timeout,
            output=output_file,
        )
        label = (
            f"scrapai:{project_name}:{spider_name}"
            if project_name
            else f"scrapai:{spider_name}"
        )
        add = [
            "pueue",
            "add",
            "--label",
            label,
            "--working-directory",
            os.getcwd(),
            "--print-task-id",
            "--",
            *inner,
        ]
        res = subprocess.run(add, capture_output=True, text=True)
        if res.returncode != 0:
            click.echo(f"Failed to queue crawl via Pueue: {res.stderr.strip()}")
            sys.exit(1)
        tid = res.stdout.strip()
        click.echo(
            f"Production crawl '{spider_name}' queued in Pueue (task {tid}); "
            "survives SSH disconnect."
        )
        click.echo(
            f"  progress: pueue log {tid}   all: pueue status   stop: pueue kill {tid}"
        )
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
            click.echo(
                f"🔄 DeltaFetch cache cleared for '{spider_name}' - will re-crawl all URLs"
            )
        else:
            click.echo(
                f"ℹ️  No DeltaFetch cache found for '{spider_name}' (already clean)"
            )

        # Also clear checkpoint when resetting (otherwise dupefilter has old state)
        if project_name:
            checkpoint_path = Path(DATA_DIR) / project_name / spider_name / "checkpoint"
        else:
            checkpoint_path = Path(DATA_DIR) / spider_name / "checkpoint"

        if checkpoint_path.exists():
            shutil.rmtree(checkpoint_path)
            click.echo("🗑️  Checkpoint cleared - starting completely fresh")

    if proxy_type == "auto":
        click.echo("🔄 Proxy mode: auto (smart escalation with expert-in-the-loop)")
    elif proxy_type == "none":
        click.echo("🌐 Proxy mode: none (direct connections only)")
    else:
        click.echo(f"🔀 Proxy mode: {proxy_type} (explicit, used when blocked)")

    # Check if browser mode enabled (CLI flag or spider setting)
    cf_enabled = browser  # CLI flag takes precedence
    use_sitemap = False
    if spider_settings:
        for setting in spider_settings:
            if setting.key in ["CLOUDFLARE_ENABLED", "BROWSER_ENABLED"] and str(
                setting.value
            ).lower() in [
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
        click.echo(
            "🌐 Browser mode enabled (CloakBrowser with JS rendering + CF bypass)"
        )

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
            click.echo(
                "⚠️  Detected corrupted checkpoint (dupefilter persisted but queue empty)"
            )
            click.echo(
                "   This is a known Scrapy bug: URLs marked seen but never crawled"
            )
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
                click.echo("♻️  Resuming from checkpoint - continuing to same file")
            else:
                # New crawl - use date-based filename (one file per day)
                now = datetime.now()
                timestamp = now.strftime("%d%m%Y")  # Just date, no time

                if project_name:
                    output_dir = str(
                        Path(DATA_DIR) / project_name / spider_name / "crawls"
                    )
                else:
                    output_dir = str(Path(DATA_DIR) / spider_name / "crawls")

                os.makedirs(output_dir, exist_ok=True)
                output_file = str(Path(output_dir) / f"crawl_{timestamp}.jsonl")

                # Check if file already exists (multiple crawls on same day will append)
                if Path(output_file).exists():
                    click.echo(
                        f"📝 Appending to existing file for today: {output_file}"
                    )
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
                    "🖥️  Headless server detected - using Xvfb for headed browser (best stealth)"
                )
                cmd = ["xvfb-run", "-a"] + cmd
            else:
                click.echo(
                    "❌ ERROR: Browser mode requires a display but Xvfb is not installed"
                )
                click.echo("")
                click.echo(
                    "Browser runs in HEADED mode (headless=False) for maximum stealth."
                )
                click.echo(
                    "On servers without a display, Xvfb provides a virtual framebuffer."
                )
                click.echo("")
                click.echo("Fix options:")
                click.echo("  1. Install Xvfb (recommended):")
                click.echo("     sudo apt-get update && sudo apt-get install -y xvfb")
                click.echo("")
                click.echo("  2. Or force headless mode (worse stealth):")
                click.echo("     Add to spider settings: CLOUDFLARE_HEADLESS=true")
                click.echo("")
                sys.exit(1)

        if browser:
            click.echo("🌐 Browser mode enabled via --browser flag")
        else:
            click.echo("🌐 Browser enabled via spider settings")

    # Add custom Scrapy arguments if provided
    if scrapy_args:
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

    # Upload to S3 if configured (production mode only)
    if output_file and not limit and result.returncode == 0:
        from utils.s3_upload import is_s3_configured, upload_to_s3

        if is_s3_configured():
            click.echo("📤 Uploading to S3...")
            try:
                # Determine S3 key (path in bucket)
                # Preserve project/spider structure: project/spider/crawls/filename
                output_path = Path(output_file)
                if project_name:
                    s3_key = f"{project_name}/{spider_name}/crawls/{output_path.name}"
                else:
                    s3_key = f"{spider_name}/crawls/{output_path.name}"

                success = upload_to_s3(
                    output_file,
                    s3_key=s3_key,
                    compress=True,
                    delete_after_upload=True,
                )

                if success:
                    click.echo("✅ Upload to S3 completed")
                else:
                    click.echo("⚠️  S3 upload failed (file kept locally)")

            except ImportError:
                click.echo("⚠️  boto3 not installed")
                click.echo("   Run: pip install -r requirements.txt")
            except Exception as e:
                click.echo(f"⚠️  S3 upload error: {e}")
                click.echo("   File kept locally")
