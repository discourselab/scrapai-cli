"""
Unit tests for Cloudflare download handler.

Tests the hybrid cookie caching strategy, block detection, and fallback logic.
Mocks browser automation to keep tests fast.
"""

import time
import pytest
from unittest.mock import Mock, AsyncMock, patch

from handlers.cloudflare_handler import CloudflareDownloadHandler
from scrapy.http import Request


class TestCloudflareHandlerInit:
    """Test handler initialization and configuration."""

    @pytest.mark.unit
    def test_handler_initializes_with_settings(self):
        """Test basic handler initialization."""
        settings = {}
        crawler = Mock()
        crawler.settings = settings

        handler = CloudflareDownloadHandler.from_crawler(crawler)

        assert handler.crawler == crawler
        assert handler.loop is None


# Cookie verification is reactive + host-keyed now (no time-based refresh);
# that behavior is covered by tests/unit/test_cf_reactive_gate.py.


class TestSessionExpiry:
    """A SESSION crawl that gets its auth-wall page = the saved login expired.
    Stop loudly on the first one instead of silently quarantining every row."""

    def _spider(self, settings):
        s = Mock()
        s.name = "ladiaria_com_uy"
        s.custom_settings = settings
        return s

    @pytest.mark.unit
    def test_detected_when_signal_present(self):
        h = CloudflareDownloadHandler({})
        spider = self._spider(
            {"SESSION": "ladiaria_com_uy", "SESSION_EXPIRED_SIGNAL": "Muro de pago"}
        )
        assert h._session_expired("<title>Muro de pago</title>", spider) is True

    @pytest.mark.unit
    def test_not_detected_when_signal_absent_from_page(self):
        h = CloudflareDownloadHandler({})
        spider = self._spider(
            {"SESSION": "ladiaria_com_uy", "SESSION_EXPIRED_SIGNAL": "Muro de pago"}
        )
        assert h._session_expired("<title>Real article</title>", spider) is False

    @pytest.mark.unit
    def test_never_fires_without_signal_configured(self):
        # No SESSION_EXPIRED_SIGNAL -> feature off, backward compatible.
        h = CloudflareDownloadHandler({})
        spider = self._spider({"SESSION": "ladiaria_com_uy"})
        assert h._session_expired("<title>Muro de pago</title>", spider) is False

    @pytest.mark.unit
    def test_guard_stops_crawl_and_raises_on_expiry(self, monkeypatch):
        from scrapy.exceptions import IgnoreRequest
        from twisted.internet import reactor

        h = CloudflareDownloadHandler({})
        spider = self._spider(
            {"SESSION": "ladiaria_com_uy", "SESSION_EXPIRED_SIGNAL": "Muro de pago"}
        )
        closed = {}
        spider.crawler.engine.close_spider = lambda sp, reason: closed.update(
            spider=sp, reason=reason
        )
        # run the scheduled reactor call inline so the test can observe it
        monkeypatch.setattr(reactor, "callFromThread", lambda fn, *a, **k: fn(*a, **k))
        with pytest.raises(IgnoreRequest):
            h._stop_if_session_expired("<title>Muro de pago</title>", spider)
        assert closed["reason"] == "session_expired"

    @pytest.mark.unit
    def test_guard_is_noop_on_healthy_page(self):
        h = CloudflareDownloadHandler({})
        spider = self._spider(
            {"SESSION": "ladiaria_com_uy", "SESSION_EXPIRED_SIGNAL": "Muro de pago"}
        )
        # no raise, no crawler interaction needed
        h._stop_if_session_expired("<title>Real article with content</title>", spider)


