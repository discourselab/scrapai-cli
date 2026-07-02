"""Reactive, host-keyed Cloudflare verification.

A central browser verifies CF once per host -> cookie cached -> fast concurrent
HTTP. No time-based reverify. The browser is touched only when (a) a host has no
cookie yet, or (b) an HTTP response comes back blocked: then all requests hold at
one gate, ONE reverifies, everyone retries with the fresh cookie.
"""

import asyncio
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest

from handlers.cloudflare_handler import CloudflareDownloadHandler

pytestmark = pytest.mark.unit


def test_cache_key_is_per_spider_and_host():
    k = CloudflareDownloadHandler._cache_key
    assert k("larazon", "https://www.larazon.bo/a") == "larazon|www.larazon.bo"
    assert (
        k("larazon", "https://hemeroteca.larazon.bo/x")
        == "larazon|hemeroteca.larazon.bo"
    )
    # same host, different path -> same key
    assert k("larazon", "https://www.larazon.bo/b") == k(
        "larazon", "https://www.larazon.bo/c"
    )
    # different spider -> different key
    assert k("other", "https://www.larazon.bo/a") != k(
        "larazon", "https://www.larazon.bo/a"
    )


@pytest.fixture(autouse=True)
def _service_down(monkeypatch):
    # Default: no warm browser service, and don't try to start one -> _reverify
    # uses the local browser path (which the gate tests mock). The service-routing
    # tests override these.
    monkeypatch.setattr("utils.browser_client.request", lambda *a, **k: None)
    monkeypatch.setattr("utils.browser_client.ensure_running", lambda *a, **k: False)


def _make_handler():
    h = CloudflareDownloadHandler({})
    CloudflareDownloadHandler._cookie_cache = {}
    CloudflareDownloadHandler._refresh_lock = None
    return h


def _spider():
    s = AsyncMock()
    s.name = "larazon"
    s.custom_settings = {}
    return s


async def _drive(handler, urls):
    """Fire requests concurrently through the hybrid fetch path."""
    from scrapy.http import Request

    return await asyncio.gather(
        *[handler._hybrid_fetch_async(Request(u), _spider()) for u in urls]
    )


def _patch_io(handler, verified_hosts):
    """Fake the browser service + HTTP. HTTP returns a CF block page for a host
    until that host has been verified via the service; then good HTML. Returns
    the service AsyncMock so tests can count verifications. (Verification only
    ever goes through the service now — there is no per-crawl local browser.)"""

    async def fake_http(url, cached):
        host = urlparse(url).hostname
        if host in verified_hosts:
            return f"<html>content for {url}</html>"
        return "<title>Just a moment...</title>"  # _is_blocked() matches this

    async def fake_service(url, spider):
        verified_hosts.add(urlparse(url).hostname)
        await asyncio.sleep(0.01)  # simulate browser work so requests overlap
        return "<html>verified</html>", {"cf_clearance": "x"}, "UA"

    service = AsyncMock(side_effect=fake_service)
    handler._fetch_with_http = AsyncMock(side_effect=fake_http)
    handler._verify_via_service = service
    return service


def _ok(r):
    # got valid content, not a CF block page (the verifying request gets the
    # browser's HTML; the rest get HTTP content — both are fine, neither blocked)
    return bool(r) and "just a moment" not in r.lower()


async def test_concurrent_first_hit_verifies_once():
    h = _make_handler()
    browser = _patch_io(h, verified_hosts=set())
    urls = [f"https://www.larazon.bo/{i}" for i in range(16)]
    results = await _drive(h, urls)
    # 16 concurrent requests to a fresh host -> exactly ONE browser verify
    assert browser.call_count == 1
    assert all(_ok(r) for r in results)


async def test_concurrent_blocked_reverifies_once_and_retries():
    h = _make_handler()
    verified = set()
    browser = _patch_io(h, verified)
    # warm the host (1 verify)
    await _drive(h, ["https://www.larazon.bo/seed"])
    assert browser.call_count == 1
    # cookie "dies": HTTP starts returning blocked again until a reverify
    verified.discard("www.larazon.bo")
    results = await _drive(h, [f"https://www.larazon.bo/{i}" for i in range(16)])
    # 16 concurrent blocked -> ONE reverify (total 2 browser calls), all recover
    assert browser.call_count == 2
    assert all(_ok(r) for r in results)


