"""Persistent browser service daemon.

Owns ONE warm CloakBrowser for its lifetime and answers requests over a local
socket. This avoids the open-browser / pass-Cloudflare / close cycle on every
page — the browser opens once, solves Cloudflare once, and is reused.

Step 1 is serialized (one page at a time) via an op-lock; parallel tabs come
later. Run as: python -m utils.browser_service --port N [--proxy-type auto]
"""

import argparse
import asyncio
import json
import os

from utils.cf_browser import CloudflareBrowserClient
from utils.inspector import _capture_screenshot
from core import proxy as proxy_mod


async def _run(port, proxy_type):
    client = CloudflareBrowserClient(
        headless=False, proxy_chain=proxy_mod.chain(proxy_type)
    )
    await client.start()
    print(f"[browser-service] browser ready, listening on 127.0.0.1:{port}", flush=True)

    stop = asyncio.Event()
    op_lock = asyncio.Lock()  # serialize browser ops (Step 1: one page at a time)

    async def handle(reader, writer):
        resp = {"ok": False, "error": "unknown action"}
        try:
            line = await reader.readline()
            req = json.loads(line.decode())
            action = req.get("action")

            if action == "ping":
                resp = {"ok": True, "pid": os.getpid()}
            elif action == "shutdown":
                resp = {"ok": True}
                stop.set()
            elif action == "fetch":
                async with op_lock:
                    html = await client.fetch(req["url"])
                resp = {"ok": html is not None, "bytes": len(html or "")}
            elif action == "screenshot":
                async with op_lock:
                    html = await client.fetch(req["url"])
                    if html:
                        await _capture_screenshot(
                            client.page, req["path"], req.get("screens", 2)
                        )
                resp = (
                    {"ok": True, "bytes": len(html)}
                    if html
                    else {"ok": False, "error": "fetch failed"}
                )
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

    await client.close()
    print("[browser-service] stopped", flush=True)


def main():
    parser = argparse.ArgumentParser(description="scrapai persistent browser service")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--proxy-type", default="auto")
    args = parser.parse_args()
    asyncio.run(_run(args.port, args.proxy_type))


if __name__ == "__main__":
    main()
