"""`scrapai browser` — manage the persistent browser service.

Keeps one warm browser running in the background so inspect/screenshot calls
reuse it (open once, pass Cloudflare once) instead of cold-starting every page.
"""

import os
import signal
import sys
import time
from urllib.parse import urlparse

import click

from utils import browser_client as bc


@click.group()
def browser():
    """Manage the persistent browser service."""


def _start(proxy_type, pool):
    """Spawn the service and wait until it answers pings. Exits on failure."""
    try:
        proc = bc._spawn_service(proxy_type, pool)
    except RuntimeError:
        click.echo("ERROR: browser needs a display but Xvfb is not installed.")
        click.echo("Install: sudo apt-get install -y xvfb")
        sys.exit(1)

    click.echo("Starting browser service (launching browser, may take a moment)...")
    for _ in range(90):
        if bc.is_running():
            state = bc.read_state()
            click.echo(
                f"Browser service started (pid {proc.pid}, port {state['port']})."
            )
            return
        if proc.poll() is not None:
            bc.clear_state()
            click.echo("Browser service failed to start.")
            sys.exit(1)
        time.sleep(1)
    click.echo("Browser service did not become ready in time.")
    sys.exit(1)


def _stop(state):
    """Gracefully shut the service down and drop its state file."""
    if bc.is_running():
        bc.request("shutdown", timeout=10)
        time.sleep(1)
    # Ensure the process is gone, then drop the state file.
    try:
        os.kill(state["pid"], signal.SIGTERM)
    except OSError:
        pass
    bc.clear_state()


@browser.command()
@click.option(
    "--proxy-type",
    default="auto",
    help="Proxy for the service (auto/none, or any name in .env)",
)
@click.option(
    "--pool",
    default=5,
    type=int,
    help="Max concurrent lanes (one per site, default 5)",
)
def start(proxy_type, pool):
    """Start the background browser service."""
    if bc.is_running():
        state = bc.read_state()
        click.echo(f"Browser service already running (pid {state['pid']}).")
        return
    _start(proxy_type, pool)


@browser.command()
def stop():
    """Stop the background browser service."""
    state = bc.read_state()
    if not state:
        click.echo("Browser service not running.")
        return
    _stop(state)
    click.echo("Browser service stopped.")


@browser.command()
@click.option(
    "--proxy-type",
    default=None,
    help="Proxy for the service (default: same as before the restart)",
)
@click.option(
    "--pool",
    default=None,
    type=int,
    help="Max concurrent lanes (default: same as before the restart)",
)
def restart(proxy_type, pool):
    """Restart the browser service with its previous settings (flags override)."""
    state = bc.read_state() or {}
    if proxy_type is None:
        proxy_type = state.get("proxy_type", "auto")
    if pool is None:
        pool = state.get("pool", 5)
    if state:
        _stop(state)
        click.echo("Browser service stopped.")
    _start(proxy_type, pool)


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