class TestBlockDetection:
    """Test Cloudflare block detection."""

    @pytest.mark.unit
    def test_detects_checking_browser_message(self):
        """Test detection of 'Checking your browser' message."""
        handler = CloudflareDownloadHandler({})
        # Must contain both "cloudflare" and "checking your browser"
        html = "<html><body><h1>Cloudflare: Checking your browser before accessing...</h1></body></html>"

        is_blocked = handler._is_blocked(html)

        assert is_blocked is True

    @pytest.mark.unit
    def test_detects_just_a_moment_message(self):
        """Test detection of 'Just a moment' message."""
        handler = CloudflareDownloadHandler({})
        # Must contain both "cloudflare" and "just a moment"
        html = "<html><body><div>Just a moment... Cloudflare</div></body></html>"

        is_blocked = handler._is_blocked(html)

        assert is_blocked is True

    @pytest.mark.unit
    def test_detects_javascript_disabled_robot_challenge(self):
        """CF interstitial that names neither 'cloudflare' nor 'just a moment'.

        This variant was being saved as article content (title empty, content =
        the challenge text) because no indicator matched it.
        """
        handler = CloudflareDownloadHandler({})
        html = (
            "JavaScript is disabled\nIn order to continue, we need to verify "
            "that you're not a robot. This requires JavaScript. Enable "
            "JavaScript and then reload the page."
        )

        assert handler._is_blocked(html) is True

    @pytest.mark.unit
    def test_no_block_on_normal_html(self):
        """Test that normal HTML is not flagged as blocked."""
        handler = CloudflareDownloadHandler({})
        # Long normal HTML without cloudflare indicators
        html = (
            "<html><body><h1>Welcome to our site</h1>"
            + "<p>Content here</p>" * 1000
            + "</body></html>"
        )

        is_blocked = handler._is_blocked(html)

        assert is_blocked is False

    @pytest.mark.unit
    def test_block_on_empty_html(self):
        """Test that empty HTML is flagged as blocked."""
        handler = CloudflareDownloadHandler({})
        html = ""

        is_blocked = handler._is_blocked(html)

        # Empty HTML is considered blocked (returns True)
        assert is_blocked is True


class TestStrategySelection:
    """Test strategy selection (hybrid vs browser-only)."""

    @pytest.mark.unit
    def test_default_strategy_is_hybrid(self):
        """Test that default strategy is hybrid mode."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.custom_settings = {}
        request = Mock(spec=Request)
        request.url = "https://example.com"

        # Check which method gets called
        with patch.object(
            handler, "_hybrid_fetch_sync", return_value=Mock()
        ) as mock_hybrid:
            with patch(
                "twisted.internet.threads.deferToThread",
                side_effect=lambda f, *args: f(*args),
            ):
                handler.download_request(request, spider)
                mock_hybrid.assert_called_once()

    @pytest.mark.unit
    def test_browser_only_strategy_when_configured(self):
        """Test browser-only mode when explicitly configured."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.custom_settings = {"CLOUDFLARE_STRATEGY": "browser_only"}
        request = Mock(spec=Request)
        request.url = "https://example.com"

        # Check which method gets called
        with patch.object(
            handler, "_browser_only_fetch_sync", return_value=Mock()
        ) as mock_browser:
            with patch(
                "twisted.internet.threads.deferToThread",
                side_effect=lambda f, *args: f(*args),
            ):
                handler.download_request(request, spider)
                mock_browser.assert_called_once()


class TestCookieCacheManagement:
    """Test thread-safe cookie cache operations."""

    @pytest.mark.unit
    def test_cookie_cache_stores_cookies(self):
        """Test that cookies are stored in cache."""
        CloudflareDownloadHandler._cookie_cache = {}

        spider_name = "test_spider"
        cookies = {"cf_clearance": "test_token", "session": "abc123"}
        user_agent = "Mozilla/5.0"

        CloudflareDownloadHandler._cookie_cache[spider_name] = {
            "cookies": cookies,
            "user_agent": user_agent,
            "timestamp": time.time(),
        }

        cached = CloudflareDownloadHandler._cookie_cache.get(spider_name)
        assert cached is not None
        assert cached["cookies"] == cookies
        assert cached["user_agent"] == user_agent
        assert "timestamp" in cached

    @pytest.mark.unit
    def test_multiple_spiders_have_separate_cookies(self):
        """Test that different spiders have isolated cookie caches."""
        CloudflareDownloadHandler._cookie_cache = {
            "spider1": {
                "cookies": {"cf_clearance": "token1"},
                "user_agent": "agent1",
                "timestamp": time.time(),
            },
            "spider2": {
                "cookies": {"cf_clearance": "token2"},
                "user_agent": "agent2",
                "timestamp": time.time(),
            },
        }

        # Each spider has its own cookies
        assert (
            CloudflareDownloadHandler._cookie_cache["spider1"]["cookies"][
                "cf_clearance"
            ]
            == "token1"
        )
        assert (
            CloudflareDownloadHandler._cookie_cache["spider2"]["cookies"][
                "cf_clearance"
            ]
            == "token2"
        )


