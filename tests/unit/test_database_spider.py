"""
Unit tests for DatabaseSpider - edge cases and error handling.

Integration tests cover the happy path, these cover error conditions.
"""

import pytest
from unittest.mock import Mock, patch
from spiders.database_spider import DatabaseSpider
from core.models import Spider, SpiderRule


class TestDatabaseSpiderInit:
    """Test spider initialization and configuration loading."""

    @pytest.mark.unit
    def test_requires_spider_name(self):
        """Test that spider_name is required."""
        with pytest.raises(ValueError, match="spider_name argument is required"):
            DatabaseSpider()

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_fails_when_spider_not_found_in_database(self, mock_get_db):
        """Test error when spider doesn't exist in database."""
        # Mock database to return no spider
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = iter([mock_db])

        with pytest.raises(ValueError, match="not found in database"):
            DatabaseSpider(spider_name="nonexistent_spider")

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_fails_when_spider_inactive(self, mock_get_db):
        """Test error when spider is inactive."""
        # Mock database to return inactive spider
        mock_spider = Mock(spec=Spider)
        mock_spider.name = "test_spider"
        mock_spider.active = False

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_spider
        mock_get_db.return_value = iter([mock_db])

        with pytest.raises(ValueError, match="is inactive"):
            DatabaseSpider(spider_name="test_spider")


class TestRuleCompilation:
    """Test rule compilation from database configuration."""

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_skips_rule_with_missing_callback(self, mock_get_db):
        """Test that rules with undefined callbacks are skipped."""
        # Mock spider with rule that has callback that doesn't exist
        mock_rule = Mock(spec=SpiderRule)
        mock_rule.allow_patterns = ["/article/.*"]
        mock_rule.deny_patterns = None
        mock_rule.restrict_xpaths = None
        mock_rule.restrict_css = None
        mock_rule.callback = "nonexistent_callback"  # This callback doesn't exist
        mock_rule.follow = True
        mock_rule.priority = 0

        mock_spider = Mock(spec=Spider)
        mock_spider.name = "test_spider"
        mock_spider.active = True
        mock_spider.allowed_domains = ["example.com"]
        mock_spider.start_urls = ["https://example.com"]
        mock_spider.rules = [mock_rule]
        mock_spider.callbacks_config = {}
        mock_spider.settings = []

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_spider
        mock_get_db.return_value = iter([mock_db])

        with patch.object(DatabaseSpider, "_load_settings_from_db"):
            with patch.object(DatabaseSpider, "_setup_cloudflare_handlers"):
                spider = DatabaseSpider(spider_name="test_spider")

                # Rule with missing callback should be skipped
                assert len(spider.rules) == 0

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_compiles_rules_with_all_patterns(self, mock_get_db):
        """Test rule compilation with various pattern types."""
        # Mock rule with all pattern types
        mock_rule = Mock(spec=SpiderRule)
        mock_rule.allow_patterns = ["/article/.*"]
        mock_rule.deny_patterns = ["/admin/.*"]
        mock_rule.restrict_xpaths = ["//div[@class='content']"]
        mock_rule.restrict_css = ["div.article"]
        mock_rule.callback = None
        mock_rule.follow = True
        mock_rule.priority = 0

        mock_spider = Mock(spec=Spider)
        mock_spider.name = "test_spider"
        mock_spider.active = True
        mock_spider.allowed_domains = ["example.com"]
        mock_spider.start_urls = ["https://example.com"]
        mock_spider.rules = [mock_rule]
        mock_spider.callbacks_config = {}
        mock_spider.settings = []

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_spider
        mock_get_db.return_value = iter([mock_db])

        with patch.object(DatabaseSpider, "_load_settings_from_db"):
            with patch.object(DatabaseSpider, "_setup_cloudflare_handlers"):
                spider = DatabaseSpider(spider_name="test_spider")

                # Rule should be compiled with all patterns
                assert len(spider.rules) == 1


class TestCallbackRegistration:
    """Test callback registration from database configuration."""

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_registers_callbacks_from_config(self, mock_get_db):
        """Test that callbacks are registered from config."""
        callbacks_config = {
            "parse_product": {"extract": {"name": {"css": "h1.title::text"}}}
        }

        mock_spider = Mock(spec=Spider)
        mock_spider.name = "test_spider"
        mock_spider.active = True
        mock_spider.allowed_domains = ["example.com"]
        mock_spider.start_urls = ["https://example.com"]
        mock_spider.rules = []
        mock_spider.callbacks_config = callbacks_config
        mock_spider.settings = []

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_spider
        mock_get_db.return_value = iter([mock_db])

        with patch.object(DatabaseSpider, "_load_settings_from_db"):
            with patch.object(DatabaseSpider, "_setup_cloudflare_handlers"):
                with patch.object(
                    DatabaseSpider, "_make_callback", return_value=lambda x: None
                ):
                    spider = DatabaseSpider(spider_name="test_spider")

                    # Callback should be registered on spider
                    assert hasattr(spider, "parse_product")

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_handles_no_callbacks(self, mock_get_db):
        """Test spider with no callbacks defined."""
        mock_spider = Mock(spec=Spider)
        mock_spider.name = "test_spider"
        mock_spider.active = True
        mock_spider.allowed_domains = ["example.com"]
        mock_spider.start_urls = ["https://example.com"]
        mock_spider.rules = []
        mock_spider.callbacks_config = {}
        mock_spider.settings = []

        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_spider
        mock_get_db.return_value = iter([mock_db])

        with patch.object(DatabaseSpider, "_load_settings_from_db"):
            with patch.object(DatabaseSpider, "_setup_cloudflare_handlers"):
                spider = DatabaseSpider(spider_name="test_spider")

                # Should initialize successfully with no callbacks
                assert spider.spider_name == "test_spider"
