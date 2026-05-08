"""`scrapai try` — run each generic extractor against a saved HTML file for quick comparison."""

import click


@click.command(name="try")
@click.argument("html_file")
@click.option(
    "--content-preview",
    default=300,
    type=int,
    help="Chars of content to preview (default 300)",
)
def try_cmd(html_file, content_preview):
    """Run newspaper and trafilatura against a local HTML file and compare output.

    Pair with `scrapai inspect <url>` to fetch the HTML first:

        scrapai inspect https://example.com/article --project proj
        scrapai try data/proj/spider/analysis/page.html
    """
    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()

    click.echo(f"\n📄 File: {html_file}")
    click.echo(f"📊 HTML size: {len(html):,} bytes\n")

    from core.extractors import NewspaperExtractor, TrafilaturaExtractor

    # The extractors accept a url arg for their own metadata; use a placeholder.
    url = f"file://{html_file}"

    _run_extractor("newspaper", NewspaperExtractor(), url, html, content_preview)
    _run_extractor("trafilatura", TrafilaturaExtractor(), url, html, content_preview)


def _run_extractor(name, extractor, url, html, preview_chars):
    click.echo("=" * 60)
    click.echo(f"🧪 {name}")
    click.echo("=" * 60)

    try:
        result = extractor.extract(url, html)
    except Exception as e:
        click.echo(f"❌ {name} raised: {e}\n")
        return

    if not result:
        click.echo(f"❌ {name} returned no result\n")
        return

    content = result.content or ""
    click.echo(f"  title:   {result.title or '(none)'}")
    click.echo(f"  author:  {result.author or '(none)'}")
    click.echo(f"  date:    {result.published_date or '(none)'}")
    click.echo(f"  length:  {len(content):,} chars")
    click.echo(f"  preview: {content[:preview_chars].strip()}")
    click.echo("")
