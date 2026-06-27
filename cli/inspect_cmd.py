import click
import sys
import logging


@click.command()
@click.argument("url")
@click.option("--project", default="default", help="Project name")
@click.option(
    "--session",
    default=None,
    help="Reuse a saved login session (see `scrapai session login`)",
)
@click.option("--output-dir", default=None, help="Directory to save analysis")
@click.option(
    "--proxy-type",
    default="auto",
    help=(
        "Proxy to test with: auto/none, or any name configured in .env "
        "(datacenter, residential, isp, mobile, …)"
    ),
)
@click.option("--no-save-html", is_flag=True, help="Do not save the full HTML")
@click.option(
    "--browser",
    is_flag=True,
    help="Use CloakBrowser for JS-rendered sites and Cloudflare bypass",
)
@click.option(
    "--screenshot",
    is_flag=True,
    help="Save a screenshot (page.png) to view the page — forces browser",
)
@click.option(
    "--screenshot-screens",
    type=int,
    default=2,
    help="Screen-heights to capture from the top (default 2; raise to see lower, 0 = full page)",
)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error", "critical"]),
    default="info",
    help="Set the logging level",
)
@click.option("--log-file", default=None, help="Path to log file")
def inspect_cmd(
    url,
    project,
    session,
    output_dir,
    proxy_type,
    no_save_html,
    browser,
    screenshot,
    screenshot_screens,
    log_level,
    log_file,
):
    """Inspect a website to help create scrapers

    Uses lightweight HTTP by default. Use --browser for JS-rendered or Cloudflare-protected sites.
    Use --screenshot to save a full-page page.png you can view directly.
    """
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logger = logging.getLogger("inspector")
    logger.info(f"Starting inspection of {url}")

    # A screenshot needs a rendered page → force the browser path.
    if browser or screenshot:
        click.echo("Using CloakBrowser (headed mode, JS + Cloudflare bypass)")
        _run_browser_inspect(
            url,
            project,
            output_dir,
            proxy_type,
            no_save_html,
            screenshot,
            screenshot_screens,
            session,
        )
    else:
        click.echo("⚡ Trying lightweight transports (HTTP → curl_cffi)")
        from utils.inspector import inspect_page

        result = inspect_page(
            url,
            output_dir,
            proxy_type,
            not no_save_html,
            mode="http",
            project=project,
            session=session,
        )
        if result and result.get("needs_browser"):
            click.echo("↑ Lightweight transports blocked — escalating to browser…")
            _run_browser_inspect(
                url, project, output_dir, proxy_type, no_save_html, session=session
            )

    logger.info("Inspection complete")


def _run_browser_inspect(
    url,
    project,
    output_dir,
    proxy_type,
    no_save_html,
    screenshot=False,
    screenshot_screens=2,
    session=None,
):
    """Run browser inspection as subprocess (same pattern as crawl.py).

    Wraps with xvfb-run on headless servers automatically.
    """
    import os
    import subprocess

    # If the shared browser service is running, route through it in-process —
    # no separate browser, no subprocess, no Xvfb needed.
    from utils import browser_client

    if browser_client.is_running():
        click.echo("Using shared browser service (reusing the warm browser)")
        from utils.inspector import inspect_page

        inspect_page(
            url,
            output_dir,
            proxy_type,
            not no_save_html,
            mode="browser",
            project=project,
            screenshot=screenshot,
            screenshot_screens=screenshot_screens,
            session=session,
        )
        return

    # Build subprocess command: python -m utils.inspector <url> --browser ...
    cmd = [sys.executable, "-m", "utils.inspector", url, "--browser"]
    cmd += ["--project", project]
    if session:
        cmd += ["--session", session]
    if screenshot:
        cmd += ["--screenshot", "--screenshot-screens", str(screenshot_screens)]
    if output_dir:
        cmd += ["--output-dir", output_dir]
    if proxy_type != "auto":
        cmd += ["--proxy-type", proxy_type]
    if no_save_html:
        cmd += ["--no-save-html"]

    # Auto-wrap with xvfb-run on headless servers (same as crawl.py)
    from utils.display_helper import needs_xvfb, has_xvfb

    if needs_xvfb():
        if has_xvfb():
            click.echo("🖥️  Headless server detected - using Xvfb for headed browser")
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
            click.echo("Install Xvfb:")
            click.echo("  sudo apt-get update && sudo apt-get install -y xvfb")
            click.echo("")
            sys.exit(1)

    # Run the inspector subprocess
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(__file__)))
    if result.returncode != 0:
        sys.exit(result.returncode)
