"""Fail-loud browser-wedge detection + browser Pueue group (docs/requests/17).

The wedge signature is zero downloader responses with at least one downloader
exception: nothing loaded and the browser path was throwing. A legitimately
empty re-crawl (DeltaFetch filters everything) has no exceptions and must not
trigger; a partially successful crawl has responses and must not trigger.
"""

import json
from unittest.mock import Mock

import pytest

from cli.crawl import BROWSER_GROUP, _ensure_browser_group, _spider_transport
from extensions.browser_wedge import BrowserWedgeDetector

pytestmark = pytest.mark.unit


def _detector(tmp_path, stats):
    crawler = Mock()
    crawler.stats.get_stats.return_value = stats
    marker = tmp_path / ".browser_wedge.json"
    ext = BrowserWedgeDetector(crawler, str(marker))
    spider = Mock()
    spider.spider_name = "x_com"
    return ext, spider, marker


def test_wedge_writes_marker(tmp_path):
    stats = {
        "downloader/response_count": 0,
        "downloader/exception_count": 7,
        "item_scraped_count": 0,
    }
    ext, spider, marker = _detector(tmp_path, stats)
    ext.spider_closed(spider)
    data = json.loads(marker.read_text())
    assert data["spider"] == "x_com"
    assert data["exceptions"] == 7


def test_responses_mean_no_wedge(tmp_path):
    stats = {"downloader/response_count": 12, "downloader/exception_count": 40}
    ext, spider, marker = _detector(tmp_path, stats)
    ext.spider_closed(spider)
    assert not marker.exists()


def test_deltafetch_empty_crawl_is_not_a_wedge(tmp_path):
    # Everything filtered before download: no responses AND no exceptions.
    stats = {"downloader/response_count": 0, "downloader/exception_count": 0}
    ext, spider, marker = _detector(tmp_path, stats)
    ext.spider_closed(spider)
    assert not marker.exists()


def test_stale_marker_removed_on_open(tmp_path):
    ext, spider, marker = _detector(tmp_path, {})
    marker.write_text("{}")
    ext.spider_opened(spider)
    assert not marker.exists()


def test_inert_without_marker_setting():
    crawler = Mock()
    crawler.settings.get.return_value = None
    BrowserWedgeDetector.from_crawler(crawler)
    crawler.signals.connect.assert_not_called()


def test_group_parallelism_only_set_on_creation(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        # First invocation: `pueue group add` succeeds (new group).
        return Mock(returncode=0 if cmd[1] == "group" else 0)

    import subprocess  # the same module object cli.crawl imported

    monkeypatch.setattr(subprocess, "run", fake_run)
    _ensure_browser_group()
    assert calls[0][:3] == ["pueue", "group", "add"]
    assert ["--group", BROWSER_GROUP] == calls[1][-2:]

    # Existing group: `group add` fails -> parallelism left untouched.
    calls.clear()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: (calls.append(cmd), Mock(returncode=1))[1],
    )
    _ensure_browser_group()
    assert len(calls) == 1


def test_spider_transport_detection():
    def setting(key, value):
        s = Mock()
        s.key, s.value = key, value
        return s

    cf, sm, repo = _spider_transport([setting("CLOUDFLARE_ENABLED", "true")], False)
    assert (cf, sm, repo) == (True, False, False)
    cf, sm, repo = _spider_transport([setting("USE_SITEMAP", "True")], False)
    assert (cf, sm, repo) == (False, True, False)
    cf, sm, repo = _spider_transport([setting("REPOSITORY_SOURCE", {"a": 1})], False)
    assert repo is True
    # --browser CLI flag alone
    cf, sm, repo = _spider_transport([], True)
    assert cf is True
