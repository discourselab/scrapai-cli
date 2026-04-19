"""
Unit tests for SitemapDatabaseSpider and DatabaseSpider name resolution.

These tests guard against regressions of the bug where the spider's runtime
``self.name`` would incorrectly stay as the class-level default
(``"sitemap_database_spider"`` / ``"database_spider"``) instead of being
overridden to the per-instance ``spider_name``. That bug caused DeltaFetch
caches, JSONL output paths, and pipeline source attribution to collide across
sitemap crawls.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from spiders.database_spider import DatabaseSpider
from spiders.sitemap_spider import SitemapDatabaseSpider
from core.models import Spider


def _make_active_spider_record(name="bbc_co_uk"):
    """Return a Mock Spider DB record that loads cleanly for either spider."""
    rec = Mock(spec=Spider)
    rec.id = 42
    rec.name = name
    rec.active = True
    rec.allowed_domains = ["bbc.co.uk"]
    rec.start_urls = ["https://bbc.co.uk/sitemap.xml"]
    rec.rules = []
    rec.callbacks_config = {}
    rec.settings = []
    return rec


def _patch_get_db(mock_get_db, spider_record):
    """Wire a mocked get_db() context manager to return ``spider_record``."""
    mock_db = Mock()
    mock_db.query.return_value.filter.return_value.first.return_value = spider_record
    cm = MagicMock()
    cm.__enter__.return_value = mock_db
    mock_get_db.return_value = cm


class TestSitemapSpiderNameResolution:
    """Spider.name MUST be the per-instance spider_name, not the class default."""

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_instance_name_overrides_class_default(self, mock_get_db):
        """SitemapDatabaseSpider(spider_name="bbc_co_uk") -> self.name == "bbc_co_uk"."""
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))

        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        assert spider.spider_name == "bbc_co_uk"
        # Critical: must NOT be the class-level "sitemap_database_spider"
        assert spider.name == "bbc_co_uk"
        assert spider.name != "sitemap_database_spider"

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_class_attribute_unchanged(self, mock_get_db):
        """Setting self.name must not mutate the class attribute."""
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))

        SitemapDatabaseSpider(spider_name="bbc_co_uk")

        # Other instances of the class must still see the original default.
        assert SitemapDatabaseSpider.name == "sitemap_database_spider"

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_different_spider_names_are_isolated(self, mock_get_db):
        """Two sitemap spiders with different names must each keep their own name."""
        # First spider
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))
        spider_a = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        # Second spider
        _patch_get_db(mock_get_db, _make_active_spider_record("nytimes_com"))
        spider_b = SitemapDatabaseSpider(spider_name="nytimes_com")

        assert spider_a.name == "bbc_co_uk"
        assert spider_b.name == "nytimes_com"


class TestDatabaseSpiderNameResolution:
    """DatabaseSpider should also override class-level name with spider_name."""

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_instance_name_overrides_class_default(self, mock_get_db):
        """DatabaseSpider(spider_name="bbc_co_uk") -> self.name == "bbc_co_uk"."""
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))

        spider = DatabaseSpider(spider_name="bbc_co_uk")

        assert spider.spider_name == "bbc_co_uk"
        assert spider.name == "bbc_co_uk"
        assert spider.name != "database_spider"

    @pytest.mark.unit
    @patch("spiders.database_spider.get_db")
    def test_class_attribute_unchanged(self, mock_get_db):
        """Setting self.name must not mutate the class attribute."""
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))

        DatabaseSpider(spider_name="bbc_co_uk")

        assert DatabaseSpider.name == "database_spider"
