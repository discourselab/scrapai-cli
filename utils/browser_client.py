"""Client for the persistent browser service.

A small JSON-over-localhost-socket protocol. The running daemon (utils.browser_
service) owns one warm CloakBrowser; callers (inspect, the `browser` CLI) send it
requests instead of spawning their own browser. State (pid + port) lives in a
temp file so any process can find the daemon. If the daemon isn't running or is
stale, helpers fail gracefully so callers can fall back to spawning their own.
"""

import json
import os
import socket
import tempfile

STATE_FILE = os.path.join(tempfile.gettempdir(), "scrapai_browser.json")


def read_state():
    """Return {'pid', 'port'} for the running service, or None."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def write_state(pid, port):
    with open(STATE_FILE, "w") as f:
        json.dump({"pid": pid, "port": port}, f)


def clear_state():
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass


def request(action, timeout=180, **kwargs):
    """Send a request to the service; return the parsed response dict, or None.

    Returns None if no service is reachable (no state file, or connection fails).
    """
    state = read_state()
    if not state:
        return None
    payload = (json.dumps({"action": action, **kwargs}) + "\n").encode()
    try:
        with socket.create_connection(("127.0.0.1", state["port"]), timeout=10) as sock:
            sock.settimeout(timeout)
            sock.sendall(payload)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
    except OSError:
        return None
    return json.loads(buf.decode()) if buf.strip() else None


def is_running():
    """True if a service is up and answering pings (handles stale state files)."""
    if not read_state():
        return False
    resp = request("ping", timeout=5)
    return bool(resp and resp.get("ok"))


def free_port():
    """Pick a free localhost port."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
