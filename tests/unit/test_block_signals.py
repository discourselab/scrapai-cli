"""Tests for the shared anti-bot block detector used by inspect escalation."""

import pytest

from core.block_signals import is_blocked

pytestmark = pytest.mark.unit

GOOD = "<html><body>" + ("x" * 6000) + "</body></html>"


class TestIsBlocked:
    def test_ok_page_not_blocked(self):
        assert is_blocked(200, GOOD) is False

    def test_403_blocked(self):
        assert is_blocked(403, GOOD) is True

    def test_429_blocked(self):
        assert is_blocked(429, "") is True

    def test_503_blocked(self):
        assert is_blocked(503, GOOD) is True

    def test_empty_body_on_200_blocked(self):
        assert is_blocked(200, "") is True
        assert is_blocked(200, "   ") is True

    def test_cloudflare_challenge_marker_blocked(self):
        assert is_blocked(200, "<html>Just a moment...</html>") is True

    def test_short_cloudflare_body_blocked(self):
        assert is_blocked(200, "<html>cloudflare ray id</html>") is True

    def test_genuine_404_not_blocked(self):
        # A real not-found won't be helped by a stronger transport.
        assert is_blocked(404, "<html>Not Found</html>") is False

    def test_normal_long_page_not_blocked(self):
        assert is_blocked(200, GOOD) is False

    def test_none_status_empty_blocked(self):
        assert is_blocked(None, None) is True
