"""Tests for the browser-service client (state file + IPC protocol)."""

import json
import socket
import threading

import pytest

from utils import browser_client as bc

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "STATE_FILE", str(tmp_path / "state.json"))


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
