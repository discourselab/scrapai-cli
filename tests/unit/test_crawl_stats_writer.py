"""
Unit tests for the per-crawl stats writer (BaseDBSpiderMixin.closed) and the
sitemap audit counters (SitemapDatabaseSpider._sm_total / _sm_eligible).

On a clean finish (reason == "finished") the spider must dump its own crawl
stats to data/<project>/_audit/crawl_stats/<spider>.json — items scraped,
requests made, an HTTP-status histogram from Scrapy's downloader stats, and
(for sitemap spiders) the sitemap size + rule-eligible count recorded while
parsing. Any other close reason (--limit test runs, cancellation) must write
NOTHING, so a partial run can never overwrite a real crawl's numbers.
"""

import json
import os

import pytest
from unittest.mock import MagicMock, Mock, patch

from spiders.sitemap_spider import SitemapDatabaseSpider
from core.models import Spider

pytestmark = pytest.mark.unit


def _make_active_spider_record(name="bbc_co_uk", rules=None, project="testproj"):
    """Return a Mock Spider DB record that loads cleanly (mirrors
    test_sitemap_spider.py, plus an explicit .project for closed())."""
    rec = Mock(spec=Spider)
    rec.id = 42
    rec.name = name
    rec.active = True
    rec.allowed_domains = ["bbc.co.uk"]
    rec.start_urls = ["https://bbc.co.uk/sitemap.xml"]
    rec.rules = rules if rules is not None else []
    rec.callbacks_config = {}
    rec.settings = []
    rec.project = project
    return rec


def _make_rule(allow=None, deny=None, callback="parse_article", priority=0):
    """Mock a DB Rule record for sitemap rule compilation."""
    rule = Mock()
    rule.allow_patterns = allow or []
    rule.deny_patterns = deny or []
    rule.callback = callback
    rule.priority = priority
    return rule


def _patch_get_db(mock_get_db, spider_record):
    """Wire a mocked get_db() context manager to return ``spider_record``."""
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = spider_record
    cm = MagicMock()
    cm.__enter__.return_value = mock_db
    mock_get_db.return_value = cm


FAKE_STATS = {
    "item_scraped_count": 42,
    "downloader/request_count": 100,
    "downloader/response_status_count/200": 90,
    "downloader/response_status_count/404": 8,
    "downloader/response_status_count/503": 2,
    # Added by commit 408562a (proxy success signal) — must NOT leak into the
    # status histogram, which filters by the downloader prefix.
    "proxy/success": 5,
}


def _make_spider(mock_get_db, rules=None, stats=None, item_limit=0):
    _patch_get_db(mock_get_db, _make_active_spider_record(rules=rules))
    spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")
    crawler = Mock()
    crawler.stats.get_stats.return_value = dict(stats or FAKE_STATS)
    crawler.settings.getint.return_value = item_limit  # CLOSESPIDER_ITEMCOUNT
    spider.crawler = crawler
    return spider


def _stats_path(tmp_path):
    return os.path.join(
        str(tmp_path), "testproj", "_audit", "crawl_stats", "bbc_co_uk.json"
    )


class TestCrawlStatsWriter:
    """closed('finished') writes the crawl's own stats for the audit."""

    @patch("spiders.sitemap_spider.get_db")
    def test_finished_writes_stats_json(self, mock_get_db, tmp_path, monkeypatch):
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db)

        spider.closed("finished")

        path = _stats_path(tmp_path)
        assert os.path.exists(path)
        with open(path) as fh:
            data = json.load(fh)
        assert data["spider"] == "bbc_co_uk"
        assert data["reason"] == "finished"
        assert data["items"] == 42
        assert data["requests"] == 100
        # Histogram keyed by bare status code; proxy/success filtered out.
        assert data["status"] == {"200": 90, "404": 8, "503": 2}

    @patch("spiders.sitemap_spider.get_db")
    def test_non_finished_reason_writes_nothing(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        """--limit test crawls end with e.g. 'closespider_itemcount'; they must
        never overwrite a real crawl's numbers."""
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db)

        spider.closed("cancelled")
        spider.closed("closespider_itemcount")

        assert not os.path.exists(_stats_path(tmp_path))
        # Not even the directory should appear.
        assert not os.path.exists(os.path.join(str(tmp_path), "testproj"))

    @patch("spiders.sitemap_spider.get_db")
    def test_item_capped_run_writes_nothing_even_when_finished(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        """A --limit/health crawl that runs out of items UNDER its limit still
        closes with reason 'finished' — the CLOSESPIDER_ITEMCOUNT setting, not
        the close reason, marks it as a capped test run."""
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db, item_limit=5)

        spider.closed("finished")

        assert not os.path.exists(_stats_path(tmp_path))
        assert not os.path.exists(os.path.join(str(tmp_path), "testproj"))

    @patch("spiders.sitemap_spider.get_db")
    def test_sitemap_counters_included_when_recorded(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db)
        spider._sm_total = 600
        spider._sm_eligible = 550

        spider.closed("finished")

        with open(_stats_path(tmp_path)) as fh:
            data = json.load(fh)
        assert data["sitemap_total"] == 600
        assert data["eligible"] == 550

    @patch("spiders.sitemap_spider.get_db")
    def test_sitemap_counters_omitted_when_zero(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        """A spider that saw no sitemap pages omits the keys entirely, so the
        audit falls back to fetching the sitemap."""
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db)

        spider.closed("finished")

        with open(_stats_path(tmp_path)) as fh:
            data = json.load(fh)
        assert "sitemap_total" not in data
        assert "eligible" not in data

    @patch("spiders.sitemap_spider.get_db")
    def test_write_failure_never_raises(self, mock_get_db, monkeypatch):
        """Stats-writing must not fail a crawl."""
        monkeypatch.setattr("core.config.DATA_DIR", "/proc/nonexistent/forbidden")
        spider = _make_spider(mock_get_db)

        spider.closed("finished")  # must not raise


