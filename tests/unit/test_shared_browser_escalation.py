"""A failed verify on the shared browser fails that request only (docs/requests/30).

The browser service's lanes are tabs in one browser. Proxy escalation used to
close and relaunch the browser from inside a lane, which closed every other
tab and left the service answering "browser has been closed" to every request
until it was restarted.
"""

import asyncio
import logging

import pytest

import utils.cf_browser as cf_browser
from utils.browser_service import handle_request
from utils.cf_browser import CloudflareBrowserClient
from utils.lane_pool import LanePool

pytestmark = pytest.mark.unit

PROXY = "http://user01:secret01@proxy.example:10000"
DEAD = "https://gone.example/a"
LIVE = "https://site01.example/a"
CLOSED = "Target page, context or browser has been closed"


class FakeResponse:
    headers = {"content-type": "text/html"}

    async def text(self):
        return "<html><body>" + "content " * 200 + "</body></html>"


class FakePage:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def is_closed(self):
        return self.closed

    async def goto(self, url, **kwargs):
        if self.closed or self.context.browser.closed:
            raise RuntimeError(f"Page.goto: {CLOSED}")
        if "gone.example" in url:
            raise RuntimeError(f"Page.goto: net::ERR_NAME_NOT_RESOLVED at {url}")
        return FakeResponse()

    async def title(self):
        return "A page"

    async def content(self):
        return "<html><body>" + "content " * 200 + "</body></html>"

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, browser):
        self.browser = browser

    async def new_page(self):
        if self.browser.closed:
            raise RuntimeError(f"BrowserContext.new_page: {CLOSED}")
        return FakePage(self)

    async def cookies(self, url):
        return []


class FakeBrowser:
    def __init__(self):
        self.closed = False
        self.close_calls = 0

    async def new_context(self, **kwargs):
        return FakeContext(self)

    async def close(self):
        self.close_calls += 1
        self.closed = True


@pytest.fixture(autouse=True)
def no_waits_no_launch(monkeypatch):
    async def no_sleep(*a, **k):
        return None

    async def no_launch(**kwargs):
        raise AssertionError("a shared client must never launch a browser")

    monkeypatch.setattr(cf_browser.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(cf_browser, "launch_async", no_launch)


async def _parent(chain=(None, PROXY)):
    """The service's parent, as _run builds it, already started."""
    parent = CloudflareBrowserClient(proxy_chain=list(chain), shared=True)
    parent.browser = FakeBrowser()
    parent.context = await parent.browser.new_context()
    parent.page = await parent.context.new_page()
    return parent


async def test_failed_lane_verify_leaves_the_shared_browser_open():
    parent = await _parent()
    lane = await parent.attach_lane()

    assert lane.shared
    assert await lane.fetch(DEAD) is None
    assert lane.last_error.startswith("navigation error: ")
    assert "ERR_NAME_NOT_RESOLVED" in lane.last_error
    assert parent.browser.close_calls == 0
    assert lane.browser is parent.browser
    assert lane._chain_index == 0  # never moved down the chain

    other = await parent.attach_lane()  # the incident: this raised "closed"
    assert await other.fetch(LIVE)


async def test_failed_parent_verify_leaves_the_shared_browser_open():
    parent = await _parent()
    lane = await parent.attach_lane()

    assert await parent.fetch(DEAD) is None
    assert parent.browser.close_calls == 0
    assert await lane.fetch(LIVE)


async def test_service_keeps_serving_after_a_dead_host():
    parent = await _parent()
    used = False

    async def open_lane(session_file=None):
        nonlocal used
        if not used:
            used = True
            return parent
        return await parent.attach_lane(session_file=session_file)

    async def close_lane(lane):
        await lane.close_lane()

    pool = LanePool(open_lane, close_lane, max_lanes=3)
    stop = asyncio.Event()

    dead = await handle_request(pool, {"action": "cf_verify", "url": DEAD}, stop)
    live = await handle_request(pool, {"action": "cf_verify", "url": LIVE}, stop)
    again = await handle_request(pool, {"action": "cf_verify", "url": DEAD}, stop)

    assert dead["ok"] is False and "ERR_NAME_NOT_RESOLVED" in dead["error"]
    assert live["ok"] is True
    assert again["ok"] is False and "ERR_NAME_NOT_RESOLVED" in again["error"]
    assert parent.browser.close_calls == 0


async def test_lane_closed_mid_request_fails_without_launching():
    parent = await _parent()
    lane = await parent.attach_lane()
    await lane.close_lane()  # the pool evicted it while a request held it

    assert await lane.fetch(LIVE) is None
    assert lane.last_error == "navigation error: browser lane was closed"
    assert parent.browser.close_calls == 0


async def test_crashed_tab_is_reopened_in_the_same_context():
    parent = await _parent()
    lane = await parent.attach_lane()
    crashed = lane.page
    crashed.closed = True

    assert await lane.fetch(LIVE)
    assert lane.page is not crashed
    assert lane.context is parent.context


async def test_unshared_client_still_escalates(monkeypatch):
    client = CloudflareBrowserClient(proxy_chain=[None, PROXY])
    client.browser = FakeBrowser()
    client.context = await client.browser.new_context()
    client.page = await client.context.new_page()
    starts = []

    async def fake_start():
        starts.append(client.proxy_url)
        client.browser = FakeBrowser()
        client.context = await client.browser.new_context()
        client.page = await client.context.new_page()

    monkeypatch.setattr(client, "start", fake_start)

    assert await client.fetch(DEAD) is None
    assert starts == [PROXY]  # escalated once, then the chain ran out


async def test_shutdown_still_closes_the_shared_browser():
    parent = await _parent()
    browser = parent.browser
    await parent.close()
    assert browser.close_calls == 1


async def test_proxy_credentials_never_reach_the_log(monkeypatch, caplog):
    client = CloudflareBrowserClient(proxy_chain=[None, PROXY])
    client.browser = FakeBrowser()
    client.context = await client.browser.new_context()
    client.page = await client.context.new_page()

    async def fake_launch(**kwargs):
        return FakeBrowser()

    monkeypatch.setattr(cf_browser, "launch_async", fake_launch)
    with caplog.at_level(logging.INFO, logger="utils.cf_browser"):
        await client.fetch(DEAD)

    assert "proxy.example:10000" in caplog.text  # the proxy is still named
    assert "secret01" not in caplog.text and "user01" not in caplog.text
