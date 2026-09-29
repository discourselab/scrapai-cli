"""A failed cf_verify says why (docs/requests/17).

The browser service used to answer every failed verify with "verify failed",
which lumped a wedged browser together with a site the browser could not get
past. The lane now records the reason, the service returns it, and the
Cloudflare handler words a site-side reason so it is never read as a service
fault.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from handlers.cloudflare_handler import _site_refused
from utils.browser_service import handle_request
from utils.cf_browser import CloudflareBrowserClient

pytestmark = pytest.mark.unit

URL = "https://site01.example/a"


class FailingLane:
    def __init__(self, last_error=None):
        if last_error is not None:
            self.last_error = last_error

    async def fetch(self, url, **kwargs):
        return None


class Pool:
    def __init__(self, lane):
        self.lane = lane

    async def acquire(self, domain, session_file=None):
        return self.lane


async def _verify(lane):
    req = {"action": "cf_verify", "url": URL}
    return await handle_request(Pool(lane), req, asyncio.Event())


async def test_service_returns_the_lane_reason():
    resp = await _verify(FailingLane("challenge not passed after 120s"))
    assert resp == {"ok": False, "error": "challenge not passed after 120s"}


async def test_service_falls_back_to_verify_failed():
    assert (await _verify(FailingLane()))["error"] == "verify failed"


async def test_navigation_exception_is_recorded_as_navigation_error():
    lane = CloudflareBrowserClient()
    lane.page = Mock()
    lane.page.goto = AsyncMock(side_effect=RuntimeError("net::ERR_NAME_NOT_RESOLVED"))
    assert await lane.verify_cloudflare(URL) is False
    assert lane.last_error == "navigation error: net::ERR_NAME_NOT_RESOLVED"


async def test_verified_lane_records_a_failed_navigation():
    lane = CloudflareBrowserClient()
    lane.cf_verified = True
    lane.page = Mock()
    lane.page.goto = AsyncMock(side_effect=RuntimeError("Timeout 60000ms exceeded."))
    assert await lane.fetch(URL) is None
    assert lane.last_error == "navigation error: Timeout 60000ms exceeded."


@pytest.mark.parametrize(
    "reason, site",
    [
        ("challenge not passed after 120s", True),
        ("challenge not passed (access denied)", True),
        ("navigation error: net::ERR_CONNECTION_REFUSED at https://x", True),
        ("navigation error: net::ERR_CERT_DATE_INVALID at https://x", True),
        ("navigation error: net::ERR_NAME_RESOLUTION_FAILED at https://x", True),
        ("navigation error: browser lane was closed", False),
        ("navigation error: Timeout 60000ms exceeded.", False),
        ("navigation error: Target page, context or browser has been closed", False),
        ("verify failed", False),
    ],
)
def test_site_refused(reason, site):
    assert _site_refused(reason) is site


async def _no_sleep(*a, **k):
    return None


async def test_a_page_that_never_settles_is_a_navigation_error(monkeypatch):
    # Every poll lands mid-navigation and no challenge is ever seen: that is
    # not "challenge not passed" — the site never showed one.
    import utils.cf_browser as cf_browser

    monkeypatch.setattr(cf_browser.asyncio, "sleep", _no_sleep)
    lane = CloudflareBrowserClient()
    lane.page = Mock()
    lane.page.goto = AsyncMock()
    lane.page.title = AsyncMock(
        side_effect=RuntimeError("Execution context was destroyed by a navigation")
    )
    assert await lane.verify_cloudflare(URL) is False
    assert lane.last_error.startswith("navigation error: page still navigating")
    assert not _site_refused(lane.last_error)


async def test_a_seen_challenge_that_never_clears_is_not_passed(monkeypatch):
    import utils.cf_browser as cf_browser

    monkeypatch.setattr(cf_browser.asyncio, "sleep", _no_sleep)
    lane = CloudflareBrowserClient()
    lane.page = Mock()
    lane.page.goto = AsyncMock()
    lane.page.title = AsyncMock(return_value="Just a moment...")
    lane.page.content = AsyncMock(return_value="<html></html>")
    lane._click_turnstile = AsyncMock(return_value=False)
    assert await lane.verify_cloudflare(URL) is False
    assert lane.last_error == "challenge not passed after 120s"


async def test_a_stale_reason_never_labels_a_later_fetch(monkeypatch):
    # A reason from an earlier failure is cleared when the next fetch starts,
    # so a later empty render is reported as "verify failed", not as the site.
    import utils.cf_browser as cf_browser

    monkeypatch.setattr(cf_browser.asyncio, "sleep", _no_sleep)
    lane = CloudflareBrowserClient()
    lane.cf_verified = True
    lane.last_error = "challenge not passed after 120s"
    lane.page = Mock()
    lane.page.goto = AsyncMock(return_value=None)
    lane._body_or_dom = AsyncMock(return_value="")
    assert await lane.fetch(URL) == ""
    assert lane.last_error is None

    class Pool:
        async def acquire(self, domain, session_file=None):
            return lane

    resp = await handle_request(
        Pool(), {"action": "cf_verify", "url": URL}, asyncio.Event()
    )
    assert resp["error"] == "verify failed"
