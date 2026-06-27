"""LanePool: domain-sticky pool of browser lanes with LRU eviction.

The pool logic is tested with fake lanes (no real browser) via injected
open/close callables, the same way the browser-service client is tested
without launching a browser.
"""

import pytest

from utils.lane_pool import LanePool

pytestmark = pytest.mark.unit


def _fakes():
    """Return (open_lane, close_lane, state) recording lane lifecycle."""
    state = {"opened": 0, "closed": []}

    async def open_lane(session_file=None):
        state["opened"] += 1
        return {"id": state["opened"]}

    async def close_lane(lane):
        state["closed"].append(lane["id"])

    return open_lane, close_lane, state


async def test_acquire_new_domain_opens_one_lane():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=5)
    lane = await pool.acquire("a.com")
    assert lane == {"id": 1}
    assert state["opened"] == 1


async def test_same_domain_reuses_lane():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=5)
    first = await pool.acquire("a.com")
    second = await pool.acquire("a.com")
    assert first is second
    assert state["opened"] == 1  # not opened again


async def test_different_domains_get_different_lanes():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=5)
    a = await pool.acquire("a.com")
    b = await pool.acquire("b.com")
    assert a is not b
    assert state["opened"] == 2


async def test_exceeding_cap_evicts_lru():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=2)
    await pool.acquire("a.com")  # lane 1
    await pool.acquire("b.com")  # lane 2
    await pool.acquire("c.com")  # over cap -> evict oldest (a.com = lane 1)
    assert state["closed"] == [1]
    assert set(pool.domains()) == {"b.com", "c.com"}


async def test_recent_use_protects_lane_from_eviction():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=2)
    await pool.acquire("a.com")  # lane 1
    await pool.acquire("b.com")  # lane 2
    await pool.acquire("a.com")  # touch a -> b is now LRU
    await pool.acquire("c.com")  # evict b (lane 2), not a
    assert state["closed"] == [2]
    assert set(pool.domains()) == {"a.com", "c.com"}


async def test_close_closes_all_lanes():
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=5)
    await pool.acquire("a.com")
    await pool.acquire("b.com")
    await pool.close()
    assert sorted(state["closed"]) == [1, 2]
    assert pool.domains() == []


async def test_session_change_recreates_lane():
    # A domain's lane is tied to its session_file: same session reuses, a
    # different session (or none) tears it down and reopens.
    open_lane, close_lane, state = _fakes()
    pool = LanePool(open_lane, close_lane, max_lanes=5)

    a = await pool.acquire("a.com", session_file="s1.json")
    b = await pool.acquire("a.com", session_file="s1.json")  # same -> reuse
    assert a is b
    assert state["opened"] == 1

    await pool.acquire("a.com", session_file="s2.json")  # changed -> recreate
    assert state["opened"] == 2
    assert state["closed"] == [1]

    await pool.acquire("a.com")  # back to no session -> recreate again
    assert state["opened"] == 3