class _FakeUrlset(list):
    """Stand-in for Scrapy's Sitemap object over a <urlset> (type attr set)."""

    type = "urlset"


class _FakeSitemapIndex(list):
    """Stand-in for Scrapy's Sitemap object over a <sitemapindex>."""

    type = "sitemapindex"


class TestSitemapAuditCounters:
    """sitemap_filter() counts _sm_total (page locs) and _sm_eligible (survived
    date + deny AND matched an allow rule)."""

    @patch("spiders.sitemap_spider.get_db")
    def test_total_and_eligible_counted(self, mock_get_db):
        rule = _make_rule(allow=["/article/.*"], deny=[r"\.pdf$"])
        _patch_get_db(mock_get_db, _make_active_spider_record(rules=[rule]))
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = _FakeUrlset(
            [
                {"loc": "https://bbc.co.uk/article/1"},  # eligible
                {"loc": "https://bbc.co.uk/article/2"},  # eligible
                {"loc": "https://bbc.co.uk/about"},  # page, but no allow match
                {"loc": "https://bbc.co.uk/article/x.pdf"},  # denied
                {"loc": "https://bbc.co.uk/sub-sitemap.xml"},  # not a page loc
            ]
        )

        out = list(spider.sitemap_filter(entries))

        # .xml loc is not a page; everything else is.
        assert spider._sm_total == 4
        # Only the two /article/ pages that also survive the deny filter.
        assert spider._sm_eligible == 2
        # The filter itself still yields everything not denied.
        assert len(out) == 4

    @patch("spiders.sitemap_spider.get_db")
    def test_match_all_fallback_counts_all_pages(self, mock_get_db):
        """No rules -> ("/", parse_article) fallback -> every page eligible."""
        _patch_get_db(mock_get_db, _make_active_spider_record(rules=[]))
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = _FakeUrlset(
            [
                {"loc": "https://bbc.co.uk/post-1"},
                {"loc": "https://bbc.co.uk/post-2"},
            ]
        )
        list(spider.sitemap_filter(entries))

        assert spider._sm_match_all is True
        assert spider._sm_total == 2
        assert spider._sm_eligible == 2

    @patch("spiders.sitemap_spider.get_db")
    def test_sitemapindex_entries_never_counted(self, mock_get_db):
        """Sub-sitemap refs in a <sitemapindex> are not content pages — they
        must not inflate the coverage denominator."""
        _patch_get_db(mock_get_db, _make_active_spider_record(rules=[]))
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = _FakeSitemapIndex(
            [
                {"loc": "https://bbc.co.uk/sitemap.xml?page=1"},
                {"loc": "https://bbc.co.uk/sitemap.xml?page=2"},
            ]
        )
        out = list(spider.sitemap_filter(entries))

        assert spider._sm_total == 0
        assert spider._sm_eligible == 0
        assert len(out) == 2  # still passed through for recursion

    @patch("spiders.sitemap_spider.get_db")
    def test_relative_loc_counted_and_matched_after_resolution(self, mock_get_db):
        """Eligibility is checked on the resolved absolute loc."""
        rule = _make_rule(allow=["/article/.*"])
        _patch_get_db(mock_get_db, _make_active_spider_record(rules=[rule]))
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = _FakeUrlset([{"loc": "/article/relative"}])
        out = list(spider.sitemap_filter(entries))

        assert out[0]["loc"] == "https://bbc.co.uk/article/relative"
        assert spider._sm_total == 1
        assert spider._sm_eligible == 1


