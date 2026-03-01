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

    @pytest.mark.unit
    def test_default_cookie_refresh_threshold(self):
        """Test default cookie refresh is 10 minutes (600 seconds)."""
        assert CloudflareDownloadHandler.DEFAULT_COOKIE_REFRESH_THRESHOLD == 600


class TestCookieRefreshLogic:
    """Test cookie refresh timing and thresholds."""

    @pytest.mark.unit
    async def test_should_refresh_when_no_cookies(self):
        """Test that handler refreshes cookies when cache is empty."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {}

        # Clear cache
        CloudflareDownloadHandler._cookie_cache = {}

        should_refresh = await handler._should_refresh_cookies("test_spider", spider)

        assert should_refresh is True

    @pytest.mark.unit
    async def test_should_not_refresh_when_cookies_fresh(self):
        """Test that handler doesn't refresh fresh cookies."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {}

        # Add fresh cookies (just created)
        CloudflareDownloadHandler._cookie_cache = {
            "test_spider": {
                "cookies": {"cf_clearance": "test_token"},
                "user_agent": "test_agent",
                "timestamp": time.time(),  # Fresh
            }
        }

        should_refresh = await handler._should_refresh_cookies("test_spider", spider)

        assert should_refresh is False

    @pytest.mark.unit
    async def test_should_refresh_when_cookies_expired(self):
        """Test that handler refreshes cookies after threshold."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {"CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 600}  # 10 min

        # Add expired cookies (11 minutes old)
        CloudflareDownloadHandler._cookie_cache = {
            "test_spider": {
                "cookies": {"cf_clearance": "old_token"},
                "user_agent": "test_agent",
                "timestamp": time.time() - 660,  # 11 minutes ago
            }
        }

        should_refresh = await handler._should_refresh_cookies("test_spider", spider)

        assert should_refresh is True

    @pytest.mark.unit
    async def test_custom_refresh_threshold(self):
        """Test custom cookie refresh threshold."""
        handler = CloudflareDownloadHandler({})
        spider = Mock()
        spider.name = "test_spider"
        spider.custom_settings = {
            "CLOUDFLARE_COOKIE_REFRESH_THRESHOLD": 300
        }  # 5 min custom

        # Cookies 6 minutes old (should refresh with 5 min threshold)
        CloudflareDownloadHandler._cookie_cache = {
            "test_spider": {
                "cookies": {"cf_clearance": "token"},
                "user_agent": "agent",
                "timestamp": time.time() - 360,  # 6 minutes ago
            }
        }

        should_refresh = await handler._should_refresh_cookies("test_spider", spider)

        assert should_refresh is True


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
    async def test_invalidate_cookies_removes_from_cache(self):
        """Test that invalidating cookies removes them from cache."""
        handler = CloudflareDownloadHandler({})
        spider_name = "test_spider"

        # Add cookies
        CloudflareDownloadHandler._cookie_cache = {
            spider_name: {
                "cookies": {"cf_clearance": "token"},
                "user_agent": "agent",
                "timestamp": time.time(),
            }
        }

        # Invalidate
        await handler._invalidate_cookies(spider_name)

        # Should be removed
        assert spider_name not in CloudflareDownloadHandler._cookie_cache

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

        # Mock fresh cookies
        CloudflareDownloadHandler._cookie_cache = {
            "test_spider": {
                "cookies": {"cf_clearance": "valid_token"},
                "user_agent": "Mozilla/5.0",
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

        # Mock: cookies needed, refresh succeeds, but cache still empty
        with patch.object(
            handler,
            "_should_refresh_cookies",
            new_callable=AsyncMock,
            return_value=True,
        ):
            with patch.object(handler, "_refresh_cookies", new_callable=AsyncMock):
                # Cache is empty after refresh (shouldn't happen, but test error handling)
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
