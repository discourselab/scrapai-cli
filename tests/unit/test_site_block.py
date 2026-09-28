"""Stop a crawl the site is blocking (docs/requests/29).

A page still challenged after a fresh browser re-verify raises SiteBlockedError
(never retried, always counted); a transport failure falls back to the
browser's render and raises HttpTransportError only if that fails too; it is
never a block. SiteBlockGuard stops the crawl when 60 of the last 100
downloader attempts are SiteBlockedError or HTTP 429 (every 429 attempt,
retried or not, unless a live proxy is still to be tried). 403, transport and
browser-service errors never count.
"""

import json
import os
import subprocess
import sys
import textwrap
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request
from scrapy.settings import Settings

from extensions.site_block import BLOCK_THRESHOLD, BLOCK_WINDOW, SiteBlockGuard
from handlers.cloudflare_handler import (
    CloudflareDownloadHandler,
    HttpTransportError,
    SiteBlockedError,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
URL = "https://site01.example/a"
BLOCKED = SiteBlockedError(f"Still blocked after reverify: {URL}")
TRANSPORT = HttpTransportError(f"HTTP fetch failed for {URL}: curl: (35) TLS error")
SERVICE = Exception(f"Browser service failed to verify CF for {URL}: verify failed")


def _guard(tmp_path, stats=None):
    crawler = Mock()
    crawler.stats.get_stats.return_value = stats or {}
    crawler.engine.downloader.slots = {}
    crawler.engine.downloader.middleware.middlewares = []
    marker = tmp_path / "site_block.json"
    guard = SiteBlockGuard(crawler, str(marker))
    return guard, marker


def _response(status):
    return Mock(status=status)


def _attempt(guard, exc=None, status=200):
    """One downloader attempt: it leaves the downloader, then its outcome."""
    guard.request_left_downloader(Mock(url=URL), None)
    if exc is not None:
        guard.process_exception(Mock(url=URL), exc)
    else:
        guard.process_response(Mock(url=URL), _response(status))


# --- window --------------------------------------------------------------------


def test_trips_at_60_blocks_not_59(tmp_path):
    guard, _ = _guard(tmp_path)
    guard._trip = Mock()
    for i in range(BLOCK_THRESHOLD - 1):
        _attempt(guard, BLOCKED) if i % 2 else _attempt(guard, status=429)
    guard._trip.assert_not_called()
    _attempt(guard, status=429)
    guard._trip.assert_called_once()
    assert (BLOCK_THRESHOLD, BLOCK_WINDOW) == (60, 100)


def test_ignores_403_transport_and_browser_service_errors(tmp_path):
    guard, _ = _guard(tmp_path)
    guard._trip = Mock()
    for _ in range(BLOCK_WINDOW):
        _attempt(guard, status=403)
        _attempt(guard, TRANSPORT)
        _attempt(guard, SERVICE)
        _attempt(guard, IgnoreRequest("robots.txt"))
    guard._trip.assert_not_called()
    assert not guard.recent


def test_forgets_blocks_older_than_100_attempts(tmp_path):
    guard, _ = _guard(tmp_path)
    guard._trip = Mock()
    for _ in range(BLOCK_THRESHOLD - 1):
        _attempt(guard, BLOCKED)
    for _ in range(BLOCK_WINDOW):
        _attempt(guard)  # healthy responses push the old blocks out
    _attempt(guard, BLOCKED)
    guard._trip.assert_not_called()


def _smart_proxy(**state):
    from middlewares import SmartProxyMiddleware

    proxy = SmartProxyMiddleware.__new__(SmartProxyMiddleware)
    proxy.__dict__.update(state)
    return proxy


@pytest.mark.parametrize(
    "state, counted",
    [
        ({"proxy_available": True}, False),  # escalation still to come
        ({"proxy_available": True, "proxy_dead": True}, True),  # it will not come
        ({"proxy_available": False}, True),  # no proxy at all
    ],
)
def test_direct_429s_count_unless_a_live_proxy_is_still_to_try(
    tmp_path, state, counted
):
    guard, _ = _guard(tmp_path)
    guard.crawler.engine.downloader.middleware.middlewares = [_smart_proxy(**state)]
    guard._trip = Mock()
    for _ in range(BLOCK_THRESHOLD):
        request = Mock(url=URL, meta={})  # direct: no meta["proxy"]
        guard.request_left_downloader(request, None)
        guard.process_response(request, _response(429))
    assert guard._trip.called is counted
    proxied = Mock(url=URL, meta={"proxy": "http://p.example:8"})
    guard.process_response(proxied, _response(429))
    assert guard.recent[-1][1] == "http_429"  # through the proxy: always counts


def test_window_is_exactly_100_attempts(tmp_path):
    for clean, trips in ((40, True), (41, False)):
        guard, _ = _guard(tmp_path)
        guard._trip = Mock()
        for _ in range(BLOCK_THRESHOLD - 1):
            _attempt(guard, BLOCKED)  # attempts 1..59
        for _ in range(clean):
            _attempt(guard)
        _attempt(guard, BLOCKED)  # attempt 100 keeps attempt 1; 101 drops it
        assert guard._trip.called is trips


def test_every_block_is_counted_in_stats(tmp_path):
    guard, _ = _guard(tmp_path)
    _attempt(guard, BLOCKED)
    _attempt(guard, status=429)
    _attempt(guard, status=403)
    calls = [c.args[0] for c in guard.crawler.stats.inc_value.call_args_list]
    assert calls == ["blocked/site_blocked", "blocked/http_429"]


def test_trip_stops_once_and_drops_queued_requests(tmp_path):
    guard, _ = _guard(tmp_path)
    queued = [(Mock(), Mock()), (Mock(), Mock())]
    slot = Mock()
    slot.queue = deque(queued)
    guard.crawler.engine.downloader.slots = {"site01.example": slot}
    with patch("extensions.site_block.deferred_from_coro") as dfc:
        for _ in range(BLOCK_THRESHOLD + 5):
            _attempt(guard, BLOCKED)
    guard.crawler.engine.close_spider_async.assert_called_once_with(
        reason="site_blocked"
    )
    dfc.assert_called_once()
    assert not slot.queue
    for _request, dfd in queued:
        assert isinstance(dfd.errback.call_args.args[0], IgnoreRequest)
    with pytest.raises(IgnoreRequest):
        guard.process_request(Mock())


def test_marker_written_only_when_tripped(tmp_path):
    stats = {
        "blocked/site_blocked": 70,
        "blocked/http_429": 3,
        "item_scraped_count": 12,
    }
    guard, marker = _guard(tmp_path, stats)
    spider = Mock(spider_name="example_org")
    guard.spider_closed(spider)
    assert not marker.exists()
    with patch("extensions.site_block.deferred_from_coro"):
        for _ in range(BLOCK_THRESHOLD + 3):  # 3 more arrive after the stop
            _attempt(guard, BLOCKED)
    guard.spider_closed(spider)
    data = json.loads(marker.read_text())
    # The window as it stood at the stop.
    assert data["window_counts"] == {"site_blocked": BLOCK_THRESHOLD}
    assert data["window"] == BLOCK_THRESHOLD  # only 60 attempts had run
    assert data["totals"] == {"site_blocked": 70, "http_429": 3}
    assert data["items"] == 12


def test_stale_marker_removed_on_open(tmp_path):
    guard, marker = _guard(tmp_path)
    marker.write_text("{}")
    guard.spider_opened(Mock())
    assert not marker.exists()


# --- handler -------------------------------------------------------------------


def test_site_blocked_is_not_retried_by_scrapy():
    retry = RetryMiddleware(Settings())
    assert not isinstance(BLOCKED, retry.exceptions_to_retry)
    assert not isinstance(TRANSPORT, retry.exceptions_to_retry)
    # The browser-wedge check (docs/requests/17) keys on "browser service".
    assert "browser service" not in str(BLOCKED).lower()
    assert "browser service" not in str(TRANSPORT).lower()


def _handler():
    h = CloudflareDownloadHandler({})
    CloudflareDownloadHandler._cookie_cache = {}
    CloudflareDownloadHandler._refresh_lock = None
    return h


def _spider():
    s = AsyncMock()
    s.name = "example_org"
    s.custom_settings = {}
    return s


def _cookie(handler, spider):
    key = handler._cache_key(spider.name, URL)
    CloudflareDownloadHandler._cookie_cache[key] = {
        "cookies": {"cf_clearance": "x"},
        "user_agent": "UA",
        "seq": 1,
    }


async def test_still_blocked_after_reverify_raises_site_blocked():
    h, spider = _handler(), _spider()
    _cookie(h, spider)
    h._fetch_with_http = AsyncMock(return_value="<title>Just a moment...</title>")
    h._reverify = AsyncMock()
    with pytest.raises(SiteBlockedError, match="Still blocked after reverify"):
        await h._hybrid_fetch_async(Request(URL), spider)
    h._reverify.assert_awaited_once()


async def test_transport_failure_falls_back_to_the_browser_render(tmp_path):
    # curl gets no response; the re-verify renders this URL in the browser.
    h, spider = _handler(), _spider()
    _cookie(h, spider)
    h._fetch_with_http = AsyncMock(side_effect=TRANSPORT)
    page = "<html>" + "real article " * 1000 + "</html>"
    h._reverify = AsyncMock()
    h._consume_browser_html = Mock(side_effect=[None, page])
    assert await h._hybrid_fetch_async(Request(URL), spider) == page
    h._reverify.assert_awaited_once()
    # A captured page is a plain response: the guard counts nothing.
    guard, _ = _guard(tmp_path)
    _attempt(guard)
    assert not guard.recent
    assert guard.crawler.stats.inc_value.call_count == 0


async def test_transport_failure_raises_only_when_the_browser_fails_too():
    h, spider = _handler(), _spider()
    _cookie(h, spider)
    h._fetch_with_http = AsyncMock(side_effect=TRANSPORT)
    h._reverify = AsyncMock()  # no browser render for this URL
    with pytest.raises(HttpTransportError):
        await h._hybrid_fetch_async(Request(URL), spider)
    h._reverify.assert_awaited_once()


async def test_transport_failure_on_a_utility_file_skips_the_browser():
    h, spider = _handler(), _spider()
    _cookie(h, spider)
    h._fetch_with_http = AsyncMock(side_effect=TRANSPORT)
    h._reverify = AsyncMock()
    with pytest.raises(HttpTransportError):
        await h._hybrid_fetch_async(
            Request("https://site01.example/robots.txt"), spider
        )
    h._reverify.assert_not_awaited()


async def test_transport_failure_after_reverify_is_not_a_block():
    h, spider = _handler(), _spider()
    _cookie(h, spider)
    h._fetch_with_http = AsyncMock(
        side_effect=["<title>Just a moment...</title>", TRANSPORT]
    )
    h._reverify = AsyncMock()
    with pytest.raises(HttpTransportError):
        await h._hybrid_fetch_async(Request(URL), spider)


async def test_fetch_with_http_raises_transport_error(monkeypatch):
    import curl_cffi.requests as curl_requests

    def boom(*a, **k):
        raise RuntimeError("curl: (60) SSL certificate problem")

    monkeypatch.setattr(curl_requests, "get", boom)
    cached = {"cookies": {}, "user_agent": "UA"}
    with pytest.raises(HttpTransportError, match="SSL certificate problem"):
        await _handler()._fetch_with_http(URL, cached)


# --- in a real Scrapy crawl (fake download handler, no network) ----------------
#
# The project's own middleware stack: SiteBlockGuard at 960, SmartProxyMiddleware
# at 350, Scrapy's RetryMiddleware at 550 with default settings.

_FAKE_CRAWL = textwrap.dedent("""
    import json, sys
    from scrapy import Request, Spider
    from scrapy.crawler import CrawlerProcess
    from scrapy.http import HtmlResponse
    from twisted.internet.task import deferLater

    from extensions.site_block import SiteBlockGuard
    from handlers.cloudflare_handler import SiteBlockedError

    mode, n_urls, marker, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
    log = {"n": 0, "proxied": 0, "at_trip": None, "queued_at_trip": None}
    _trip = SiteBlockGuard._trip

    def trip(self):  # record what had been sent / was waiting at the stop
        log["at_trip"] = log["n"]
        slots = self.crawler.engine.downloader.slots.values()
        log["queued_at_trip"] = sum(len(s.queue) for s in slots)
        _trip(self)

    SiteBlockGuard._trip = trip

    class Handler:
        lazy = False

        @classmethod
        def from_crawler(cls, crawler):
            return cls()

        def download_request(self, request, spider=None):
            from twisted.internet import defer, reactor  # Scrapy's reactor

            log["n"] += 1
            proxied = bool(request.meta.get("proxy"))
            log["proxied"] += proxied
            i = -1 if request.url.endswith("/seed") else int(request.url.rsplit("/", 1)[1])
            if mode == "gap" and i >= 0:  # 59 blocks, 100 good pages, 59 blocks
                if i < 59 or i >= 159:
                    exc = SiteBlockedError("Still blocked after reverify: " + request.url)
                    return defer.fail(exc)
                ok = HtmlResponse(request.url, status=200, body=b"x", request=request)
                return defer.succeed(ok)
            if mode == "blocked" and not request.url.endswith("/seed"):
                exc = SiteBlockedError("Still blocked after reverify: " + request.url)
                return deferLater(reactor, 0.01, lambda: (_ for _ in ()).throw(exc))
            if request.url.endswith("/seed"):  # a listing page, always served
                status = 200
            elif mode == "proxy_ok":  # the site limits direct requests only
                status = 200 if proxied else 429
            else:
                status = int(mode)
            response = HtmlResponse(
                request.url, status=status, body=b"x", request=request
            )
            return defer.succeed(response)

        async def close(self):
            pass

    class S(Spider):
        name = "s"
        custom_settings = {}  # SmartProxyMiddleware reads it, as on DB spiders

        async def start(self):
            # One listing page links to every URL, so they are all scheduled
            # at once — as on a real site — and retries queue behind them.
            yield Request("https://site01.example/seed", callback=self.links)

        def links(self, response):
            for i in range(n_urls):
                yield Request(
                    "https://site01.example/%d" % i, errback=lambda f: None
                )

        def parse(self, response):
            pass

    p = CrawlerProcess({
        "DOWNLOAD_HANDLERS": {"https": "__main__.Handler"},
        "DOWNLOADER_MIDDLEWARES": {
            "extensions.site_block.SiteBlockGuard": 960,
            "middlewares.SmartProxyMiddleware": 350,
        },
        "SITE_BLOCK_MARKER": marker,
        # "gap" runs one request at a time so the order of outcomes is fixed.
        "CONCURRENT_REQUESTS": {"blocked": 32, "gap": 1}.get(mode, 8),
        "CONCURRENT_REQUESTS_PER_DOMAIN": {"blocked": 2, "gap": 1}.get(mode, 8),
        # "blocked" adds latency and a delay so requests wait in the downloader
        "DOWNLOAD_DELAY": 0.02 if mode == "blocked" else 0,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "LOG_LEVEL": "ERROR",
        "TELNETCONSOLE_ENABLED": False,
    })
    crawler = p.create_crawler(S)
    p.crawl(crawler)
    p.start()
    log["reason"] = crawler.stats.get_value("finish_reason")
    log["retries"] = crawler.stats.get_value("retry/count", 0)
    log["counted_429"] = crawler.stats.get_value("blocked/http_429", 0)
    json.dump(log, open(out, "w"))
    """)


def _fake_crawl(tmp_path, mode, n_urls, proxy=None):
    script = tmp_path / "fake_crawl.py"
    script.write_text(_FAKE_CRAWL)
    marker, out = tmp_path / "marker.json", tmp_path / "out.json"
    env = {k: v for k, v in os.environ.items() if "_PROXY_" not in k}
    env["PYTHONPATH"] = str(REPO)
    if proxy:
        env["DATACENTER_PROXY_URL"] = proxy
    subprocess.run(
        [sys.executable, str(script), mode, str(n_urls), str(marker), str(out)],
        cwd=tmp_path,
        env=env,
        check=True,
        timeout=120,
    )
    return json.loads(out.read_text()), marker


def test_total_429_block_trips_at_attempt_60_and_sends_nothing_after(tmp_path):
    # No proxy configured; default retries (every 429 retried twice).
    result, marker = _fake_crawl(tmp_path, "429", 300)
    assert result["reason"] == "site_blocked"
    # The stop comes on the 60th 429; besides the listing page, only the few
    # downloads already in flight (concurrency 8) had been sent by then.
    assert json.loads(marker.read_text())["window_counts"] == {"http_429": 60}
    assert result["at_trip"] <= 1 + BLOCK_THRESHOLD + 8
    assert result["n"] == result["at_trip"]  # nothing sent after the stop


def test_retried_429s_count(tmp_path):
    # 30 URLs x 3 attempts: every attempt is a 429, only 30 are final.
    result, marker = _fake_crawl(tmp_path, "429", 30)
    assert result["retries"] > 0
    assert result["reason"] == "site_blocked"
    assert json.loads(marker.read_text())["window_counts"] == {"http_429": 60}


def test_proxy_escalation_gets_its_chance(tmp_path):
    # A proxy is configured and the site limits direct requests only: the
    # direct 429s do not count, SmartProxyMiddleware escalates, and the crawl
    # finishes through the proxy.
    # Every URL is scheduled at once, so the direct retries queue behind them
    # and hundreds of direct 429s come before the first escalation — which
    # would have tripped the guard had they counted.
    result, marker = _fake_crawl(tmp_path, "proxy_ok", 300, proxy="http://p.example:8")
    assert result["reason"] == "finished"
    assert result["proxied"] == 300  # every page ended up going through the proxy
    assert result["n"] - result["proxied"] > 100  # direct 429s before the switch
    assert result["counted_429"] == 0
    assert not marker.exists()


def test_429s_through_the_proxy_count(tmp_path):
    # Proxy configured, but the site refuses it too: once requests go through
    # the proxy, their 429s count and the crawl stops.
    result, marker = _fake_crawl(tmp_path, "429", 300, proxy="http://p.example:8")
    assert result["reason"] == "site_blocked"
    assert result["proxied"] >= BLOCK_THRESHOLD
    assert result["n"] < 300 * 3


def test_site_blocked_errors_trip_it_through_the_real_chain(tmp_path):
    # SiteBlockedError passes RetryMiddleware untouched (never retried), and
    # requests waiting in the downloader at the stop are never sent.
    result, marker = _fake_crawl(tmp_path, "blocked", 300)
    assert result["reason"] == "site_blocked"
    assert result["retries"] == 0
    assert result["queued_at_trip"] > 0
    assert result["n"] - result["at_trip"] <= 1
    assert json.loads(marker.read_text())["window_counts"] == {"site_blocked": 60}


def test_real_crawl_forgets_blocks_100_attempts_back(tmp_path):
    # 59 blocks, 100 good pages, 59 blocks: never 60 within 100 attempts. Also
    # proves the attempt counter is wired to request_left_downloader.
    result, marker = _fake_crawl(tmp_path, "gap", 218)
    assert result["reason"] == "finished"
    assert result["n"] == 219
    assert not marker.exists()


def test_project_settings_load_it_above_the_retry_middleware():
    from scrapy.settings.default_settings import DOWNLOADER_MIDDLEWARES_BASE

    import settings

    order = settings.DOWNLOADER_MIDDLEWARES["extensions.site_block.SiteBlockGuard"]
    retry = DOWNLOADER_MIDDLEWARES_BASE[
        "scrapy.downloadermiddlewares.retry.RetryMiddleware"
    ]
    proxy = settings.DOWNLOADER_MIDDLEWARES["middlewares.SmartProxyMiddleware"]
    assert order > retry and order > proxy  # sees every attempt, retries included


def test_total_403_never_trips(tmp_path):
    result, marker = _fake_crawl(tmp_path, "403", 150)
    assert result["reason"] == "finished"
    assert result["n"] == 151  # the listing page and all 150 links
    assert not marker.exists()


def test_healthy_crawl_finishes(tmp_path):
    result, marker = _fake_crawl(tmp_path, "200", 150)
    assert result["reason"] == "finished"
    assert not marker.exists()


# --- CLI: exit 4, message, checkpoint ------------------------------------------


def _run_cli(monkeypatch, tmp_path, marker_data, returncode=0, rows=()):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(crawl_mod, "DATA_DIR", str(tmp_path / "data"))

    def fake_run(cmd, *a, **k):
        if rows:  # the crawl appends its items to the -o file, like scrapy -o
            with open(cmd[cmd.index("-o") + 1], "a") as fh:
                fh.writelines(f'{{"url": "{r}"}}\n' for r in rows)
        for arg in cmd:
            if marker_data is not None and arg.startswith("SITE_BLOCK_MARKER="):
                Path(arg.split("=", 1)[1]).write_text(json.dumps(marker_data))
        return Mock(returncode=returncode)

    monkeypatch.setattr(crawl_mod.subprocess, "run", fake_run)
    rec = Mock()
    rec.settings = []
    rec.rules = []
    with patch("core.db.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = rec
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        rc = crawl_mod._run_spider("news", "example_org", detached=True)
    return rc, tmp_path / "data" / "news" / "example_org" / "checkpoint"


def test_cli_blocked_crawl_exits_4_and_deletes_checkpoint(
    monkeypatch, tmp_path, capsys
):
    marker = {
        "window": 100,
        "window_counts": {"site_blocked": 58, "http_429": 2},
        "totals": {"site_blocked": 140, "http_429": 2},
        "items": 900,
    }
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, marker)
    out = capsys.readouterr().out
    assert rc == 4
    assert "🛑 SITE IS BLOCKING THE CRAWL — stopped to protect access" in out
    assert "60 of the last 100 downloads were blocked: 58 still challenged" in out
    assert "Checkpoint deleted" in out
    assert "--reset-deltafetch only if" in out
    assert "(successful completion)" not in out
    assert not checkpoint.exists()


def test_cli_failed_crawl_without_block_keeps_checkpoint(monkeypatch, tmp_path):
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, None, returncode=1)
    assert rc != 4
    assert checkpoint.exists()


