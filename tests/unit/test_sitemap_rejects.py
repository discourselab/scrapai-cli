"""
Unit tests for rejected-sitemap detection (SitemapDatabaseSpider).

Scrapy's SitemapSpider._parse_sitemap drops a sitemap whose body is not a
urlset or sitemapindex ("Ignoring invalid sitemap"), and every URL in it with
it. The spider must count that (stat sitemap/rejected), warn, list the URL in
the crawl-stats file (sitemap_rejected) and keep the body, bounded, under
data/<project>/_audit/sitemap_rejects/<spider>/, without changing what Scrapy
does with the response. All responses here are built in memory.
"""

import json
import logging

import pytest
from unittest.mock import MagicMock, Mock, patch
from scrapy.http import HtmlResponse, Request, TextResponse, XmlResponse
from scrapy.spiders import SitemapSpider

from core.models import Spider
from spiders import sitemap_spider as sm
from spiders.base import _add_leg_counts
from spiders.sitemap_spider import SitemapDatabaseSpider

pytestmark = pytest.mark.unit

SPIDER = "example_org"
PROJECT = "proj"
HTML_VIEW = (
    b"<!DOCTYPE html><html><head><title>XML Sitemap</title></head>"
    b"<body><table><tr><td>https://example.org/a</td></tr></table></body></html>"
)
URLSET = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<?xml-stylesheet type="text/xsl" href="/sitemap.xsl"?>'
    b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<url><loc>https://example.org/a</loc></url>"
    b"<url><loc>https://example.org/b</loc></url></urlset>"
)
INDEX = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    b"<sitemap><loc>https://example.org/post-sitemap.xml</loc></sitemap>"
    b"</sitemapindex>"
)


def _make_spider(get_db_mock, item_limit=0, jobdir=None):
    rec = Mock(spec=Spider)
    rec.id = 7
    rec.name = SPIDER
    rec.active = True
    rec.allowed_domains = ["example.org"]
    rec.start_urls = ["https://example.org/sitemap.xml"]
    rec.rules = []
    rec.callbacks_config = {}
    rec.settings = []
    rec.project = PROJECT
    db = Mock()
    filtered = db.query.return_value.filter.return_value
    filtered.first.return_value = rec
    filtered.all.return_value = [rec]
    cm = MagicMock()
    cm.__enter__.return_value = db
    get_db_mock.return_value = cm

    spider = SitemapDatabaseSpider(spider_name=SPIDER)
    crawler = Mock()
    crawler.stats.get_stats.return_value = {}
    crawler.settings.getint.return_value = item_limit  # CLOSESPIDER_ITEMCOUNT
    crawler.settings.get.side_effect = lambda k, d=None: (
        str(jobdir) if (k == "JOBDIR" and jobdir) else d
    )
    spider.crawler = crawler
    return spider


def _open(spider, resumed=False):
    spider._resumed = resumed
    spider._open_sitemap_rejects(spider.crawler)


def _rejects_dir(tmp_path):
    return tmp_path / PROJECT / "_audit" / "sitemap_rejects" / SPIDER


def _stats(tmp_path):
    path = tmp_path / PROJECT / "_audit" / "crawl_stats" / f"{SPIDER}.json"
    return json.loads(path.read_text())


