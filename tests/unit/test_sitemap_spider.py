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


def _make_active_spider_record(name="bbc_co_uk", rules=None):
    """Return a Mock Spider DB record that loads cleanly for either spider."""
    rec = Mock(spec=Spider)
    rec.id = 42
    rec.name = name
    rec.active = True
    rec.allowed_domains = ["bbc.co.uk"]
    rec.start_urls = ["https://bbc.co.uk/sitemap.xml"]
    rec.rules = rules if rules is not None else []
    rec.callbacks_config = {}
    rec.settings = []
    return rec


def _make_rule(allow=None, deny=None, callback="parse_article", priority=0):
    """Mock a DB Rule record for sitemap rule compilation."""
    rule = Mock()
    rule.allow_patterns = allow or []
    rule.deny_patterns = deny or []
    rule.callback = callback
    rule.priority = priority
    return rule


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


class TestSitemapRelativeLocResolution:
    """Relative <loc> values must be resolved to absolute URLs without aborting
    iteration of the rest of the sitemap (item #1 — silent data loss guard)."""

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_relative_locs_resolved_to_absolute(self, mock_get_db):
        _patch_get_db(mock_get_db, _make_active_spider_record("bbc_co_uk"))
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = [
            {"loc": "/media/blog/post-1"},  # root-relative, placed FIRST
            {"loc": "https://bbc.co.uk/media/blog/post-2"},  # already absolute
            {"loc": "//cdn.bbc.co.uk/post-3"},  # protocol-relative
        ]

        out = list(spider.sitemap_filter(entries))

        # Regression guard: nothing dropped after the relative entry.
        assert len(out) == len(entries)
        # Every yielded loc is absolute (has a scheme).
        from urllib.parse import urlparse

        assert all(urlparse(e["loc"]).scheme for e in out)
        assert out[0]["loc"] == "https://bbc.co.uk/media/blog/post-1"
        assert out[2]["loc"] == "https://cdn.bbc.co.uk/post-3"


class TestSitemapDenyPatterns:
    """Sitemap spiders must honor deny_patterns (item #2)."""

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_deny_drops_matching_locs(self, mock_get_db):
        rule = _make_rule(allow=["/article/.*"], deny=[r"\.pdf$"])
        _patch_get_db(
            mock_get_db, _make_active_spider_record("bbc_co_uk", rules=[rule])
        )
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = [
            {"loc": "https://bbc.co.uk/article/1"},
            {"loc": "https://bbc.co.uk/files/doc.pdf"},
            {"loc": "https://bbc.co.uk/article/2"},
        ]

        out = [e["loc"] for e in spider.sitemap_filter(entries)]

        assert "https://bbc.co.uk/files/doc.pdf" not in out
        assert "https://bbc.co.uk/article/1" in out
        assert "https://bbc.co.uk/article/2" in out

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_deny_only_rule_is_collected(self, mock_get_db):
        """A deny-only rule (no allow) must still have its deny enforced."""
        rule = _make_rule(allow=None, deny=[r"\.pdf$"])
        _patch_get_db(
            mock_get_db, _make_active_spider_record("bbc_co_uk", rules=[rule])
        )
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = [
            {"loc": "https://bbc.co.uk/post"},
            {"loc": "https://bbc.co.uk/doc.pdf"},
        ]

        out = [e["loc"] for e in spider.sitemap_filter(entries)]

        assert out == ["https://bbc.co.uk/post"]

    @pytest.mark.unit
    @patch("spiders.sitemap_spider.get_db")
    def test_deny_applied_to_resolved_relative_loc(self, mock_get_db):
        """Deny must run on the absolute URL (after relative resolution)."""
        rule = _make_rule(deny=[r"\.pdf$"])
        _patch_get_db(
            mock_get_db, _make_active_spider_record("bbc_co_uk", rules=[rule])
        )
        spider = SitemapDatabaseSpider(spider_name="bbc_co_uk")

        entries = [
            {"loc": "/files/relative.pdf"},  # relative AND denied
            {"loc": "/posts/keep"},
        ]

        out = [e["loc"] for e in spider.sitemap_filter(entries)]

        assert out == ["https://bbc.co.uk/posts/keep"]


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
