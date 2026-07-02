"""inspect --screenshot captures a height-capped PNG (legible, not a full-page blur)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

import utils.cf_browser as cf
from utils.inspector import _fetch_browser

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _force_cold_browser(monkeypatch):
    # These tests exercise the cold direct-browser path and monkeypatch
    # CloudflareBrowserClient. If a browser service happens to be running on the
    # dev machine, _fetch_browser would route to it instead — so pin it off.
    monkeypatch.setattr("utils.browser_client.is_running", lambda: False)


def _fake_client(html="<html>ok</html>", scroll_height=9000, viewport_h=800):
    captured = {}

    class Fake:
        def __init__(self, *args, **kwargs):
            page = MagicMock()
            page.viewport_size = {"width": 1200, "height": viewport_h}
            page.evaluate = AsyncMock(return_value=scroll_height)
            page.screenshot = AsyncMock()
            self.page = page
            captured["page"] = page

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def fetch(self, url):
            return html

    return Fake, captured


def test_capped_to_two_screens_by_default(monkeypatch, tmp_path):
    Fake, captured = _fake_client(scroll_height=9000, viewport_h=800)
    monkeypatch.setattr(cf, "CloudflareBrowserClient", Fake)
    path = str(tmp_path / "page.png")

    asyncio.run(_fetch_browser("http://x.com", "none", path))  # default 2 screens

    _, kwargs = captured["page"].screenshot.call_args
    assert kwargs["path"] == path
    assert kwargs["clip"]["height"] == 1600  # min(800*2, 9000)
    assert kwargs["clip"]["width"] == 1200
    assert "full_page" not in kwargs


def test_short_page_not_padded_past_content(monkeypatch, tmp_path):
    # A 500px page should clip to 500, not 1600.
    Fake, captured = _fake_client(scroll_height=500, viewport_h=800)
    monkeypatch.setattr(cf, "CloudflareBrowserClient", Fake)

    asyncio.run(_fetch_browser("http://x.com", "none", str(tmp_path / "p.png")))

    _, kwargs = captured["page"].screenshot.call_args
    assert kwargs["clip"]["height"] == 500


def test_screens_zero_is_full_page(monkeypatch, tmp_path):
    Fake, captured = _fake_client()
    monkeypatch.setattr(cf, "CloudflareBrowserClient", Fake)

    asyncio.run(_fetch_browser("http://x.com", "none", str(tmp_path / "p.png"), 0))

    _, kwargs = captured["page"].screenshot.call_args
    assert kwargs.get("full_page") is True


def test_no_screenshot_when_path_none(monkeypatch):
    Fake, captured = _fake_client()
    monkeypatch.setattr(cf, "CloudflareBrowserClient", Fake)

    asyncio.run(_fetch_browser("http://x.com", "none", None))

    captured["page"].screenshot.assert_not_awaited()
