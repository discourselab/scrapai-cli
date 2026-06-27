"""Persistent browser service daemon.

Owns ONE warm browser process and a pool of "lanes" (isolated context + page
that solves Cloudflare on its own). Requests are routed to a lane by their URL
domain: the same site reuses its lane (and its solved CF session), different
sites get different lanes and run concurrently. This lets several agents inspect
different sites at once through a single browser instead of one browser each.

Run as: python -m utils.browser_service --port N [--proxy-type auto] [--pool 5]
"""

import argparse
import asyncio
import json
import os
from urllib.parse import urlparse

from utils.cf_browser import CloudflareBrowserClient
from utils.inspector import _capture_screenshot
from utils.lane_pool import LanePool
from core import proxy as proxy_mod


def _domain(url):
    return urlparse(url).netloc


def _session_file(req):
    """Resolve a request's session NAME to its storage_state file (or None)."""
    name = req.get("session")
    if not name:
        return None
    from core.sessions import session_path

    p = session_path(name)
    return str(p) if p.exists() else None


async def handle_request(pool, req, stop):
    """Route one request to a lane and return the response dict.

    Pure of socket I/O so it can be tested with a fake pool/lane.
    """
    action = req.get("action")

    if action == "ping":
        return {"ok": True, "pid": os.getpid()}

    if action == "shutdown":
        stop.set()
        return {"ok": True}

    if action == "fetch":
        lane = await pool.acquire(_domain(req["url"]), _session_file(req))
        html = await lane.fetch(req["url"])
        return {"ok": html is not None, "bytes": len(html or "")}

    if action == "screenshot":
        lane = await pool.acquire(_domain(req["url"]), _session_file(req))
        html = await lane.fetch(req["url"])
        if html:
            await _capture_screenshot(lane.page, req["path"], req.get("screens", 2))
            return {"ok": True, "bytes": len(html)}
        return {"ok": False, "error": "fetch failed"}

    if action == "inspect":
        # Like screenshot but returns the HTML so `inspect` can save page.html
        # and report the title. Screenshots only when a path is given.
        lane = await pool.acquire(_domain(req["url"]), _session_file(req))
        html = await lane.fetch(req["url"])
        if html and req.get("path"):
            await _capture_screenshot(lane.page, req["path"], req.get("screens", 2))
        return {"ok": html is not None, "html": html or ""}

    return {"ok": False, "error": "unknown action"}


async def _run(port, proxy_type, pool_size):
    parent = CloudflareBrowserClient(
        headless=False, proxy_chain=proxy_mod.chain(proxy_type)
    )
    await parent.start()

    parent_used = False

    async def _open_lane(session_file=None):
        # Reuse the browser's first tab as lane 0 so no idle tab is left over;
        # every later lane is a new tab in the same (one-window) context. A
        # sessioned lane always goes through attach_lane (its own context with
        # the saved login), never the shared parent.
        nonlocal parent_used
        if not session_file and not parent_used:
            parent_used = True
            return parent
        return await parent.attach_lane(session_file=session_file)

    async def _close_lane(lane):
        await lane.close_lane()

    pool = LanePool(_open_lane, _close_lane, max_lanes=pool_size)
    print(
        f"[browser-service] browser ready, {pool_size}-lane pool, "
        f"listening on 127.0.0.1:{port}",
        flush=True,
    )

    stop = asyncio.Event()

    async def handle(reader, writer):
        resp = {"ok": False, "error": "unknown action"}
        try:
            line = await reader.readline()
            req = json.loads(line.decode())
            resp = await handle_request(pool, req, stop)
        except Exception as e:
            resp = {"ok": False, "error": str(e)}

        try:
            writer.write((json.dumps(resp) + "\n").encode())
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    async with server:
        await stop.wait()

    await pool.close()
    await parent.close()
    print("[browser-service] stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description="scrapai persistent browser service")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--proxy-type", default="auto")
    parser.add_argument("--pool", type=int, default=5, help="Max concurrent lanes")
    args = parser.parse_args()
    asyncio.run(_run(args.port, args.proxy_type, args.pool))


if __name__ == "__main__":
    main()
