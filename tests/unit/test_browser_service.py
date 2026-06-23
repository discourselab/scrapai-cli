"""Browser-service request routing: each fetch/screenshot is routed to a lane
by its URL domain. Tested with a fake pool/lane (no real browser)."""

import asyncio

import pytest
from unittest.mock import Mock

from utils.browser_service import handle_request

pytestmark = pytest.mark.unit


class FakeLane:
    def __init__(self):
        self.page = Mock()

    async def fetch(self, url):
        return "<html>body</html>" * 1000  # > 0 bytes


class FakePool:
    def __init__(self):
        self.acquired = []

    async def acquire(self, domain):
        self.acquired.append(domain)
        return FakeLane()


async def test_ping_returns_pid():
    resp = await handle_request(FakePool(), {"action": "ping"}, asyncio.Event())
    assert resp["ok"] is True
    assert "pid" in resp


async def test_fetch_routes_by_domain():
    pool = FakePool()
    resp = await handle_request(
        pool, {"action": "fetch", "url": "https://a.com/page"}, asyncio.Event()
    )
    assert pool.acquired == ["a.com"]
    assert resp["ok"] is True
    assert resp["bytes"] > 0


async def test_screenshot_captures_on_lane_page(monkeypatch):
    captured = {}

    async def fake_capture(page, path, screens):
        captured["args"] = (path, screens)

    monkeypatch.setattr("utils.browser_service._capture_screenshot", fake_capture)
    pool = FakePool()
    resp = await handle_request(
        pool,
        {
            "action": "screenshot",
            "url": "https://b.com/x",
            "path": "/tmp/p.png",
            "screens": 3,
        },
        asyncio.Event(),
    )
    assert pool.acquired == ["b.com"]
    assert captured["args"] == ("/tmp/p.png", 3)
    assert resp["ok"] is True


async def test_shutdown_sets_stop_event():
    stop = asyncio.Event()
    resp = await handle_request(FakePool(), {"action": "shutdown"}, stop)
    assert stop.is_set()
    assert resp["ok"] is True


async def test_unknown_action():
    resp = await handle_request(FakePool(), {"action": "frobnicate"}, asyncio.Event())
    assert resp["ok"] is False


async def test_inspect_returns_html_and_screenshots(monkeypatch):
    captured = {}

    async def fake_capture(page, path, screens):
        captured["shot"] = (path, screens)

    monkeypatch.setattr("utils.browser_service._capture_screenshot", fake_capture)
    pool = FakePool()
    resp = await handle_request(
        pool,
        {
            "action": "inspect",
            "url": "https://c.com/x",
            "path": "/tmp/c.png",
            "screens": 2,
        },
        asyncio.Event(),
    )
    assert pool.acquired == ["c.com"]
    assert resp["ok"] is True
    assert "<html>" in resp["html"]
    assert captured["shot"] == ("/tmp/c.png", 2)


async def test_inspect_without_path_skips_screenshot(monkeypatch):
    calls = {"n": 0}

    async def fake_capture(*a):
        calls["n"] += 1

    monkeypatch.setattr("utils.browser_service._capture_screenshot", fake_capture)
    resp = await handle_request(
        FakePool(), {"action": "inspect", "url": "https://d.com/"}, asyncio.Event()
    )
    assert resp["ok"] is True
    assert calls["n"] == 0  # no path -> no screenshot
