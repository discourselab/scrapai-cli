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
import subprocess
import sys
import time


def _default_state_file():
    """A stable, per-user location for the service state.

    Must be the same path for every scrapai process (the `browser start` and all
    `inspect` callers) so they can find one running service. ``tempfile.gettempdir()``
    is unsuitable: it follows $TMPDIR, which differs per shell/sandbox on macOS,
    so a service started in one terminal is invisible from another. Anchor on the
    user's home instead.
    """
    return os.path.join(os.path.expanduser("~"), ".scrapai", "browser_service.json")


STATE_FILE = _default_state_file()


def read_state():
    """Return {'pid', 'port'} for the running service, or None."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return None


def write_state(pid, port, proxy_type=None, pool=None):
    """Record the daemon's pid/port, plus how it was started (proxy/pool) so a
    respawn or `browser restart` brings it back with the SAME settings."""
    state = {"pid": pid, "port": port}
    if proxy_type is not None:
        state["proxy_type"] = proxy_type
    if pool is not None:
        state["pool"] = pool
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


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


def _pid_alive(pid):
    """True if a process with this pid exists (signal 0 probes without killing).

    EPERM means the process exists but isn't ours — still alive. A recycled
    pid belonging to some other program is indistinguishable here; acceptable,
    because this only gates the rare ping-timed-out path and a false "alive"
    just delays the respawn until the next attempt.
    """
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _up_or_busy():
    """The service counts as up if it answers pings, OR if its recorded pid is
    still alive — a service mid-Cloudflare-solve for many crawls can miss the
    ping window. Busy is not dead: spawning a second service over a live one
    orphans the first one's Chrome (nothing would ever close it)."""
    if is_running():
        return True
    state = read_state()
    return bool(state and _pid_alive(state.get("pid")))


def free_port():
    """Pick a free localhost port."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _spawn_service(proxy_type="auto", pool=5):
    """Launch the daemon process (detached) and record its state. Returns the
    Popen handle. Raises RuntimeError if a display is needed but Xvfb is absent."""
    clear_state()
    port = free_port()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [
        sys.executable,
        "-m",
        "utils.browser_service",
        "--port",
        str(port),
        "--proxy-type",
        proxy_type,
        "--pool",
        str(pool),
    ]
    from utils.display_helper import needs_xvfb, has_xvfb

    if needs_xvfb():
        if not has_xvfb():
            raise RuntimeError("browser needs a display but Xvfb is not installed")
        cmd = ["xvfb-run", "-a"] + cmd

    proc = subprocess.Popen(
        cmd,
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    write_state(proc.pid, port, proxy_type=proxy_type, pool=pool)
    return proc


def ensure_running(proxy_type=None, pool=None, timeout=90):
    """Make sure the service is up, starting it if a crawl finds it stopped.

    A file lock serializes startup across processes so several concurrent crawls
    can't each spawn their own daemon (which would defeat one-browser-for-all).
    ``proxy_type``/``pool`` default to whatever the dead service was started
    with (from its state file) — a `browser start --pool 40` that dies must not
    come back as pool 5. Returns True if the service is up, False if not."""
    if _up_or_busy():
        return True

    lock_path = os.path.join(os.path.dirname(STATE_FILE), "browser_service.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lockf = None
    try:
        import fcntl

        lockf = open(lock_path, "w")
        fcntl.flock(lockf, fcntl.LOCK_EX)
    except ImportError:
        lockf = None  # no flock (e.g. Windows): best-effort, no cross-proc lock

    try:
        if _up_or_busy():  # another process started it while we waited for the lock
            return True
        # Reuse the dead service's settings unless the caller overrides them.
        stale = read_state() or {}
        if proxy_type is None:
            proxy_type = stale.get("proxy_type", "auto")
        if pool is None:
            pool = stale.get("pool", 5)
        try:
            proc = _spawn_service(proxy_type, pool)
        except RuntimeError:
            return False
        for _ in range(timeout):
            if is_running():
                return True
            if proc.poll() is not None:
                clear_state()
                return False
            time.sleep(1)
        return False
    finally:
        if lockf is not None:
            lockf.close()
