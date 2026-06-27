"""inspect routes its browser fetch through the running browser service when one
is up (sharing the warm browser), and cold-starts its own only when it isn't."""

import pytest

from utils import inspector, browser_client

pytestmark = pytest.mark.unit


async def test_fetch_browser_routes_to_service_when_running(monkeypatch):
    monkeypatch.setattr(browser_client, "is_running", lambda: True)
    captured = {}

    def fake_request(action, **kw):
        captured["action"] = action
        captured["kw"] = kw
        return {"ok": True, "html": "<html>hello</html>"}

    monkeypatch.setattr(browser_client, "request", fake_request)

    html = await inspector._fetch_browser("https://a.com/p", "auto", "/tmp/p.png", 2)

    assert html == "<html>hello</html>"
    assert captured["action"] == "inspect"
    assert captured["kw"]["url"] == "https://a.com/p"
    assert captured["kw"]["path"] == "/tmp/p.png"
    assert captured["kw"]["screens"] == 2


async def test_fetch_browser_returns_none_on_service_failure(monkeypatch):
    monkeypatch.setattr(browser_client, "is_running", lambda: True)
    monkeypatch.setattr(browser_client, "request", lambda action, **kw: {"ok": False})

    html = await inspector._fetch_browser("https://a.com/p", "auto", None, 2)
    assert html is None


async def test_fetch_browser_does_not_call_service_when_down(monkeypatch):
    monkeypatch.setattr(browser_client, "is_running", lambda: False)

    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        return None

    monkeypatch.setattr(browser_client, "request", boom)
    # Stop before a real browser launches: a fake cold-start that yields a marker.
    monkeypatch.setattr(inspector, "_fetch_browser_cold", _make_fake_cold())

    html = await inspector._fetch_browser("https://a.com/p", "auto", None, 2)
    assert called["n"] == 0  # service never consulted
    assert html == "COLD"  # fell through to cold-start path


def _make_fake_cold():
    async def _cold(url, proxy_type, screenshot_path, screenshot_screens, session=None):
        return "COLD"

    return _cold
