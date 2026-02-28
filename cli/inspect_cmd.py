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
@click.option("--browser", is_flag=True, help="Use browser for JS-rendered sites")
@click.option("--cloudflare", is_flag=True, help="Use Cloudflare bypass mode")
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
    cloudflare,
    log_level,
    log_file,
):
    """Inspect a website to help create scrapers

    Uses lightweight HTTP by default. Use --browser for JS sites, --cloudflare for protected sites.
    """
    from utils.inspector import inspect_page

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logger = logging.getLogger("inspector")
    logger.info(f"Starting inspection of {url}")

    # Both flags do the same thing now (use CloakBrowser)
    # Keep both for backward compatibility, but they're identical

    # Determine mode
    if cloudflare or browser:
        mode = "browser"  # Both use CloakBrowser now
        if cloudflare:
            click.echo("🌐 Using CloakBrowser (visible mode, JS + CF bypass)")
        else:
            click.echo("🌐 Using CloakBrowser (visible mode, JS rendering + CF bypass)")
    else:
        mode = "http"
        click.echo("⚡ Using lightweight HTTP fetch")

    inspect_page(
        url, output_dir, proxy_type, not no_save_html, mode=mode, project=project
    )
    logger.info("Inspection complete")
