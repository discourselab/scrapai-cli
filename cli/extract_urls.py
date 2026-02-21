import click
import sys


@click.command()
@click.option('--file', required=True, help='Path to HTML file')
@click.option('--output', '-o', default=None, help='Output file path')
def extract_urls(file, output):
    """Extract all URLs from an HTML file"""
    from utils.url_extractor import extract_urls_from_html

    try:
        urls = extract_urls_from_html(file, output)

        if not output:
            click.echo('\n'.join(urls))
        else:
            click.echo(f"✅ Extracted {len(urls)} URLs to {output}")

    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Error: {e}")
        sys.exit(1)
