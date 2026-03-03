import click
import sys
import logging


@click.command()
@click.argument("url")
@click.option("--project", default="default", help="Project name")
@click.option("--output-dir", default=None, help="Directory to save analysis")
@click.option(
    "--proxy-type",
    type=click.Choice(["none", "static", "residential", "auto"]),
    default="auto",
    help="Proxy type to use",
)
@click.option("--no-save-html", is_flag=True, help="Do not save the full HTML")
@click.option(
    "--browser",
    is_flag=True,
    help="Use CloakBrowser for JS-rendered sites and Cloudflare bypass",
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
    output_dir,
    proxy_type,
    no_save_html,
    browser,
    log_level,
    log_file,
):
    """Inspect a website to help create scrapers

    Uses lightweight HTTP by default. Use --browser for JS-rendered or Cloudflare-protected sites.
    """
    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logger = logging.getLogger("inspector")
    logger.info(f"Starting inspection of {url}")

    if browser:
        click.echo("🌐 Using CloakBrowser (headed mode, JS + Cloudflare bypass)")
        _run_browser_inspect(url, project, output_dir, proxy_type, no_save_html)
    else:
        click.echo("⚡ Using lightweight HTTP fetch")
        from utils.inspector import inspect_page

        inspect_page(
            url, output_dir, proxy_type, not no_save_html, mode="http", project=project
        )

    logger.info("Inspection complete")


def _run_browser_inspect(url, project, output_dir, proxy_type, no_save_html):
    """Run browser inspection as subprocess (same pattern as crawl.py).

    Wraps with xvfb-run on headless servers automatically.
    """
    import os
    import subprocess

    # Build subprocess command: python -m utils.inspector <url> --browser ...
    cmd = [sys.executable, "-m", "utils.inspector", url, "--browser"]
    cmd += ["--project", project]
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
