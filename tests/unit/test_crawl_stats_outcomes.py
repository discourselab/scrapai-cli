"""
Unit tests for the raw outcome counters in the per-crawl stats file
(BaseDBSpiderMixin.closed): responses, final_status, exceptions, retries.

These are Scrapy's own counters stored uninterpreted, so the audit can derive
outcomes later without re-crawling. They must always be present ({} / 0 when
Scrapy recorded nothing) so a reader can tell a new-format file from an old
one, and the item-capped skip must still apply.
"""

import json
import os

import pytest
from unittest.mock import MagicMock, Mock, patch

from spiders.sitemap_spider import SitemapDatabaseSpider
from core.models import Spider

pytestmark = pytest.mark.unit

SPIDER = "site01_org"
PROJECT = "proj"

OUTCOME_STATS = {
    "item_scraped_count": 70,
    "downloader/request_count": 120,
    "response_received_count": 95,
    # Attempt-level histogram: retried 503s are counted here.
    "downloader/response_status_count/200": 80,
    "downloader/response_status_count/404": 6,
    "downloader/response_status_count/503": 9,
    # Final non-2xx responses (after retries).
    "httperror/response_ignored_count": 9,
    "httperror/response_ignored_status_count/404": 6,
    "httperror/response_ignored_status_count/503": 3,
    "downloader/exception_count": 25,
    "downloader/exception_type_count/scrapy.exceptions.IgnoreRequest": 4,
    "downloader/exception_type_count/twisted.internet.error.TimeoutError": 21,
    "retry/count": 27,
    "retry/reason_count/503 Service Unavailable": 6,
    "retry/reason_count/twisted.internet.error.TimeoutError": 21,
    "retry/max_reached": 3,
    "proxy/success": 5,
}


def _make_spider(get_db_mock, stats, item_limit=0):
    rec = Mock(spec=Spider)
    rec.id = 7
    rec.name = SPIDER
    rec.active = True
    rec.allowed_domains = ["site01.example"]
    rec.start_urls = ["https://site01.example/sitemap.xml"]
    rec.rules = []
    rec.callbacks_config = {}
    rec.settings = []
    rec.project = PROJECT
    db = Mock()
    filtered = db.query.return_value.filter.return_value
    # Both lookup shapes: first() by name, all() when scoped per project.
    filtered.first.return_value = rec
    filtered.all.return_value = [rec]
    cm = MagicMock()
    cm.__enter__.return_value = db
    get_db_mock.return_value = cm

    spider = SitemapDatabaseSpider(spider_name=SPIDER)
    crawler = Mock()
    crawler.stats.get_stats.return_value = dict(stats)
    crawler.settings.getint.return_value = item_limit  # CLOSESPIDER_ITEMCOUNT
    spider.crawler = crawler
    return spider


def _stats_path(tmp_path):
    return os.path.join(
        str(tmp_path), PROJECT, "_audit", "crawl_stats", f"{SPIDER}.json"
    )


def _read(tmp_path):
    with open(_stats_path(tmp_path)) as fh:
        return json.load(fh)


@patch("spiders.sitemap_spider.get_db")
def test_outcome_keys_written(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, OUTCOME_STATS)

    spider.closed("finished")

    data = _read(tmp_path)
    assert data["responses"] == 95
    assert data["final_status"] == {"404": 6, "503": 3}
    assert data["exceptions"] == {
        "scrapy.exceptions.IgnoreRequest": 4,
        "twisted.internet.error.TimeoutError": 21,
    }
    assert data["retries"] == {
        "503 Service Unavailable": 6,
        "twisted.internet.error.TimeoutError": 21,
    }
    # Existing keys unchanged; the attempt-level histogram stays separate.
    assert data["status"] == {"200": 80, "404": 6, "503": 9}
    assert data["items"] == 70
    assert data["requests"] == 120


@patch("spiders.sitemap_spider.get_db")
def test_outcome_keys_present_when_stats_empty(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, {})

    spider.closed("finished")

    data = _read(tmp_path)
    assert data["responses"] == 0
    assert data["final_status"] == {}
    assert data["exceptions"] == {}
    assert data["retries"] == {}


@patch("spiders.sitemap_spider.get_db")
def test_outcome_keys_written_on_resumed_leg(db, tmp_path, monkeypatch):
    """Resumed legs keep the counters (flagged by `resumed`), unlike the
    sitemap denominator which is withheld."""
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, OUTCOME_STATS)
    spider._resumed = True

    spider.closed("finished")

    data = _read(tmp_path)
    assert data["resumed"] is True
    assert data["responses"] == 95
    assert data["final_status"] == {"404": 6, "503": 3}


@patch("spiders.sitemap_spider.get_db")
def test_outcome_keys_not_written_on_capped_run(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, OUTCOME_STATS, item_limit=10)

    spider.closed("finished")

    assert not os.path.exists(_stats_path(tmp_path))


def _jobdir_crawler(spider, tmp_path, stats):
    jobdir = tmp_path / "checkpoint"
    jobdir.mkdir(exist_ok=True)
    spider.crawler.stats.get_stats.return_value = dict(stats)
    spider.crawler.settings.get.side_effect = lambda k, d=None: (
        str(jobdir) if k == "JOBDIR" else d
    )
    return jobdir


