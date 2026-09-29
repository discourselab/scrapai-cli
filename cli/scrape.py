"""`scrapai scrape` — fetch one URL and print its content. No spider, no database."""

import contextlib
import json
import os
import sys
import tempfile

import click


@click.command()
@click.argument("url")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "text", "json"]),
    default="markdown",
    help="Output format (default markdown)",
)
@click.option(
    "--browser",
    is_flag=True,
    help="Force the browser; without this the transport auto-escalates",
)
@click.option(
    "--session",
    default=None,
    help="Reuse a saved login session (see `scrapai session login`)",
)
@click.option(
    "--proxy-type",
    default="auto",
    help="Proxy to use: auto/none, or any name configured in .env",
)
@click.option("--output", "-o", default=None, help="Write to a file instead of stdout")
def scrape(url, fmt, browser, session, proxy_type, output):
    """Fetch a single URL and print its clean content.

    One-shot: no spider, no project, nothing written to the database. Transport
    escalates HTTP -> curl_cffi -> browser, so Cloudflare-protected pages work
    the same as plain ones. Progress goes to stderr, content to stdout:

        scrapai scrape https://example.com/article > article.md
    """
    html = _fetch(url, browser, session, proxy_type)
    if not html:
        raise click.ClickException(f"Could not fetch {url}")

    article = _extract(url, html)
    if not article:
        raise click.ClickException(
            f"Fetched {url} but extracted no content — the page may be JS-rendered "
            f"(retry with --browser) or not an article."
        )

    rendered = _render(article, fmt)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(rendered)
        click.echo(f"Wrote {len(rendered):,} chars to {output}", err=True)
    else:
        click.echo(rendered)


def _fetch(url, browser, session, proxy_type):
    """Fetch one URL, escalating HTTP -> curl_cffi -> browser as needed.

    Reuses inspect's transport path rather than adding a third copy of the
    ladder. The inspector writes page.html and prints progress, so it runs
    against a temp dir with stdout redirected to stderr — nothing is left on
    disk and stdout stays clean for piping.
    """
    from cli.inspect_cmd import _run_browser_inspect
    from utils.inspector import inspect_page

    with tempfile.TemporaryDirectory() as tmp:
        page = os.path.join(tmp, "page.html")
        with contextlib.redirect_stdout(sys.stderr):
            if browser:
                _run_browser_inspect(
                    url, "default", tmp, proxy_type, False, session=session
                )
            else:
                result = inspect_page(
                    url, tmp, proxy_type, True, mode="http", session=session
                )
                if result and result.get("needs_browser"):
                    click.echo(
                        "Lightweight transports blocked — escalating to browser…",
                        err=True,
                    )
                    _run_browser_inspect(
                        url, "default", tmp, proxy_type, False, session=session
                    )
        if os.path.exists(page):
            with open(page, encoding="utf-8") as f:
                return f.read()
    return None


def _extract(url, html):
    """Run the generic extractors in EXTRACTOR_ORDER's default order."""
    from core.extractors import NewspaperExtractor, TrafilaturaExtractor

    for extractor in (TrafilaturaExtractor(), NewspaperExtractor()):
        article = extractor.extract(url, html)
        if article and (article.markdown or article.content):
            return article
    return None


def _render(article, fmt):
    """Render a ScrapedArticle in the requested output format."""
    if fmt == "json":
        return json.dumps(
            {
                "url": article.url,
                "title": article.title,
                "author": article.author,
                "published_date": (
                    str(article.published_date) if article.published_date else None
                ),
                "markdown": article.markdown,
                "content": article.content,
            },
            indent=2,
            ensure_ascii=False,
        )
    if fmt == "text":
        return article.content or ""
    # markdown needs clean_html; extractors that produced none fall back to text
    return article.markdown or article.content or ""