async def test_two_hosts_verify_independently():
    h = _make_handler()
    browser = _patch_io(h, verified_hosts=set())
    urls = [f"https://www.larazon.bo/{i}" for i in range(8)]
    urls += [f"https://hemeroteca.larazon.bo/{i}" for i in range(8)]
    results = await _drive(h, urls)
    # one verify per host, not per request
    assert browser.call_count == 2
    assert all(_ok(r) for r in results)


async def test_verified_host_skips_browser():
    h = _make_handler()
    verified = set()
    browser = _patch_io(h, verified)
    await _drive(h, ["https://www.larazon.bo/seed"])  # 1 verify
    await _drive(h, [f"https://www.larazon.bo/{i}" for i in range(16)])
    # cookie still good -> no further browser calls for 16 more requests
    assert browser.call_count == 1


# Host-scoped cookie extraction now lives in the browser service
# (_lane_cookies in utils/browser_service.py) — covered by its own tests.


async def test_reverify_uses_browser_service_when_available(monkeypatch):
    """The central browser: a verify goes through the warm service (one browser
    for all crawls) and its html+cookies+ua are cached — no local browser."""
    h = _make_handler()

    def fake_request(action, **kw):
        assert action == "cf_verify"
        assert kw["url"] == "https://www.larazon.bo/x"
        return {
            "ok": True,
            "html": "<html>svc</html>",
            "cookies": {"cf_clearance": "S"},
            "user_agent": "UA-S",
        }

    monkeypatch.setattr("utils.browser_client.request", fake_request)
    # if the local browser were used these would blow up (no real browser)
    await h._reverify(
        "larazon|www.larazon.bo", "https://www.larazon.bo/x", _spider(), used_seq=None
    )
    cached = CloudflareDownloadHandler._cookie_cache["larazon|www.larazon.bo"]
    assert cached["cookies"] == {"cf_clearance": "S"}
    assert cached["user_agent"] == "UA-S"


async def test_reverify_restarts_service_when_stopped(monkeypatch):
    """If the service was stopped, a crawl that needs it restarts it and retries
    through the service — not a per-crawl local browser."""
    h = _make_handler()
    calls = {"n": 0}

    def fake_request(action, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # service down on first try
        return {
            "ok": True,
            "html": "<html>svc</html>",
            "cookies": {"cf_clearance": "S"},
            "user_agent": "UA-S",
        }

    monkeypatch.setattr("utils.browser_client.request", fake_request)
    monkeypatch.setattr("utils.browser_client.ensure_running", lambda *a, **k: True)
    # local browser would blow up if used -> proves we went through the service
    await h._reverify(
        "larazon|www.larazon.bo", "https://www.larazon.bo/x", _spider(), used_seq=None
    )
    cached = CloudflareDownloadHandler._cookie_cache["larazon|www.larazon.bo"]
    assert cached["cookies"] == {"cf_clearance": "S"}
    assert calls["n"] == 2  # tried, restarted, retried


async def test_reverify_raises_when_service_unreachable(monkeypatch):
    """No per-crawl local browser, ever: if the service can't be reached or
    restarted, the request fails (Scrapy retries it later) instead of every
    crawl spawning its own Chrome — which is how 40 crawls under load used to
    turn into 40 orphaned browsers."""
    h = _make_handler()
    # autouse _service_down fixture: request -> None, ensure_running -> False
    h._ensure_browser_started = AsyncMock()  # must never be awaited
    with pytest.raises(Exception, match="browser service"):
        await h._reverify(
            "larazon|www.larazon.bo",
            "https://www.larazon.bo/x",
            _spider(),
            used_seq=None,
        )
    h._ensure_browser_started.assert_not_awaited()
    assert "larazon|www.larazon.bo" not in CloudflareDownloadHandler._cookie_cache
