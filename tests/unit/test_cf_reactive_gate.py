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
    """Fake the browser + HTTP + cookie extraction. HTTP returns a CF block page
    for a host until that host has been verified by the browser; then good HTML.
    Returns the browser AsyncMock so tests can count verifications."""

    async def fake_http(url, cached):
        host = urlparse(url).hostname
        if host in verified_hosts:
            return f"<html>content for {url}</html>"
        return "<title>Just a moment...</title>"  # _is_blocked() matches this

    async def fake_browser(url, spider):
        verified_hosts.add(urlparse(url).hostname)
        await asyncio.sleep(0.01)  # simulate browser work so requests overlap
        return "<html>verified</html>"

    browser = AsyncMock(side_effect=fake_browser)
    handler._fetch_with_http = AsyncMock(side_effect=fake_http)
    handler._fetch_with_browser = browser
    handler._ensure_browser_started = AsyncMock()
    handler._extract_cookies_from_browser = AsyncMock(
        return_value=({"cf_clearance": "x"}, "UA")
    )
    return browser


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


async def test_extract_cookies_scoped_to_verify_host():
    """Extraction must pull only the verified host's cookies, not the whole
    shared-context jar (cf_clearance is per-host; flattening by name across
    subdomains would let one host's cf_clearance overwrite another's)."""
    h = _make_handler()
    captured = {}

    class FakeCtx:
        async def cookies(self, url=None):
            captured["url"] = url
            if url and "hemeroteca" in url:
                return [{"name": "cf_clearance", "value": "HEM"}]
            return [{"name": "cf_clearance", "value": "WWW"}]

    class FakePage:
        async def evaluate(self, _js):
            return "UA"

    class FakeBrowser:
        context = FakeCtx()
        page = FakePage()

    CloudflareDownloadHandler._shared_browser = FakeBrowser()
    try:
        cookies, ua = await h._extract_cookies_from_browser(
            "https://hemeroteca.larazon.bo/x"
        )
    finally:
        CloudflareDownloadHandler._shared_browser = None

    assert captured["url"] == "https://hemeroteca.larazon.bo/x"
    assert cookies == {"cf_clearance": "HEM"}  # host-scoped, not the www value
