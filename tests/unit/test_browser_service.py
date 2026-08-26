"""Browser-service request routing: each fetch/screenshot is routed to a lane
by its URL domain. Tested with a fake pool/lane (no real browser)."""

import asyncio

import pytest
from unittest.mock import Mock

from utils.browser_service import handle_request, _orphaned_browser_pids

pytestmark = pytest.mark.unit


def test_orphaned_browser_pids_picks_reparented_cloakbrowser_chrome():
    """A Chrome from the cloakbrowser cache whose parent died (ppid 1) is an
    orphan from a SIGKILLed/OOMed owner; anything still parented, or any other
    program, is left alone."""
    procs = [
        # orphaned cloakbrowser chrome -> sweep
        {"pid": 100, "ppid": 1, "cmdline": "/home/u/.cloakbrowser/chrome --headless"},
        # cloakbrowser chrome with a live parent (the running service) -> keep
        {"pid": 101, "ppid": 900, "cmdline": "/home/u/.cloakbrowser/chrome --tab"},
        # unrelated orphan (user's own chrome) -> keep
        {"pid": 102, "ppid": 1, "cmdline": "/Applications/Chrome.app/chrome"},
        # unreadable cmdline -> keep
        {"pid": 103, "ppid": 1, "cmdline": ""},
    ]
    assert _orphaned_browser_pids(procs, "/home/u/.cloakbrowser") == [100]


class FakeLane:
    def __init__(self):
        self.page = Mock()

    async def fetch(self, url, wait_selector=None, wait_timeout=10):
        return "<html>body</html>" * 1000  # > 0 bytes


class FakePool:
    def __init__(self):
        self.acquired = []

    async def acquire(self, domain, session_file=None):
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


class FakeLaneWithCookies(FakeLane):
    def __init__(self):
        super().__init__()
        self.context = Mock()

        async def cookies(url=None):
            self.context.cookies_url = url
            return [{"name": "cf_clearance", "value": "tok"}]

        self.context.cookies = cookies

        async def evaluate(_js):
            return "UA-1"

        self.page.evaluate = evaluate


async def test_cf_verify_returns_html_cookies_and_ua():
    class P(FakePool):
        async def acquire(self, domain, session_file=None):
            self.acquired.append(domain)
            return FakeLaneWithCookies()

    pool = P()
    resp = await handle_request(
        pool, {"action": "cf_verify", "url": "https://e.com/x"}, asyncio.Event()
    )
    assert pool.acquired == ["e.com"]
    assert resp["ok"] is True
    assert "<html>" in resp["html"]
    assert resp["cookies"] == {"cf_clearance": "tok"}
    assert resp["user_agent"] == "UA-1"


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


# ---------------------------------------------------------------------------
# cf_browser.fetch() — wait_selector on first fetch (cf_verified=False)
# ---------------------------------------------------------------------------


async def test_cf_browser_fetch_applies_wait_selector_on_first_request(monkeypatch):
    """wait_selector must be honoured on the very first URL per domain.

    Before the fix, fetch() only called wait_for_selector in the
    'subsequent requests' branch (cf_verified=True). On the first request
    (cf_verified=False) it used a hardcoded sleep(3) and returned immediately,
    so a CSR SPA's start_url came back as a half-hydrated shell.
    """
    from utils.cf_browser import CloudflareBrowserClient

    client = CloudflareBrowserClient()

    # Stub out the real browser: CF verify always succeeds immediately.
    async def fake_verify_cloudflare(url):
        client.cf_verified = True
        return True

    monkeypatch.setattr(client, "verify_cloudflare", fake_verify_cloudflare)

    # Minimal page mock: goto succeeds, content() returns rendered HTML.
    page = Mock()

    async def fake_goto(url, wait_until=None, timeout=None):
        return None

    page.goto = fake_goto

    selector_waits = []

    async def fake_wait_for_selector(selector, timeout=None):
        selector_waits.append(selector)

    page.wait_for_selector = fake_wait_for_selector

    async def fake_content():
        return "<html><div class='app'>hydrated</div></html>"

    page.content = fake_content

    client.page = page
    # Initialise the fetch lock so the lock-init branch is skipped.
    client.fetch_lock = asyncio.Lock()

    html = await client.fetch(
        "https://example.com/jobs", wait_selector=".app", wait_timeout=5
    )

    assert selector_waits == [".app"], (
        "wait_for_selector was not called on the first (cf_verified=False) fetch"
    )
    assert "hydrated" in html