@patch("spiders.sitemap_spider.get_db")
def test_resumed_crawl_sums_its_legs(db, tmp_path, monkeypatch):
    """Leg 1 stops early and keeps its counters in JOBDIR; the resumed leg
    takes them and writes whole-crawl numbers, marked `summed`."""
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    leg1 = _make_spider(db, OUTCOME_STATS)
    jobdir = _jobdir_crawler(leg1, tmp_path, OUTCOME_STATS)
    leg1._resumed = False
    leg1.closed("shutdown")
    assert not os.path.exists(_stats_path(tmp_path))
    assert (jobdir / "crawl_stats_leg.json").exists()

    leg2 = _make_spider(db, OUTCOME_STATS)
    _jobdir_crawler(leg2, tmp_path, OUTCOME_STATS)
    leg2._resumed = True
    leg2._earlier_legs = SitemapDatabaseSpider._take_leg_stats(leg2.crawler)
    assert not (jobdir / "crawl_stats_leg.json").exists()
    leg2.closed("finished")

    data = _read(tmp_path)
    assert data["resumed"] is True and data["summed"] is True
    assert data["requests"] == 240
    assert data["responses"] == 190
    assert data["final_status"] == {"404": 12, "503": 6}
    assert data["status"] == {"200": 160, "404": 12, "503": 18}


@patch("spiders.sitemap_spider.get_db")
def test_resumed_crawl_without_earlier_counts_is_last_leg(db, tmp_path, monkeypatch):
    """No leg file (the earlier leg died without closing): this leg's own
    numbers, marked resumed but not summed, and nothing kept for later."""
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, OUTCOME_STATS)
    jobdir = _jobdir_crawler(spider, tmp_path, OUTCOME_STATS)
    spider._resumed = True
    spider._earlier_legs = SitemapDatabaseSpider._take_leg_stats(spider.crawler)
    assert spider._earlier_legs is None
    spider.closed("finished")

    data = _read(tmp_path)
    assert data["resumed"] is True and "summed" not in data
    assert data["responses"] == 95
    assert not (jobdir / "crawl_stats_leg.json").exists()


@patch("spiders.sitemap_spider.get_db")
def test_early_stop_without_checkpoint_writes_nothing(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    spider = _make_spider(db, OUTCOME_STATS)
    spider.crawler.settings.get.side_effect = lambda k, d=None: d

    spider.closed("shutdown")

    assert not os.path.exists(_stats_path(tmp_path))
    assert list(tmp_path.iterdir()) == []


def _leg(db, tmp_path, stats, reason, pending):
    """One crawl leg through the real wiring: _apply_cf_to_crawler detects the
    resume from JOBDIR and takes the earlier legs' counters, then closed()."""
    jobdir = tmp_path / "checkpoint"
    (jobdir / "requests.queue").mkdir(parents=True, exist_ok=True)
    (jobdir / "requests.queue" / "active.json").write_text(
        json.dumps([0, 5] if pending else [])
    )
    spider = _make_spider(db, stats)
    spider.crawler.settings.get.side_effect = lambda k, d=None: (
        str(jobdir) if k == "JOBDIR" else d
    )
    SitemapDatabaseSpider._apply_cf_to_crawler(spider, spider.crawler)
    spider.closed(reason)
    return jobdir / "crawl_stats_leg.json"


@patch("spiders.sitemap_spider.get_db")
def test_three_legs_sum_through_the_wiring(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    leg_file = _leg(db, tmp_path, OUTCOME_STATS, "shutdown", pending=False)
    assert leg_file.exists()
    _leg(db, tmp_path, OUTCOME_STATS, "shutdown", pending=True)
    assert json.loads(leg_file.read_text())["requests"] == 240
    _leg(db, tmp_path, OUTCOME_STATS, "finished", pending=True)
    assert not leg_file.exists()

    data = _read(tmp_path)
    assert data["summed"] is True
    assert data["requests"] == 360
    assert data["final_status"] == {"404": 18, "503": 9}


@patch("spiders.sitemap_spider.get_db")
def test_resumed_leg_without_file_interrupted_again_keeps_nothing(
    db, tmp_path, monkeypatch
):
    """Its own counters are not the whole crawl, so they must not be saved as
    if they were: the next leg reports its own leg only."""
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    leg_file = _leg(db, tmp_path, OUTCOME_STATS, "shutdown", pending=True)
    assert not leg_file.exists()


@patch("spiders.sitemap_spider.get_db")
def test_unreadable_leg_file_is_taken_once(db, tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    jobdir = tmp_path / "checkpoint"
    jobdir.mkdir()
    (jobdir / "crawl_stats_leg.json").write_text("{not json")
    _leg(db, tmp_path, OUTCOME_STATS, "finished", pending=True)

    data = _read(tmp_path)
    assert data["resumed"] is True and "summed" not in data
    assert list(jobdir.glob("crawl_stats_leg.json*")) == []
