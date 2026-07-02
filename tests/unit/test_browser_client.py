"""Tests for the browser-service client (state file + IPC protocol)."""

import json
import os
import socket
import threading

import pytest

from utils import browser_client as bc

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "STATE_FILE", str(tmp_path / "state.json"))


def test_state_file_is_home_based_not_tmpdir(monkeypatch):
    # The state file must be discoverable across terminals/processes, so it
    # cannot depend on $TMPDIR (which differs per shell/sandbox on macOS).
    monkeypatch.setenv("TMPDIR", "/weird/sandbox/tmp")
    path = bc._default_state_file()
    assert path == os.path.join(
        os.path.expanduser("~"), ".scrapai", "browser_service.json"
    )
    assert "/weird/sandbox/tmp" not in path


def test_write_state_creates_parent_dir(tmp_path, monkeypatch):
    nested = tmp_path / "deep" / "dir" / "state.json"
    monkeypatch.setattr(bc, "STATE_FILE", str(nested))
    bc.write_state(7, 8)
    assert nested.exists()
    assert bc.read_state() == {"pid": 7, "port": 8}


def test_state_roundtrip():
    assert bc.read_state() is None
    bc.write_state(123, 4567)
    assert bc.read_state() == {"pid": 123, "port": 4567}
    bc.clear_state()
    assert bc.read_state() is None


def test_is_running_false_without_state():
    assert bc.is_running() is False


def test_request_none_without_state():
    assert bc.request("ping") is None


def _fake_server(response):
    """One-shot server that returns a canned JSON response. Returns its port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        conn.recv(4096)
        conn.sendall((json.dumps(response) + "\n").encode())
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return port


def test_request_roundtrip():
    port = _fake_server({"ok": True, "pid": 99})
    bc.write_state(1, port)
    assert bc.request("ping", timeout=5) == {"ok": True, "pid": 99}


def test_is_running_true_when_ping_ok():
    port = _fake_server({"ok": True})
    bc.write_state(1, port)
    assert bc.is_running() is True


def test_is_running_false_when_unreachable():
    # State points at a dead port → graceful False, not a crash.
    bc.write_state(1, bc.free_port())
    assert bc.is_running() is False


def test_ensure_running_short_circuits_when_already_up(monkeypatch):
    spawned = {"n": 0}
    monkeypatch.setattr(bc, "is_running", lambda: True)
    monkeypatch.setattr(bc, "_spawn_service", lambda *a, **k: spawned.update(n=1))
    assert bc.ensure_running() is True
    assert spawned["n"] == 0  # never spawned — already up


def test_ensure_running_spawns_when_down(monkeypatch, _tmp_state):
    # down, then up after spawn (second is_running check); no state file
    # means there is no live pid to guard.
    states = iter([False, False, True])
    monkeypatch.setattr(bc, "is_running", lambda: next(states))
    spawned = {"n": 0}

    class FakeProc:
        def poll(self):
            return None

    def fake_spawn(*a, **k):
        spawned["n"] += 1
        return FakeProc()

    monkeypatch.setattr(bc, "_spawn_service", fake_spawn)
    assert bc.ensure_running(timeout=5) is True
    assert spawned["n"] == 1


def test_pid_alive_true_for_self_false_for_dead():
    assert bc._pid_alive(os.getpid()) is True
    # A freshly-exited child pid is reliably dead.
    import subprocess

    proc = subprocess.Popen(["true"])
    proc.wait()
    assert bc._pid_alive(proc.pid) is False
    assert bc._pid_alive(None) is False


def test_ensure_running_treats_live_pid_as_busy_never_spawns(monkeypatch, _tmp_state):
    """A service mid-CF-solve misses the 5s ping window. Its pid is alive, so
    it's busy, not dead — spawning over it would orphan its Chrome."""
    bc.write_state(os.getpid(), 12345)  # our own pid: definitely alive
    monkeypatch.setattr(bc, "is_running", lambda: False)  # ping timed out
    spawned = {"n": 0}
    monkeypatch.setattr(
        bc, "_spawn_service", lambda *a, **k: spawned.update(n=spawned["n"] + 1)
    )
    assert bc.ensure_running(timeout=5) is True
    assert spawned["n"] == 0


def test_ensure_running_spawns_when_state_pid_is_dead(monkeypatch, _tmp_state):
    """State file left behind by a SIGKILLed service: pid gone -> spawn."""
    import subprocess

    proc = subprocess.Popen(["true"])
    proc.wait()
    bc.write_state(proc.pid, 12345)  # dead pid
    states = iter([False, False, True])
    monkeypatch.setattr(bc, "is_running", lambda: next(states))
    spawned = {"n": 0}

    class FakeProc:
        def poll(self):
            return None

    def fake_spawn(*a, **k):
        spawned["n"] += 1
        return FakeProc()

    monkeypatch.setattr(bc, "_spawn_service", fake_spawn)
    assert bc.ensure_running(timeout=5) is True
    assert spawned["n"] == 1


def test_write_state_persists_service_settings():
    bc.write_state(1, 2, proxy_type="residential", pool=40)
    state = bc.read_state()
    assert state["proxy_type"] == "residential"
    assert state["pool"] == 40


def test_ensure_running_respawn_reuses_remembered_settings(monkeypatch, _tmp_state):
    """A service started with --pool 40 that dies must come back with pool 40,
    not the default 5 (which thrashes under 40 concurrent crawls)."""
    import subprocess

    proc = subprocess.Popen(["true"])
    proc.wait()
    bc.write_state(proc.pid, 12345, proxy_type="residential", pool=40)  # dead
    states = iter([False, False, True])
    monkeypatch.setattr(bc, "is_running", lambda: next(states))
    captured = {}

    class FakeProc:
        def poll(self):
            return None

    def fake_spawn(proxy_type, pool):
        captured["proxy_type"] = proxy_type
        captured["pool"] = pool
        return FakeProc()

    monkeypatch.setattr(bc, "_spawn_service", fake_spawn)
    assert bc.ensure_running(timeout=5) is True
    assert captured == {"proxy_type": "residential", "pool": 40}
