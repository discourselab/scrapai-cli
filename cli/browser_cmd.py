"""`scrapai browser` — manage the persistent browser service.

Keeps one warm browser running in the background so inspect/screenshot calls
reuse it (open once, pass Cloudflare once) instead of cold-starting every page.
"""

import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

import click

from utils import browser_client as bc


@click.group()
def browser():
    """Manage the persistent browser service."""


@browser.command()
@click.option(
    "--proxy-type",
    default="auto",
    help="Proxy for the service (auto/none, or any name in .env)",
)
def start(proxy_type):
    """Start the background browser service."""
    if bc.is_running():
        state = bc.read_state()
        click.echo(f"Browser service already running (pid {state['pid']}).")
        return

    bc.clear_state()  # drop any stale state
    port = bc.free_port()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [
        sys.executable,
        "-m",
        "utils.browser_service",
        "--port",
        str(port),
        "--proxy-type",
        proxy_type,
    ]

    from utils.display_helper import needs_xvfb, has_xvfb

    if needs_xvfb():
        if has_xvfb():
            click.echo("Headless server detected - using Xvfb for the browser")
            cmd = ["xvfb-run", "-a"] + cmd
        else:
            click.echo("ERROR: browser needs a display but Xvfb is not installed.")
            click.echo("Install: sudo apt-get install -y xvfb")
            sys.exit(1)

    proc = subprocess.Popen(
        cmd,
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    bc.write_state(proc.pid, port)

    click.echo("Starting browser service (launching browser, may take a moment)...")
    for _ in range(90):
        if bc.is_running():
            click.echo(f"Browser service started (pid {proc.pid}, port {port}).")
            return
        if proc.poll() is not None:
            bc.clear_state()
            click.echo("Browser service failed to start.")
            sys.exit(1)
        time.sleep(1)
    click.echo("Browser service did not become ready in time.")
    sys.exit(1)


@browser.command()
def stop():
    """Stop the background browser service."""
    state = bc.read_state()
    if not state:
        click.echo("Browser service not running.")
        return

    if bc.is_running():
        bc.request("shutdown", timeout=10)
        time.sleep(1)
    # Ensure the process is gone, then drop the state file.
    try:
        os.kill(state["pid"], signal.SIGTERM)
    except OSError:
        pass
    bc.clear_state()
    click.echo("Browser service stopped.")


@browser.command()
def status():
    """Show whether the browser service is running."""
    if bc.is_running():
        state = bc.read_state()
        click.echo(f"Running (pid {state['pid']}, port {state['port']}).")
    else:
        click.echo("Not running.")


@browser.command()
@click.argument("url")
@click.option("--project", default="default", help="Project name")
@click.option("--screens", default=2, help="Screen-heights to capture (0 = full page)")
def shot(url, project, screens):
    """Screenshot a URL through the running service (reuses the warm browser)."""
    if not bc.is_running():
        click.echo("No browser service running. Start it: ./scrapai browser start")
        sys.exit(1)

    from core.config import DATA_DIR

    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    out_dir = os.path.join(DATA_DIR, project, domain, "analysis")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "page.png")

    resp = bc.request("screenshot", url=url, path=path, screens=screens, timeout=180)
    if resp and resp.get("ok"):
        click.echo(f"Saved screenshot to: {path}")
    else:
        click.echo(f"Failed: {resp}")
        sys.exit(1)
