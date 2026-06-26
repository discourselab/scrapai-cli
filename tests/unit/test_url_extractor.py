"""extract-urls reads both ordinary HTML (<a href>) and sitemaps (<loc>),
so the agent can enumerate a sitemap during analysis (not just at crawl time).
"""

import pytest

from utils.url_extractor import extract_urls_from_html

pytestmark = pytest.mark.unit


def test_reads_sitemap_loc_urls(tmp_path):
    f = tmp_path / "sitemap.xml"
    f.write_text(
        '<?xml version="1.0"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://x.com/a</loc></url>"
        "<url><loc>https://x.com/b</loc></url>"
        "</urlset>"
    )
    out = extract_urls_from_html(str(f))
    assert "https://x.com/a" in out and "https://x.com/b" in out


def test_reads_sitemap_index_subsitemaps(tmp_path):
    f = tmp_path / "sitemap_index.xml"
    f.write_text(
        '<?xml version="1.0"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://x.com/post-sitemap.xml</loc></sitemap>"
        "<sitemap><loc>https://x.com/page-sitemap.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    out = extract_urls_from_html(str(f))
    assert "https://x.com/post-sitemap.xml" in out
    assert "https://x.com/page-sitemap.xml" in out


def test_still_reads_plain_html_hrefs(tmp_path):
    f = tmp_path / "page.html"
    f.write_text(
        '<html><body><a href="https://x.com/1">a</a><a href="/rel">b</a></body></html>'
    )
    out = extract_urls_from_html(str(f))
    assert "https://x.com/1" in out and "/rel" in out


def test_html_text_containing_loc_is_not_treated_as_sitemap(tmp_path):
    # "geolocation" contains "loc" — must NOT trip sitemap detection.
    f = tmp_path / "p.html"
    f.write_text('<html><body><a href="/x">geolocation services</a></body></html>')
    out = extract_urls_from_html(str(f))
    assert out == ["/x"]