class TestAuditReadsWriterOutput:
    """The quality tool must parse the file closed() writes (same schema).

    Skipped when the quality tool isn't in the tree (it ships separately);
    runs automatically once both halves are present.
    """

    @patch("spiders.sitemap_spider.get_db")
    def test_quality_tool_parses_written_stats(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        qa = pytest.importorskip(
            "core.quality.crawl_audit", reason="quality tool not in this tree"
        )
        if not hasattr(qa, "crawl_ran"):  # bare namespace pkg (pycache residue)
            pytest.skip("quality tool not in this tree")
        from core.quality.crawl_audit import (
            crawl_ran,
            crawl_stats_liveness,
            crawl_stats_sitemap,
        )
        from core.quality.crawl_audit import spiders_db

        # Writer resolves via core.config.DATA_DIR; readers via the module copy.
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        monkeypatch.setattr(spiders_db, "DATA_DIR", str(tmp_path))

        spider = _make_spider(mock_get_db)
        spider._sm_total = 600
        spider._sm_eligible = 550
        spider.closed("finished")

        assert crawl_ran("testproj", "bbc_co_uk") is True
        live = crawl_stats_liveness("testproj", "bbc_co_uk")
        # 2xx=90, 4xx+5xx=10 -> 90/100
        assert live == {"rate": 0.9, "sample": 100}
        sm = crawl_stats_sitemap("testproj", "bbc_co_uk")
        assert sm == {"total": 600, "eligible": 550}

    def test_quality_tool_absent_file(self, tmp_path, monkeypatch):
        qa = pytest.importorskip(
            "core.quality.crawl_audit", reason="quality tool not in this tree"
        )
        if not hasattr(qa, "crawl_ran"):  # bare namespace pkg (pycache residue)
            pytest.skip("quality tool not in this tree")
        from core.quality.crawl_audit import (
            crawl_ran,
            crawl_stats_liveness,
            crawl_stats_sitemap,
        )
        from core.quality.crawl_audit import spiders_db

        monkeypatch.setattr(spiders_db, "DATA_DIR", str(tmp_path))

        assert crawl_ran("testproj", "missing") is False
        assert crawl_stats_liveness("testproj", "missing") is None
        assert crawl_stats_sitemap("testproj", "missing") is None


class TestResumeDetection:
    """A resumed (checkpoint) crawl restarts every in-memory counter, so it
    must never claim a whole-crawl sitemap denominator. Detection reads the
    scheduler's own persisted queue state: JOBDIR/requests.queue/active.json
    is a non-empty priority list after an interrupt, an empty list after a
    clean finish."""

    def _crawler(self, tmp_path, state):
        crawler = Mock()
        crawler.settings.get.return_value = str(tmp_path)  # JOBDIR
        qdir = tmp_path / "requests.queue"
        qdir.mkdir()
        if state is not None:
            (qdir / "active.json").write_text(json.dumps(state))
        return crawler

    def test_pending_state_detected_as_resume(self, tmp_path):
        crawler = self._crawler(tmp_path, [0, 10])
        assert SitemapDatabaseSpider._resumed_from_checkpoint(crawler) is True

    def test_clean_finish_state_is_fresh(self, tmp_path):
        crawler = self._crawler(tmp_path, [])
        assert SitemapDatabaseSpider._resumed_from_checkpoint(crawler) is False

    def test_missing_state_is_fresh(self, tmp_path):
        crawler = self._crawler(tmp_path, None)
        assert SitemapDatabaseSpider._resumed_from_checkpoint(crawler) is False

    def test_no_jobdir_is_fresh(self):
        crawler = Mock()
        crawler.settings.get.return_value = None
        assert SitemapDatabaseSpider._resumed_from_checkpoint(crawler) is False

    @patch("spiders.sitemap_spider.get_db")
    def test_resumed_run_withholds_sitemap_keys(
        self, mock_get_db, tmp_path, monkeypatch
    ):
        """The resumed leg's stats file is marked and carries NO denominator —
        the audit falls back to fetching the sitemap instead of trusting a
        partial count."""
        monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
        spider = _make_spider(mock_get_db)
        spider._sm_total = 600
        spider._sm_eligible = 550
        spider._resumed = True

        spider.closed("finished")

        with open(_stats_path(tmp_path)) as fh:
            data = json.load(fh)
        assert data["resumed"] is True
        assert "sitemap_total" not in data and "eligible" not in data
        assert data["items"] == 42  # leg-only numbers still recorded
