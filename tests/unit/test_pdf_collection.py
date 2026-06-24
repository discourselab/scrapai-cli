"""PDF handling is governed by the PDF_MODE setting (default "links_only"):

links_only (default): do NOT follow/download PDFs. Record PDF URLs found on a
                      page as lightweight URL-only items (no text).
extract:             follow .pdf links, download, and extract their text.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from scrapy.http import HtmlResponse, Response

from spiders.database_spider import DatabaseSpider
from spiders.base import _clean_pdf_text, _extract_pdf_text, _pdf_links
from core.models import Spider, SpiderRule

pytestmark = pytest.mark.unit


def _rule(allow=None, callback=None):
    r = Mock(spec=SpiderRule)
    r.allow_patterns = allow
    r.deny_patterns = None
    r.restrict_xpaths = None
    r.restrict_css = None
    r.tags = None
    r.callback = callback
    r.follow = True
    r.priority = 0
    return r


def _build(rules, pdf_mode="links_only"):
    rec = Mock(spec=Spider)
    rec.name = "x_com"
    rec.active = True
    rec.allowed_domains = ["x.com"]
    rec.start_urls = ["https://x.com"]
    rec.rules = rules
    rec.callbacks_config = {}
    setting = Mock()
    setting.key = "PDF_MODE"
    setting.value = pdf_mode
    rec.settings = [setting]
    rec.id = 7
    with patch("spiders.database_spider.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = rec
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        with patch.object(DatabaseSpider, "_load_settings_from_db"), patch.object(
            DatabaseSpider, "_setup_cloudflare_handlers"
        ):
            spider = DatabaseSpider(spider_name="x_com")
    spider.custom_settings = {"PDF_MODE": pdf_mode}
    return spider


# --- following: governed by PDF_MODE -----------------------------------------


def test_pdf_links_not_followed_in_default_links_only():
    spider = _build([_rule(allow=[".*"])])  # default links_only
    le = spider.rules[0].link_extractor
    html = (
        '<a href="https://x.com/report.pdf">pdf</a>'
        '<a href="https://x.com/page.html">html</a>'
    )
    resp = HtmlResponse(url="https://x.com/", body=html.encode(), encoding="utf-8")
    urls = [link.url for link in le.extract_links(resp)]
    assert not any(u.endswith("report.pdf") for u in urls)  # NOT followed by default
    assert any(u.endswith("page.html") for u in urls)


def test_pdf_links_followed_in_extract_mode_other_binaries_denied():
    spider = _build([_rule(allow=[".*"])], pdf_mode="extract")
    le = spider.rules[0].link_extractor
    html = (
        '<a href="https://x.com/report.pdf">pdf</a>'
        '<a href="https://x.com/archive.zip">zip</a>'
        '<a href="https://x.com/page.html">html</a>'
    )
    resp = HtmlResponse(url="https://x.com/", body=html.encode(), encoding="utf-8")
    urls = [link.url for link in le.extract_links(resp)]
    assert any(u.endswith("report.pdf") for u in urls)  # followed in extract mode
    assert not any(
        u.endswith("archive.zip") for u in urls
    )  # other binaries still denied
    assert any(u.endswith("page.html") for u in urls)


# --- links_only: collect PDF URLs from a page, no download -------------------


def test_pdf_links_extracts_absolute_pdf_urls():
    html = (
        '<a href="/a.pdf">a</a>'
        '<a href="https://y.com/b.pdf?x=1">b</a>'
        '<a href="/c.html">c</a>'
    )
    resp = HtmlResponse(url="https://x.com/", body=html.encode(), encoding="utf-8")
    urls = _pdf_links(resp)
    assert "https://x.com/a.pdf" in urls
    assert "https://y.com/b.pdf?x=1" in urls
    assert not any(u.endswith(".html") for u in urls)


def test_pdf_links_empty_on_non_html_response():
    assert _pdf_links(Response(url="https://x.com/doc.pdf")) == []


async def test_links_only_yields_url_only_items_for_pdf_links(monkeypatch):
    spider = _build([_rule(allow=[".*"], callback="parse_article")])  # default

    async def _no_article(*a, **k):
        for _ in []:
            yield

    monkeypatch.setattr(spider, "_extract_article", _no_article)
    html = '<a href="/docs/a.pdf">A</a><a href="https://x.com/b.pdf">B</a>'
    resp = HtmlResponse(
        url="https://x.com/article", body=html.encode(), encoding="utf-8"
    )
    items = [i async for i in spider.parse_article(resp)]
    urls = {i["url"] for i in items}
    assert "https://x.com/docs/a.pdf" in urls
    assert "https://x.com/b.pdf" in urls
    assert all(i["content"] == "" for i in items)  # links only — no text
    assert all(i["metadata_json"]["content_type"] == "pdf" for i in items)


# --- PDF response detection (a followed/start-url PDF) -----------------------


async def test_pdf_response_yields_url_item():
    spider = _build([_rule(allow=[".*"], callback="parse_article")])
    resp = Response(url="https://x.com/files/report.pdf")

    items = [i async for i in spider._extract_article(resp)]
    assert len(items) == 1
    assert items[0]["url"] == "https://x.com/files/report.pdf"
    assert items[0]["title"] == "report.pdf"
    assert items[0]["metadata_json"]["content_type"] == "pdf"


async def test_pdf_detected_by_content_type():
    spider = _build([_rule(allow=[".*"], callback="parse_article")])
    resp = Response(
        url="https://x.com/download?id=9", headers={"Content-Type": "application/pdf"}
    )
    items = [i async for i in spider._extract_article(resp)]
    assert items[0]["metadata_json"]["content_type"] == "pdf"


async def test_pdf_text_extracted_only_in_extract_mode(monkeypatch):
    monkeypatch.setattr("spiders.base._extract_pdf_text", lambda b: "EXTRACTED BODY")

    # extract mode -> content has the text
    spider = _build([_rule(allow=[".*"], callback="parse_article")], pdf_mode="extract")
    resp = Response(url="https://x.com/doc.pdf", body=b"%PDF-1.4 fake")
    items = [i async for i in spider._extract_article(resp)]
    assert items[0]["content"] == "EXTRACTED BODY"

    # links_only (default) -> URL only, no text even if a PDF response arrives
    spider2 = _build([_rule(allow=[".*"], callback="parse_article")])
    items2 = [i async for i in spider2._extract_article(resp)]
    assert items2[0]["content"] == ""
    assert items2[0]["url"].endswith("doc.pdf")


# --- text extraction + cleanup (used by extract mode) ------------------------


def test_clean_pdf_text_removes_soft_hyphens():
    assert _clean_pdf_text("scar\xadcity") == "scarcity"
    assert _clean_pdf_text("scar\xad\ncity") == "scarcity"


def test_clean_pdf_text_dehyphenates_and_dewraps():
    out = _clean_pdf_text("cli-\nmate change is\nhappening.\nNew Section")
    assert "climate" in out
    assert "change is happening" in out
    assert "happening.\nNew Section" in out


def test_clean_pdf_text_normalizes_carriage_returns():
    out = _clean_pdf_text("would \r not have \r\nbeen possible")
    assert "\r" not in out
    assert "would not have been possible" in out


def test_extract_pdf_text_empty_on_non_pdf_or_empty_bytes():
    assert _extract_pdf_text(b"this is not a pdf") == ""
    assert _extract_pdf_text(b"") == ""
