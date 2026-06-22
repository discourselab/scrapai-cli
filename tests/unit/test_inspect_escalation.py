"""inspect escalates plain HTTP -> curl_cffi, and signals when a browser is needed."""

import pytest

from utils import inspector

pytestmark = pytest.mark.unit

GOOD = "<html><head><title>T</title></head><body>" + ("x" * 6000) + "</body></html>"


def _patch(monkeypatch, http_result, curl_result):
    calls = {"curl": 0}

    async def fake_http(url):
        return http_result

    def fake_curl(url):
        calls["curl"] += 1
        return curl_result

    monkeypatch.setattr(inspector, "_fetch_http", fake_http)
    monkeypatch.setattr(inspector, "_fetch_curl_cffi", fake_curl)
    return calls


def test_http_ok_uses_http_and_skips_curl(monkeypatch, tmp_path):
    calls = _patch(monkeypatch, (200, GOOD), (200, GOOD))
    result = inspector.inspect_page(
        "https://x.com", output_dir=str(tmp_path), mode="http"
    )
    assert result == {"transport": "http", "needs_browser": False}
    assert calls["curl"] == 0  # curl_cffi never tried when HTTP works
    assert (tmp_path / "page.html").exists()


def test_http_blocked_falls_back_to_curl(monkeypatch, tmp_path):
    calls = _patch(monkeypatch, (403, ""), (200, GOOD))
    result = inspector.inspect_page(
        "https://x.com", output_dir=str(tmp_path), mode="http"
    )
    assert result == {"transport": "curl_cffi", "needs_browser": False}
    assert calls["curl"] == 1
    assert (tmp_path / "page.html").exists()


def test_both_blocked_signals_browser(monkeypatch, tmp_path):
    _patch(monkeypatch, (403, ""), (403, ""))
    result = inspector.inspect_page(
        "https://x.com", output_dir=str(tmp_path), mode="http"
    )
    assert result == {"transport": None, "needs_browser": True}
    assert not (tmp_path / "page.html").exists()  # nothing saved when all blocked
