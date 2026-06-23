"""CloudflareBrowserClient lane helpers.

A lane shares the browser process AND the browser context (so all lanes live in
one window), but drives its own tab/page. Lanes still solve Cloudflare on their
own page; cookies live in the shared context (kept apart per-domain)."""

import pytest
from unittest.mock import AsyncMock, Mock

from utils.cf_browser import CloudflareBrowserClient

pytestmark = pytest.mark.unit


async def test_attach_lane_shares_context_owns_tab():
    parent = CloudflareBrowserClient(headless=True)
    parent.browser = Mock()
    shared_ctx = Mock()
    new_tab = Mock()
    parent.context = shared_ctx
    shared_ctx.new_page = AsyncMock(return_value=new_tab)

    lane = await parent.attach_lane()

    assert lane is not parent
    assert lane.browser is parent.browser  # shared browser process
    assert lane.context is shared_ctx  # SHARED context => one window
    assert lane.page is new_tab  # own tab in that window
    assert lane.cf_verified is False  # fresh CF state, solves on its own
    parent.browser.new_context.assert_not_called()  # no extra window


async def test_attach_lane_inherits_proxy_chain():
    parent = CloudflareBrowserClient(proxy_chain=["http://proxy:1"])
    parent.browser = Mock()
    parent.context = Mock(new_page=AsyncMock())

    lane = await parent.attach_lane()
    assert lane._proxy_chain == ["http://proxy:1"]


async def test_close_lane_closes_tab_not_context_or_browser():
    client = CloudflareBrowserClient()
    page = Mock(close=AsyncMock())
    client.page = page
    client.context = Mock(close=AsyncMock())
    client.browser = Mock(close=AsyncMock())

    await client.close_lane()

    page.close.assert_awaited_once()
    client.context.close.assert_not_called()  # shared session, keep it
    client.browser.close.assert_not_called()
    assert client.page is None  # tab released
