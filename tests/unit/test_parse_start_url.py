"""parse_start_url must only parse a start URL that is actually content.

A listing/section start URL (e.g. /annual-reports/) must NOT be force-parsed as
an article — that produced junk rows in pure-CSS mode. It's parsed only when it
matches a content rule, or (single-page spider) when there are no rules at all.
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from spiders.database_spider import DatabaseSpider
from core.models import Spider, SpiderRule

pytestmark = pytest.mark.unit


def _rule(allow=None, callback=None, priority=0):
    r = Mock(spec=SpiderRule)
    r.allow_patterns = allow
    r.deny_patterns = None
    r.restrict_xpaths = None
    r.restrict_css = None
    r.tags = None
    r.callback = callback
    r.follow = True
    r.priority = priority
    return r


def _build(rules):
    rec = Mock(spec=Spider)
    rec.name = "t"
    rec.active = True
    rec.allowed_domains = ["example.com"]
    rec.start_urls = ["https://example.com"]
    rec.rules = rules
    rec.callbacks_config = {}
    rec.settings = []

    with patch("spiders.database_spider.get_db") as mock_get_db:
        mock_db = Mock()
        mock_db.query.return_value.filter.return_value.first.return_value = rec
        cm = MagicMock()
        cm.__enter__.return_value = mock_db
        mock_get_db.return_value = cm
        with patch.object(DatabaseSpider, "_load_settings_from_db"), patch.object(
            DatabaseSpider, "_setup_cloudflare_handlers"
        ):
            return DatabaseSpider(spider_name="t")


async def _collect(spider, url):
    async def fake_parse_article(response):
        yield {"cb": "parse_article", "url": response.url}

    spider.parse_article = fake_parse_article
    resp = Mock()
    resp.url = url
    items = []
    async for item in spider.parse_start_url(resp):
        items.append(item)
    return items


async def test_listing_start_url_not_parsed():
    spider = _build([_rule(allow=["/article/.*"], callback="parse_article")])
    items = await _collect(spider, "https://example.com/annual-reports/")
    assert items == []


async def test_content_start_url_is_parsed():
    spider = _build([_rule(allow=["/article/.*"], callback="parse_article")])
    items = await _collect(spider, "https://example.com/article/123")
    assert len(items) == 1
    assert items[0]["cb"] == "parse_article"


async def test_single_page_spider_no_rules_is_parsed():
    spider = _build([])
    items = await _collect(spider, "https://example.com/some-article")
    assert len(items) == 1


async def test_follow_only_rules_listing_not_parsed():
    # A pagination/follow-only rule (no callback) must not cause the start URL
    # to be parsed as an article.
    spider = _build([_rule(allow=["/page/\\d+/"], callback=None)])
    items = await _collect(spider, "https://example.com/")
    assert items == []


async def test_catch_all_rule_still_parses():
    # Documented behavior: a catch-all `.*` content rule matches everything,
    # so the start URL IS parsed. (User's config choice, asserted intentionally.)
    spider = _build([_rule(allow=[".*"], callback="parse_article")])
    items = await _collect(spider, "https://example.com/anything")
    assert len(items) == 1