def test_cli_clean_crawl_exits_0(monkeypatch, tmp_path, capsys):
    rc, checkpoint = _run_cli(monkeypatch, tmp_path, None)
    assert not rc
    assert "SITE IS BLOCKING" not in capsys.readouterr().out


def test_crawl_command_exits_with_the_code(monkeypatch):
    import importlib

    from click.testing import CliRunner

    crawl_mod = importlib.import_module("cli.crawl")
    monkeypatch.setattr(crawl_mod, "_run_spider", lambda *a, **k: 4)
    res = CliRunner().invoke(crawl_mod.crawl, ["example_org", "--project", "news"])
    assert res.exit_code == 4


def test_cli_blocked_crawl_uploads_the_partial_file(monkeypatch, tmp_path):
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
    marker = {"window": 100, "window_counts": {"http_429": 60}, "totals": {}}
    rc, _ = _run_cli(monkeypatch, tmp_path, marker)
    assert rc == 4
    # Uploaded like a finished crawl, before the checkpoint is deleted.
    assert uploads == [("crawls", "news", "example_org", True, {"keep_local": True})]
    assert not checkpoint.exists()


def test_cli_clean_crawl_uploads_as_before(monkeypatch, tmp_path):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    uploads = []
    monkeypatch.setattr(
        crawl_mod, "_upload_crawl_file", lambda f, p, s, **k: uploads.append(p)
    )
    rc, _ = _run_cli(monkeypatch, tmp_path, None)
    assert not rc
    assert uploads == ["news"]


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
        monkeypatch,
        tmp_path,
        {"window": 100, "window_counts": {"http_429": 60}, "totals": {}},
        rows=["a", "b"],
    )
    assert rc == 4
    rc, _ = _run_cli(monkeypatch, tmp_path, None, rows=["c"])
    assert not rc
    (content,) = store.values()
    assert [json.loads(line)["url"] for line in content.splitlines()] == ["a", "b", "c"]
    assert not list(
        (tmp_path / "data" / "news" / "example_org" / "crawls").glob("*.jsonl")
    )
