"""Fail-loud browser-wedge detection + browser Pueue group (docs/requests/17).

Two wedge signatures, both counting browser-service errors only: 20 of the
last 100 downloader attempts failing in the browser service stops the crawl
mid-way; zero responses with at least one browser-service error fails a crawl
too small to reach the window. Pages the site blocks, and transport errors on
the HTTP fetch, are not the browser service and must never count.
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import textwrap
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from scrapy.exceptions import IgnoreRequest, NotConfigured

from cli.crawl import BROWSER_GROUP, _ensure_browser_group, _spider_transport
from extensions.browser_wedge import (
    WEDGE_THRESHOLD,
    WEDGE_WINDOW,
    BrowserWedgeDetector,
    is_browser_service_error,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
SERVICE_ERROR = Exception(
    "Browser service failed to verify CF for https://site01.example/a: verify failed"
)
# What a site block and a transport failure look like to the handler.
BLOCK_ERROR = Exception("Still blocked after reverify: https://site01.example/a")
TRANSPORT_ERROR = Exception(
    "HTTP fetch failed for https://site01.example/a: curl: (60) SSL certificate "
    "problem: unable to get local issuer certificate"
)


def _detector(tmp_path, stats=None):
    crawler = Mock()
    crawler.stats.get_stats.return_value = stats or {}
    crawler.engine.downloader.slots = {}
    marker = tmp_path / ".browser_wedge.json"
    mw = BrowserWedgeDetector(crawler, str(marker))
    spider = Mock()
    spider.spider_name = "example_org"
    return mw, spider, marker


def _request():
    request = Mock()
    request.meta = {}
    return request


def _attempt(mw, exc=None):
    """One downloader attempt: it leaves the downloader, then its outcome."""
    request = _request()
    mw.request_left_downloader(request, None)
    if exc is not None:
        mw.process_exception(request, exc)


# --- classification ----------------------------------------------------------


def test_classifies_browser_service_errors_only():
    assert is_browser_service_error(SERVICE_ERROR)
    assert is_browser_service_error(
        OSError("browser service unreachable while verifying CF for https://x")
    )
    # CloudflareDownloadHandler._run_async re-raises the bare 300 s timeout;
    # before Python 3.11 that is concurrent.futures.TimeoutError.
    assert is_browser_service_error(TimeoutError())
    assert is_browser_service_error(concurrent.futures.TimeoutError())
    assert not is_browser_service_error(BLOCK_ERROR)
    assert not is_browser_service_error(TRANSPORT_ERROR)
    assert not is_browser_service_error(IgnoreRequest("robots.txt"))

    class OtherTimeout(TimeoutError):
        pass

    assert not is_browser_service_error(OtherTimeout("curl: (28) timed out"))


async def test_handler_carries_the_service_reason(monkeypatch):
    from handlers.cloudflare_handler import CloudflareDownloadHandler

    monkeypatch.setattr(
        "utils.browser_client.request",
        lambda *a, **k: {"ok": False, "error": "verify failed"},
    )
    spider = Mock()
    spider.custom_settings = {}
    with pytest.raises(Exception) as err:
        await CloudflareDownloadHandler({})._verify_via_service(
            "https://site01.example/a", spider
        )
    assert str(err.value).endswith("https://site01.example/a: verify failed")
    assert is_browser_service_error(err.value)


@pytest.mark.parametrize(
    "reason, is_service",
    [
        ("verify failed", True),
        ("navigation error: Timeout 60000ms exceeded.", True),
        ("navigation error: Target page, context or browser has been closed", True),
        ("challenge not passed after 120s", False),
        ("challenge not passed (geo-blocked)", False),
        ("navigation error: net::ERR_NAME_NOT_RESOLVED at https://x", False),
        ("Page.goto: net::ERR_CONNECTION_RESET at https://x", False),
    ],
)
async def test_site_refusals_are_not_service_errors(monkeypatch, reason, is_service):
    from handlers.cloudflare_handler import CloudflareDownloadHandler

    monkeypatch.setattr(
        "utils.browser_client.request",
        lambda *a, **k: {"ok": False, "error": reason},
    )
    spider = Mock()
    spider.custom_settings = {}
    with pytest.raises(Exception) as err:
        await CloudflareDownloadHandler({})._verify_via_service(
            "https://site01.example/a", spider
        )
    assert str(err.value).endswith(reason)
    assert is_browser_service_error(err.value) is is_service


# --- rolling window ----------------------------------------------------------


def test_window_trips_at_threshold_not_before(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    mw._trip = Mock()
    for _ in range(WEDGE_THRESHOLD - 1):
        _attempt(mw, SERVICE_ERROR)
    mw._trip.assert_not_called()
    _attempt(mw, SERVICE_ERROR)
    mw._trip.assert_called_once()
    assert (WEDGE_THRESHOLD, WEDGE_WINDOW) == (20, 100)


def test_window_forgets_errors_older_than_100_attempts(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    mw._trip = Mock()
    for _ in range(WEDGE_THRESHOLD - 1):
        _attempt(mw, SERVICE_ERROR)
    for _ in range(WEDGE_WINDOW):
        _attempt(mw)  # healthy responses push the old errors out
    _attempt(mw, SERVICE_ERROR)
    mw._trip.assert_not_called()


def test_window_is_exactly_100_attempts(tmp_path):
    for clean, trips in ((80, True), (81, False)):
        mw, spider, marker = _detector(tmp_path)
        mw._trip = Mock()
        for _ in range(WEDGE_THRESHOLD - 1):
            _attempt(mw, SERVICE_ERROR)  # attempts 1..19
        for _ in range(clean):
            _attempt(mw)
        _attempt(mw, SERVICE_ERROR)  # attempt 100 keeps attempt 1; 101 drops it
        assert mw._trip.called is trips


def test_late_exception_counts_at_its_own_attempt(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    slow = _request()
    mw.request_left_downloader(slow, None)  # attempt 1
    for _ in range(WEDGE_WINDOW + 50):
        _attempt(mw)
    mw.process_exception(slow, SERVICE_ERROR)  # arrives 150 attempts later
    assert mw.recent == []  # already outside the window: not counted


def test_trip_log_names_the_attempts_seen(tmp_path, caplog):
    mw, spider, marker = _detector(tmp_path)
    with patch("extensions.browser_wedge.deferred_from_coro"):
        for _ in range(WEDGE_THRESHOLD):
            _attempt(mw, SERVICE_ERROR)
    assert "20 of the last 20 downloads" in caplog.text
    assert (mw.window_errors, mw.window_seen) == (20, 20)


def test_project_settings_load_it_above_the_retry_middleware():
    from scrapy.settings.default_settings import DOWNLOADER_MIDDLEWARES_BASE

    import settings

    order = settings.DOWNLOADER_MIDDLEWARES[
        "extensions.browser_wedge.BrowserWedgeDetector"
    ]
    retry = DOWNLOADER_MIDDLEWARES_BASE[
        "scrapy.downloadermiddlewares.retry.RetryMiddleware"
    ]
    assert order == 950
    assert order > retry  # sees every attempt, retries included


def test_window_ignores_block_and_transport_errors(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    mw._trip = Mock()
    for _ in range(WEDGE_WINDOW):
        _attempt(mw, BLOCK_ERROR)
        _attempt(mw, TRANSPORT_ERROR)
    mw._trip.assert_not_called()
    assert mw.service_errors == 0


def test_trip_stops_crawl_once_and_drops_queued_requests(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    queued = [(Mock(), Mock()), (Mock(), Mock())]
    slot = Mock()
    slot.queue = deque(queued)
    mw.crawler.engine.downloader.slots = {"site01.example": slot}
    with patch("extensions.browser_wedge.deferred_from_coro") as dfc:
        for _ in range(WEDGE_THRESHOLD + 5):
            _attempt(mw, SERVICE_ERROR)
    mw.crawler.engine.close_spider_async.assert_called_once_with(reason="browser_wedge")
    dfc.assert_called_once()
    assert not slot.queue
    for _request, dfd in queued:
        assert isinstance(dfd.errback.call_args.args[0], IgnoreRequest)
    with pytest.raises(IgnoreRequest):
        mw.process_request(Mock())


def test_partial_wedge_writes_marker(tmp_path):
    stats = {"downloader/response_count": 250, "item_scraped_count": 240}
    mw, spider, marker = _detector(tmp_path, stats)
    with patch("extensions.browser_wedge.deferred_from_coro"):
        for _ in range(WEDGE_WINDOW - WEDGE_THRESHOLD):
            _attempt(mw)
        for _ in range(WEDGE_THRESHOLD + 3):  # errors after the trip
            _attempt(mw, SERVICE_ERROR)
    mw.spider_closed(spider)
    data = json.loads(marker.read_text())
    assert data["kind"] == "partial"
    # The window as it stood at the trip, not after later errors piled in.
    assert (data["window_errors"], data["window"]) == (WEDGE_THRESHOLD, 100)
    assert data["responses"] == 250


# --- zero-response rule (crawls too small to reach the window) ---------------


def test_total_wedge_writes_marker(tmp_path):
    stats = {"downloader/response_count": 0, "downloader/exception_count": 3}
    mw, spider, marker = _detector(tmp_path, stats)
    for _ in range(3):
        _attempt(mw, SERVICE_ERROR)
    mw.spider_closed(spider)
    data = json.loads(marker.read_text())
    assert data["spider"] == "example_org"
    assert data["kind"] == "total"
    assert data["service_errors"] == 3


def test_all_blocked_small_crawl_is_not_a_wedge(tmp_path):
    # Zero responses because the SITE refused every page: not the service.
    stats = {"downloader/response_count": 0, "downloader/exception_count": 5}
    mw, spider, marker = _detector(tmp_path, stats)
    for _ in range(5):
        _attempt(mw, BLOCK_ERROR)
    mw.spider_closed(spider)
    assert not marker.exists()


def test_responses_mean_no_wedge(tmp_path):
    stats = {"downloader/response_count": 12, "downloader/exception_count": 4}
    mw, spider, marker = _detector(tmp_path, stats)
    for _ in range(4):
        _attempt(mw, SERVICE_ERROR)
    mw.spider_closed(spider)
    assert not marker.exists()


def test_deltafetch_empty_crawl_is_not_a_wedge(tmp_path):
    # Everything filtered before download: no responses AND no exceptions.
    stats = {"downloader/response_count": 0, "downloader/exception_count": 0}
    mw, spider, marker = _detector(tmp_path, stats)
    mw.spider_closed(spider)
    assert not marker.exists()


def test_stale_marker_removed_on_open(tmp_path):
    mw, spider, marker = _detector(tmp_path)
    marker.write_text("{}")
    mw.spider_opened(spider)
    assert not marker.exists()


def test_inert_without_marker_setting():
    crawler = Mock()
    crawler.settings.get.return_value = None
    with pytest.raises(NotConfigured):
        BrowserWedgeDetector.from_crawler(crawler)
    crawler.signals.connect.assert_not_called()


def test_module_carries_no_author_attribution():
    source = (REPO / "extensions" / "browser_wedge.py").read_text()
    assert "added for" not in source.lower()


# --- in a real Scrapy crawl (fake download handler, no network) --------------

_FAKE_CRAWL = textwrap.dedent("""
    import json, sys
    from scrapy import Request, Spider, signals
    from scrapy.crawler import CrawlerProcess
    from twisted.internet.task import deferLater

    from extensions.browser_wedge import BrowserWedgeDetector

    marker, out, mode, n_urls, order = sys.argv[1:6]
    n_urls, order = int(n_urls), int(order)
    attempts = {"n": 0, "at_trip": None, "queued_at_trip": None}
    _trip = BrowserWedgeDetector._trip

    def trip(self):  # record what had been sent / was waiting at the stop
        attempts["at_trip"] = attempts["n"]
        slots = self.crawler.engine.downloader.slots.values()
        attempts["queued_at_trip"] = sum(len(s.queue) for s in slots)
        _trip(self)

    BrowserWedgeDetector._trip = trip

    class Handler:
        lazy = False

        @classmethod
        def from_crawler(cls, crawler):
            return cls()

        def download_request(self, request, spider=None):
            from scrapy.http import HtmlResponse
            from twisted.internet import reactor  # the one Scrapy installed

            attempts["n"] += 1
            i = int(request.url.rsplit("/", 1)[1])
            if mode == "gap" and 19 <= i < 119:  # 100 good pages between
                ok = HtmlResponse(request.url, body=b"ok", request=request)
                return deferLater(reactor, 0, lambda: ok)
            if mode == "retry":  # retried by RetryMiddleware (an OSError)
                exc = OSError("browser service unreachable for %s" % request.url)
            else:
                exc = Exception(
                    "Browser service failed to verify CF for %s: verify failed"
                    % request.url
                )
            return deferLater(reactor, 0.01, lambda: (_ for _ in ()).throw(exc))

        async def close(self):
            pass

    class S(Spider):
        name = "s"

        async def start(self):
            for i in range(n_urls):
                yield Request(
                    "https://site01.example/%d" % i, errback=lambda f: None
                )

        def parse(self, response):
            pass

    p = CrawlerProcess({
        "DOWNLOAD_HANDLERS": {"https": "__main__.Handler"},
        "DOWNLOADER_MIDDLEWARES": {
            "extensions.browser_wedge.BrowserWedgeDetector": order,
        },
        "BROWSER_WEDGE_MARKER": marker,
        # "gap" runs one request at a time so the order of outcomes is fixed.
        "CONCURRENT_REQUESTS": 1 if mode == "gap" else 32,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1 if mode == "gap" else 2,
        "DOWNLOAD_DELAY": 0 if mode == "gap" else 0.02,  # requests wait
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "LOG_LEVEL": "ERROR",
        "TELNETCONSOLE_ENABLED": False,
    })
    crawler = p.create_crawler(S)
    p.crawl(crawler)
    p.start()
    attempts["reason"] = crawler.stats.get_value("finish_reason")
    json.dump(attempts, open(out, "w"))
    """)


def _fake_crawl(tmp_path, mode, n_urls, order=None):
    if order is None:
        import settings

        order = settings.DOWNLOADER_MIDDLEWARES[
            "extensions.browser_wedge.BrowserWedgeDetector"
        ]
    script = tmp_path / "fake_crawl.py"
    script.write_text(_FAKE_CRAWL)
    marker, out = tmp_path / "marker.json", tmp_path / "out.json"
    env = dict(os.environ, PYTHONPATH=str(REPO))
    subprocess.run(
        [sys.executable, str(script), str(marker), str(out), mode]
        + [str(n_urls), str(order)],
        cwd=tmp_path,
        env=env,
        check=True,
        timeout=120,
    )
    return json.loads(out.read_text()), marker


def test_real_crawl_stops_at_threshold_without_sending_queued(tmp_path):
    result, marker = _fake_crawl(tmp_path, "wedge", 300)
    assert result["reason"] == "browser_wedge"
    # Requests were waiting inside the downloader at the stop; none of them is
    # sent. At most the one download in transfer (delay-paced slot) finishes.
    assert result["queued_at_trip"] > 0
    assert result["n"] - result["at_trip"] <= 1
    assert result["n"] < 300
    data = json.loads(marker.read_text())
    assert (data["kind"], data["stopped"]) == ("total", True)  # 0 responses


def test_real_crawl_counts_retried_attempts(tmp_path):
    # 10 URLs, each tried 3 times (OSError is retried): 30 attempts, 10 final.
    result, marker = _fake_crawl(tmp_path, "retry", 10)
    assert result["reason"] == "browser_wedge"
    # Only 10 attempts are final; the window must see the 20+ retried ones.
    assert WEDGE_THRESHOLD <= result["at_trip"] <= 30


def test_real_crawl_forgets_errors_100_attempts_back(tmp_path):
    # 19 errors, 100 good pages, 19 errors: never 20 within 100 attempts.
    result, marker = _fake_crawl(tmp_path, "gap", 138)
    assert result["reason"] == "finished"
    assert result["n"] == 138
    assert not marker.exists()


# --- CLI: exit 3, message, checkpoint ----------------------------------------


def _run_cli(monkeypatch, tmp_path, marker_data, returncode=0, rows=()):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(crawl_mod, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("utils.display_helper.needs_xvfb", lambda: False)

    def fake_run(cmd, *a, **k):
        if rows:  # the crawl appends its items to the -o file, like scrapy -o
            with open(cmd[cmd.index("-o") + 1], "a") as fh:
                fh.writelines(f'{{"url": "{r}"}}\n' for r in rows)
        for arg in cmd:
            if marker_data is not None and arg.startswith("BROWSER_WEDGE_MARKER="):
                Path(arg.split("=", 1)[1]).write_text(json.dumps(marker_data))
        return Mock(returncode=returncode)

    monkeypatch.setattr(crawl_mod.subprocess, "run", fake_run)
    setting = Mock()
    setting.key, setting.value = "CLOUDFLARE_ENABLED", "true"
    rec = Mock()
    rec.settings = [setting]
    rec.rules = []
    with patch("core.db.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = rec
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        rc = crawl_mod._run_spider("news", "example_org", detached=True)
    spider_dir = tmp_path / "data" / "news" / "example_org"
    assert (spider_dir / "crawls").is_dir()  # the crawl output stays
    return rc, spider_dir / "checkpoint"


def test_cli_partial_wedge_exits_3_and_deletes_checkpoint(
    monkeypatch, tmp_path, capsys
):
    marker = {
        "kind": "partial",
        "window_errors": 20,
        "window": 100,
        "responses": 250,
        "items": 240,
        "service_errors": 20,
    }
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, marker)
    out = capsys.readouterr().out
    assert rc == 3
    assert "💀 BROWSER CRAWL WEDGED — stopped mid-crawl: 20 of the last 100" in out
    assert "Checkpoint deleted" in out
    assert not checkpoint.exists()


def test_cli_total_wedge_exits_3(monkeypatch, tmp_path, capsys):
    marker = {"kind": "total", "service_errors": 7, "responses": 0}
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, marker)
    assert rc == 3
    assert "💀 BROWSER CRAWL WEDGED: 0 responses, 7 browser-service errors" in (
        capsys.readouterr().out
    )
    assert not checkpoint.exists()


def test_cli_clean_crawl_keeps_exit_0(monkeypatch, tmp_path, capsys):
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, None)
    assert not rc  # crawl() exits 0
    assert "WEDGED" not in capsys.readouterr().out


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


def test_cli_wedge_uploads_the_partial_crawl_file(monkeypatch, tmp_path, capsys):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    uploads = []
    checkpoint = tmp_path / "data" / "news" / "example_org" / "checkpoint"
    monkeypatch.setattr(
        crawl_mod,
        "_upload_crawl_file",
        lambda f, p, s, **k: uploads.append(
            (Path(f).parent.name, p, s, checkpoint.exists(), k)
        ),
    )
    rc, _ = _run_cli(monkeypatch, tmp_path, {"kind": "total", "service_errors": 3})
    assert rc == 3
    # Uploaded like a finished crawl, before the checkpoint is deleted.
    assert uploads == [("crawls", "news", "example_org", True, {"keep_local": True})]
    assert not checkpoint.exists()


def test_cli_failed_crawl_propagates_its_exit_code(monkeypatch, tmp_path):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    uploads = []
    monkeypatch.setattr(crawl_mod, "_upload_crawl_file", lambda *a: uploads.append(a))
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, None, returncode=1)
    assert rc == 1
    assert checkpoint.exists()  # kept for the resume
    assert uploads == []  # only a successful (or stopped) crawl is uploaded


def test_same_day_rerun_after_a_stop_keeps_both_runs_in_s3(monkeypatch, tmp_path):
    # The stopped crawl's upload keeps the local file; the same-day re-run
    # appends to it, and its upload to the same key holds both runs' rows.
    import gzip
    import sys
    import types

    store = {}

    class FakeS3:
        def upload_file(self, path, bucket, key):
            store[key] = gzip.open(path).read().decode()

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *a, **k: FakeS3()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    for var in ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_ENDPOINT", "S3_BUCKET"):
        monkeypatch.setenv(var, "x")

    rc, _ = _run_cli(
        monkeypatch, tmp_path, {"kind": "total", "service_errors": 3}, rows=["a", "b"]
    )
    assert rc == 3
    rc, _ = _run_cli(monkeypatch, tmp_path, None, rows=["c"])
    assert not rc
    (content,) = store.values()
    assert [json.loads(line)["url"] for line in content.splitlines()] == ["a", "b", "c"]
    assert not list(
        (tmp_path / "data" / "news" / "example_org" / "crawls").glob("*.jsonl")
    )