class TestHybridFetchLogic:
    """Test hybrid mode fetch logic (mocked browser)."""

    @pytest.mark.unit
    async def test_hybrid_fetch_uses_http_with_cached_cookies(self):
        """Test that hybrid mode uses HTTP when cookies are cached."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {}
        request = Mock(spec=Request)
        request.url = "https://example.com/page"

        # Cached cookie for this host (key is "<spider>|<host>") -> skips verify
        CloudflareDownloadHandler._cookie_cache = {
            "test_spider|example.com": {
                "cookies": {"cf_clearance": "valid_token"},
                "user_agent": "Mozilla/5.0",
                "seq": 1,
                "timestamp": time.time(),
            }
        }

        # Mock HTTP fetch to return non-blocked HTML
        with patch.object(
            handler, "_fetch_with_http", new_callable=AsyncMock
        ) as mock_http:
            mock_http.return_value = "<html><body>Success</body></html>"

            html = await handler._hybrid_fetch_async(request, spider)

            # Should use HTTP, not browser
            mock_http.assert_called_once()
            assert html == "<html><body>Success</body></html>"

    @pytest.mark.unit
    async def test_hybrid_fetch_detects_blocks(self):
        """Test that hybrid mode detects blocked responses."""
        handler = CloudflareDownloadHandler({})

        # Test that block detection works
        blocked_html = "<html>Cloudflare checking your browser...</html>"
        assert handler._is_blocked(blocked_html) is True

        # Test that normal HTML passes
        normal_html = "<html><body>" + "content " * 1000 + "</body></html>"
        assert handler._is_blocked(normal_html) is False


class TestErrorHandling:
    """Test error handling in Cloudflare handler."""

    @pytest.mark.unit
    def test_browser_fetch_raises_on_failure(self):
        """Test that browser fetch raises exception on failure."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        request = Mock(spec=Request)
        request.url = "https://example.com"

        # Mock browser fetch to return None (failure)
        with patch.object(CloudflareDownloadHandler, "_run_async", return_value=None):
            with pytest.raises(Exception, match="Failed to fetch"):
                handler._browser_only_fetch_sync(request, spider)

    @pytest.mark.unit
    def test_hybrid_fetch_raises_on_no_cookies_after_refresh(self):
        """Test that hybrid fetch raises when cookies unavailable after refresh."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {}
        request = Mock(spec=Request)
        request.url = "https://example.com"

        # Reverify is a no-op (cache stays empty) -> fetch must raise, not hang
        with patch.object(handler, "_reverify", new_callable=AsyncMock):
            CloudflareDownloadHandler._cookie_cache = {}

            with pytest.raises(Exception, match="No cookies available"):
                handler._hybrid_fetch_sync(request, spider)


class TestHandlerLifecycle:
    """Test handler open/close lifecycle."""

    @pytest.mark.unit
    def test_handler_opens_without_starting_browser(self):
        """Test that handler open doesn't immediately start browser."""
        handler = CloudflareDownloadHandler({})

        # Should not raise
        handler.open()

        # Browser should not be started yet (lazy initialization)
        assert CloudflareDownloadHandler._browser_started is False

    @pytest.mark.unit
    async def test_handler_close_stops_browser(self):
        """Test that handler close cleans up browser state."""
        handler = CloudflareDownloadHandler({})

        # Mock browser as started
        mock_browser = Mock()
        mock_browser.browser = Mock()  # Mock the browser attribute
        mock_browser.close = AsyncMock()  # Mock the async close method

        CloudflareDownloadHandler._shared_browser = mock_browser
        CloudflareDownloadHandler._browser_started = True

        # Call async close()
        await handler.close()

        # Browser close should have been called
        mock_browser.close.assert_called_once()

        assert CloudflareDownloadHandler._browser_started is False
        assert CloudflareDownloadHandler._shared_browser is None
