import click
import sys
import logging


@click.command()
@click.argument('url')
@click.option('--project', default='default', help='Project name')
@click.option('--output-dir', default=None, help='Directory to save analysis')
@click.option('--proxy-type', type=click.Choice(['none', 'static', 'residential', 'auto']),
              default='auto', help='Proxy type to use')
@click.option('--no-save-html', is_flag=True, help='Do not save the full HTML')
@click.option('--cloudflare', is_flag=True, help='Use Cloudflare bypass mode')
@click.option('--log-level', type=click.Choice(['debug', 'info', 'warning', 'error', 'critical']),
              default='info', help='Set the logging level')
@click.option('--log-file', default=None, help='Path to log file')
def inspect_cmd(url, project, output_dir, proxy_type, no_save_html, cloudflare, log_level, log_file):
    """Inspect a website to help create scrapers"""
    from utils.inspector import inspect_page

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    logger = logging.getLogger('inspector')
    logger.info(f"Starting inspection of {url}")

    if cloudflare:
        from utils.display_helper import needs_xvfb, has_xvfb

        if needs_xvfb():
            if not has_xvfb():
                click.echo("❌ ERROR: Cloudflare bypass requires a display")
                click.echo("   No display available and xvfb not installed")
                click.echo("\nOptions:")
                click.echo("   1. Install xvfb: sudo apt-get install xvfb")
                click.echo("   2. Then run: xvfb-run -a ./scrapai inspect <url> --cloudflare")
                click.echo("   3. Or run on a machine with a display")
                sys.exit(1)
            click.echo("🖥️  Headless environment detected - make sure to use: xvfb-run -a ./scrapai inspect ...")
        else:
            click.echo("🖥️  Display available - using native browser for Cloudflare bypass")

    inspect_page(url, output_dir, proxy_type, not no_save_html,
                 use_cloudflare=cloudflare, project=project)
    logger.info("Inspection complete")