def _html(url="https://example.org/sitemap.xml", body=HTML_VIEW, status=200):
    return HtmlResponse(
        url=url,
        status=status,
        body=body,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


def _xml(url, body):
    return XmlResponse(url=url, body=body, headers={"Content-Type": "text/xml"})


def _rejected_incs(spider):
    return [
        c
        for c in spider.crawler.stats.inc_value.call_args_list
        if c.args and c.args[0] == "sitemap/rejected"
    ]


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    return tmp_path


@patch("spiders.sitemap_spider.get_db")
def test_non_xml_200_is_counted_and_kept(db, data_dir, caplog):
    spider = _make_spider(db)
    _open(spider)
    url = "https://example.org/sitemap.xml"

    with caplog.at_level(logging.WARNING):
        result = list(spider._parse_sitemap(_html(url)))

    # Scrapy's own handling is unchanged: nothing scheduled from it.
    assert result == []
    assert len(_rejected_incs(spider)) == 1
    warning = [
        r.getMessage() for r in caplog.records if "Sitemap rejected" in r.message
    ]
    assert warning and url in warning[0]
    assert "status 200" in warning[0] and f"{len(HTML_VIEW)} bytes" in warning[0]

    folder = _rejects_dir(data_dir)
    index = json.loads((folder / "index.json").read_text())
    assert index == [
        {
            "file": "01_sitemap.xml.txt",
            "url": url,
            "status": 200,
            "bytes": len(HTML_VIEW),
            "content_type": "text/html; charset=utf-8",
        }
    ]
    assert (folder / "01_sitemap.xml.txt").read_bytes() == HTML_VIEW

    spider.closed("finished")
    assert _stats(data_dir)["sitemap_rejected"] == [url]


@patch("spiders.sitemap_spider.get_db")
def test_body_scrapy_cannot_get_is_counted(db, data_dir):
    """_get_sitemap_body() returns None for a non-XML response at a URL not
    ending .xml: Scrapy's first rejection rule."""
    spider = _make_spider(db)
    _open(spider)
    url = "https://example.org/sitemap_index"

    assert list(spider._parse_sitemap(_html(url))) == []
    assert spider._sm_rejected == [url]
    assert len(_rejected_incs(spider)) == 1


def test_rejection_rules_mirror_scrapy():
    assert sm._scrapy_rejects(None) is True
    assert sm._scrapy_rejects(b"") is True
    assert sm._scrapy_rejects(HTML_VIEW) is True
    assert sm._scrapy_rejects(b"Forbidden") is True  # no root element
    assert sm._scrapy_rejects(URLSET) is False
    assert sm._scrapy_rejects(INDEX) is False


@patch("spiders.sitemap_spider.get_db")
def test_valid_urlset_and_index_not_counted(db, data_dir):
    spider = _make_spider(db)
    _open(spider)

    pages = list(spider._parse_sitemap(_xml("https://example.org/s.xml", URLSET)))
    subs = list(spider._parse_sitemap(_xml("https://example.org/i.xml", INDEX)))

    assert [r.url for r in pages] == ["https://example.org/a", "https://example.org/b"]
    assert [r.url for r in subs] == ["https://example.org/post-sitemap.xml"]
    assert _rejected_incs(spider) == []
    assert not _rejects_dir(data_dir).exists()
    spider.closed("finished")
    data = _stats(data_dir)
    assert data["sitemap_rejected"] == []
    assert data["sitemap_total"] == 2


@patch("spiders.sitemap_spider.get_db")
def test_robots_txt_unaffected(db, data_dir):
    spider = _make_spider(db)
    _open(spider)
    robots = TextResponse(
        url="https://example.org/robots.txt",
        body=b"User-agent: *\nSitemap: https://example.org/sitemap.xml\n",
    )

    out = list(spider._parse_sitemap(robots))

    assert [r.url for r in out] == ["https://example.org/sitemap.xml"]
    assert all(isinstance(r, Request) for r in out)
    assert _rejected_incs(spider) == []
    assert not _rejects_dir(data_dir).exists()
    spider.closed("finished")
    assert _stats(data_dir)["sitemap_rejected"] == []


@patch("spiders.sitemap_spider.get_db")
def test_size_cap_holds(db, data_dir):
    spider = _make_spider(db)
    _open(spider)
    big = b"<html>" + b"x" * (sm.REJECTS_MAX_BYTES + 5000) + b"</html>"

    spider._parse_sitemap(_html(body=big))

    folder = _rejects_dir(data_dir)
    entry = json.loads((folder / "index.json").read_text())[0]
    assert entry["bytes"] == len(big)
    assert (folder / entry["file"]).stat().st_size == sm.REJECTS_MAX_BYTES == 262144


@patch("spiders.sitemap_spider.get_db")
def test_count_cap_holds(db, data_dir):
    spider = _make_spider(db)
    _open(spider)
    urls = [f"https://example.org/sitemap-{i}.xml" for i in range(25)]

    for url in urls:
        spider._parse_sitemap(_html(url))

    folder = _rejects_dir(data_dir)
    index = json.loads((folder / "index.json").read_text())
    assert len(index) == sm.REJECTS_MAX_FILES == 20
    assert len(list(folder.glob("*.txt"))) == 20
    # Every rejection is still counted and listed; only the bodies are capped.
    assert len(_rejected_incs(spider)) == 25
    spider.closed("finished")
    assert _stats(data_dir)["sitemap_rejected"] == urls


@patch("spiders.sitemap_spider.get_db")
def test_fresh_production_crawl_clears_folder(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    (folder / "01_old.xml.txt").write_bytes(b"stale")
    (folder / "index.json").write_text("[]")
    spider = _make_spider(db)

    _open(spider, resumed=False)

    assert not folder.exists()


@patch("spiders.sitemap_spider.get_db")
def test_fresh_crawl_clears_through_from_crawler(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    (folder / "01_old.xml.txt").write_bytes(b"stale")
    spider = _make_spider(db)
    base = classmethod(lambda cls, crawler, *a, **kw: spider)

    with patch.object(SitemapSpider, "from_crawler", base):
        assert SitemapDatabaseSpider.from_crawler(spider.crawler) is spider

    assert spider._resumed is False
    assert not folder.exists()


@patch("spiders.sitemap_spider.get_db")
def test_resumed_leg_keeps_folder_and_continues_index(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    old = {
        "file": "01_old.xml.txt",
        "url": "https://example.org/old.xml",
        "status": 200,
        "bytes": 5,
        "content_type": "text/html",
    }
    (folder / "01_old.xml.txt").write_bytes(b"stale")
    (folder / "index.json").write_text(json.dumps([old]))
    spider = _make_spider(db)

    _open(spider, resumed=True)
    spider._parse_sitemap(_html("https://example.org/new.xml"))

    assert (folder / "01_old.xml.txt").read_bytes() == b"stale"
    index = json.loads((folder / "index.json").read_text())
    assert [e["file"] for e in index] == ["01_old.xml.txt", "02_new.xml.txt"]


@patch("spiders.sitemap_spider.get_db")
def test_resumed_leg_cap_spans_legs(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    urls = [f"https://example.org/s{i}.xml" for i in range(1, sm.REJECTS_MAX_FILES + 1)]
    earlier = [
        {"file": f"{i:02d}_x.txt", "url": u, "status": 200, "bytes": 1}
        for i, u in enumerate(urls, 1)
    ]
    (folder / "index.json").write_text(json.dumps(earlier))
    spider = _make_spider(db)

    _open(spider, resumed=True)
    spider._parse_sitemap(_html("https://example.org/late.xml"))

    assert not (folder / "21_late.xml.txt").exists()
    assert len(json.loads((folder / "index.json").read_text())) == 20
    assert spider._sm_rejected == urls + ["https://example.org/late.xml"]


@patch("spiders.sitemap_spider.get_db")
def test_capped_run_keeps_nothing(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    (folder / "01_old.xml.txt").write_bytes(b"production evidence")
    spider = _make_spider(db, item_limit=5)

    _open(spider)
    spider._parse_sitemap(_html("https://example.org/sitemap.xml"))

    # Not cleared, nothing added; the stat still counts it.
    assert sorted(p.name for p in folder.iterdir()) == ["01_old.xml.txt"]
    assert len(_rejected_incs(spider)) == 1


def test_leg_union_keeps_order():
    data = {
        "sitemap_rejected": ["https://example.org/b.xml", "https://example.org/c.xml"]
    }
    earlier = {
        "sitemap_rejected": ["https://example.org/a.xml", "https://example.org/b.xml"]
    }

    _add_leg_counts(data, earlier)

    assert data["sitemap_rejected"] == [
        "https://example.org/a.xml",
        "https://example.org/b.xml",
        "https://example.org/c.xml",
    ]


@patch("spiders.sitemap_spider.get_db")
def test_resumed_crawl_writes_union_of_legs(db, data_dir, tmp_path):
    jobdir = tmp_path / "checkpoint"
    jobdir.mkdir()
    leg1 = _make_spider(db, jobdir=jobdir)
    _open(leg1)
    leg1._parse_sitemap(_html("https://example.org/a.xml"))
    leg1.closed("shutdown")

    leg2 = _make_spider(db, jobdir=jobdir)
    _open(leg2, resumed=True)
    leg2._earlier_legs = SitemapDatabaseSpider._take_leg_stats(leg2.crawler)
    leg2._parse_sitemap(_html("https://example.org/b.xml"))
    leg2.closed("finished")

    data = _stats(data_dir)
    assert data["summed"] is True
    assert data["sitemap_rejected"] == [
        "https://example.org/a.xml",
        "https://example.org/b.xml",
    ]
    index = json.loads((_rejects_dir(data_dir) / "index.json").read_text())
    assert [e["file"] for e in index] == ["01_a.xml.txt", "02_b.xml.txt"]


@patch("spiders.sitemap_spider.get_db")
def test_body_with_no_root_is_counted_and_kept(db, data_dir):
    """Plain text at a .xml URL has no root element: Scrapy's Sitemap() raises
    (a spider error). It is a rejection like the others."""
    spider = _make_spider(db)
    _open(spider)
    url = "https://example.org/sitemap.xml"
    forbidden = TextResponse(
        url=url, body=b"Forbidden", headers={"Content-Type": "text/plain"}
    )

    assert list(spider._parse_sitemap(forbidden)) == []

    assert len(_rejected_incs(spider)) == 1
    folder = _rejects_dir(data_dir)
    assert (folder / "01_sitemap.xml.txt").read_bytes() == b"Forbidden"
    entry = json.loads((folder / "index.json").read_text())[0]
    assert entry["content_type"] == "text/plain" and entry["bytes"] == 9
    spider.closed("finished")
    assert _stats(data_dir)["sitemap_rejected"] == [url]


@patch("spiders.sitemap_spider.get_db")
def test_other_parse_errors_still_raise(db, data_dir):
    spider = _make_spider(db)
    _open(spider)

    def boom(self, response):
        self._get_sitemap_body(response)
        raise ValueError("not a rejection")

    with patch.object(SitemapSpider, "_parse_sitemap", boom):
        with pytest.raises(ValueError):
            spider._parse_sitemap(_xml("https://example.org/s.xml", URLSET))
    assert _rejected_incs(spider) == []


@patch("spiders.sitemap_spider.get_db")
def test_resumed_leg_with_unreadable_index_never_overwrites(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    (folder / "01_sitemap.xml.txt").write_bytes(b"first leg")
    (folder / "02_sitemap.xml.txt").write_bytes(b"second body")
    (folder / "index.json").write_text("{not json")
    spider = _make_spider(db)

    _open(spider, resumed=True)
    spider._parse_sitemap(_html("https://example.org/sitemap.xml"))

    assert (folder / "01_sitemap.xml.txt").read_bytes() == b"first leg"
    assert (folder / "02_sitemap.xml.txt").read_bytes() == b"second body"
    assert (folder / "03_sitemap.xml.txt").read_bytes() == HTML_VIEW


@patch("spiders.sitemap_spider.get_db")
def test_resumed_leg_with_unreadable_index_keeps_the_cap(db, data_dir):
    folder = _rejects_dir(data_dir)
    folder.mkdir(parents=True)
    for i in range(1, sm.REJECTS_MAX_FILES + 1):
        (folder / f"{i:02d}_sitemap.xml.txt").write_bytes(b"kept")
    spider = _make_spider(db)

    _open(spider, resumed=True)
    spider._parse_sitemap(_html("https://example.org/sitemap.xml"))

    assert len(list(folder.glob("*.txt"))) == sm.REJECTS_MAX_FILES
    assert {p.read_bytes() for p in folder.glob("*.txt")} == {b"kept"}
    assert spider._sm_rejected == ["https://example.org/sitemap.xml"]


@patch("spiders.sitemap_spider.get_db")
def test_lazy_parent_generator_does_not_flag_valid_sitemaps(db, data_dir):
    """Older Scrapy versions return a generator from _parse_sitemap: the body
    is only read once it is iterated, so the check must come after that."""
    spider = _make_spider(db)
    _open(spider)
    eager = SitemapSpider._parse_sitemap

    def lazy(self, response):
        yield from eager(self, response)

    with patch.object(SitemapSpider, "_parse_sitemap", lazy):
        pages = spider._parse_sitemap(_xml("https://example.org/s.xml", URLSET))
        subs = spider._parse_sitemap(_xml("https://example.org/i.xml", INDEX))
        bad = spider._parse_sitemap(_html("https://example.org/sitemap.xml"))

    assert [r.url for r in pages] == ["https://example.org/a", "https://example.org/b"]
    assert [r.url for r in subs] == ["https://example.org/post-sitemap.xml"]
    assert list(bad) == []
    assert spider._sm_rejected == ["https://example.org/sitemap.xml"]
    assert len(_rejected_incs(spider)) == 1


@patch("spiders.sitemap_spider.get_db")
def test_resumed_unsummed_leg_reports_earlier_rejections(db, data_dir, tmp_path):
    """Leg 1 rejects a sitemap and dies without closing: no leg file, so no
    summing. The kept index still lists it, and the resumed leg reports it."""
    jobdir = tmp_path / "checkpoint"
    jobdir.mkdir()
    leg1 = _make_spider(db, jobdir=jobdir)
    _open(leg1)
    leg1._parse_sitemap(_html("https://example.org/a.xml"))
    # leg 1 never reaches closed()

    leg2 = _make_spider(db, jobdir=jobdir)
    _open(leg2, resumed=True)
    leg2._earlier_legs = SitemapDatabaseSpider._take_leg_stats(leg2.crawler)
    assert leg2._earlier_legs is None
    leg2._parse_sitemap(_html("https://example.org/b.xml"))
    leg2.closed("finished")

    data = _stats(data_dir)
    assert data["resumed"] is True and "summed" not in data
    assert data["sitemap_rejected"] == [
        "https://example.org/a.xml",
        "https://example.org/b.xml",
    ]


@patch("spiders.sitemap_spider.get_db")
def test_spider_name_outside_the_folder_never_clears(db, data_dir, caplog):
    audit = data_dir / PROJECT / "_audit"
    (audit / "crawl_stats").mkdir(parents=True)
    (audit / "crawl_stats" / "other.json").write_text("{}")
    spider = _make_spider(db)
    spider.spider_name = ".."

    with caplog.at_level(logging.WARNING):
        _open(spider)
        spider._parse_sitemap(_html("https://example.org/sitemap.xml"))

    assert (audit / "crawl_stats" / "other.json").exists()
    assert spider._sm_rejects_dir is None
    assert not (audit / "01_sitemap.xml.txt").exists()
    assert any(
        "Not keeping rejected-sitemap bodies" in r.message for r in caplog.records
    )


@patch("spiders.sitemap_spider.get_db")
def test_same_sitemap_rejected_twice_is_listed_once(db, data_dir):
    spider = _make_spider(db)
    _open(spider)
    url = "https://example.org/sitemap.xml"

    spider._parse_sitemap(_html(url))
    spider._parse_sitemap(_html(url))

    assert spider._sm_rejected == [url]
    assert len(_rejected_incs(spider)) == 2  # the stat counts every response
    spider.closed("finished")
    assert _stats(data_dir)["sitemap_rejected"] == [url]
