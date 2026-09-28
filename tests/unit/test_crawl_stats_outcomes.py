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
