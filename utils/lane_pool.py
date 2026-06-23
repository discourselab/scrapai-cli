"""Domain-sticky pool of browser lanes over one shared browser.

A "lane" is an isolated browser context + page that solves Cloudflare on its
own. The pool keeps at most ``max_lanes`` of them and maps each domain to a
lane: the same domain reuses its lane (and its already-solved CF session),
different domains get different lanes (and can run in parallel), and when the
number of domains exceeds the cap the least-recently-used lane is closed.

Lane creation/teardown is injected (``open_lane`` / ``close_lane``) so the pool
logic can be tested without launching a browser.
"""

import asyncio


class LanePool:
    def __init__(self, open_lane, close_lane, max_lanes=5):
        """
        Args:
            open_lane: async callable () -> lane, creates a fresh lane.
            close_lane: async callable (lane) -> None, tears a lane down.
            max_lanes: maximum number of concurrent lanes.
        """
        self._open_lane = open_lane
        self._close_lane = close_lane
        self.max_lanes = max_lanes
        self._lanes = {}  # domain -> lane
        self._lru = []  # domains, least-recently-used first
        self._guard = asyncio.Lock()

    async def acquire(self, domain):
        """Return the lane for ``domain``, creating or evicting as needed."""
        async with self._guard:
            if domain in self._lanes:
                self._lru.remove(domain)
                self._lru.append(domain)
                return self._lanes[domain]

            if len(self._lanes) >= self.max_lanes:
                victim = self._lru.pop(0)
                await self._close_lane(self._lanes.pop(victim))

            lane = await self._open_lane()
            self._lanes[domain] = lane
            self._lru.append(domain)
            return lane

    async def close(self):
        """Close every lane and empty the pool."""
        async with self._guard:
            for lane in list(self._lanes.values()):
                await self._close_lane(lane)
            self._lanes.clear()
            self._lru.clear()

    def domains(self):
        """Domains with a live lane, least-recently-used first."""
        return list(self._lru)
