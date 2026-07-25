"""Tests for `scrapai scrape` — extraction and rendering, no network."""

import json

from cli.scrape import _extract, _render

HTML = """
<html><head><title>Test Article</title>
<meta property="article:published_time" content="2026-07-20T10:00:00Z">
<meta name="author" content="Jane Doe">
</head><body><article>
<h1>Test Article</h1>
<p>First paragraph with enough words to survive boilerplate removal by the
generic extractors, which discard very short blocks as navigation chrome.</p>
<p>Second paragraph, also long enough to be kept as real article body text
rather than being treated as a caption or menu item by the extractor.</p>
</article></body></html>
"""


def test_extract_returns_content_and_markdown():
    article = _extract("https://example.com/a", HTML)
    assert article is not None
    assert "First paragraph" in (article.content or "")
    assert "First paragraph" in (article.markdown or "")


def test_extract_returns_none_on_empty_page():
    assert _extract("https://example.com/a", "<html><body></body></html>") is None


def test_render_formats():
    article = _extract("https://example.com/a", HTML)

    assert _render(article, "markdown") == article.markdown
    assert _render(article, "text") == article.content

    payload = json.loads(_render(article, "json"))
    assert payload["url"] == "https://example.com/a"
    assert "First paragraph" in payload["markdown"]


def test_render_markdown_falls_back_to_text():
    """An extractor that produced no clean_html still yields usable output."""

    class NoMarkdown:
        url = "https://example.com/a"
        title = "t"
        author = None
        published_date = None
        markdown = None
        content = "plain text body"

    assert _render(NoMarkdown(), "markdown") == "plain text body"
