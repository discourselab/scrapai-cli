"""Unit tests for callback schemas and extraction logic."""

import asyncio
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from scrapy.http import HtmlResponse, Request
from scrapy.selector import Selector
from core.schemas import (
    ProcessorSchema,
    FieldExtractSchema,
    CallbackSchema,
    SpiderConfigSchema,
    UrlContextFieldSchema,
    IterateFollowSchema,
    IterateSchema,
)


class TestProcessorSchema:
    def test_valid_processor(self):
        schema = ProcessorSchema(type="strip")
        assert schema.type == "strip"

    def test_processor_with_params(self):
        schema = ProcessorSchema(type="replace", old="x", new="y")
        assert schema.type == "replace"
        assert schema.old == "x"
        assert schema.new == "y"

    def test_unknown_processor_type(self):
        with pytest.raises(ValidationError) as exc_info:
            ProcessorSchema(type="unknown_processor")
        assert "Unknown processor type" in str(exc_info.value)

    def test_all_valid_types(self):
        valid_types = [
            "strip",
            "replace",
            "regex",
            "cast",
            "join",
            "default",
            "lowercase",
            "parse_datetime",
        ]
        for ptype in valid_types:
            schema = ProcessorSchema(type=ptype)
            assert schema.type == ptype


class TestFieldExtractSchema:
    def test_css_selector(self):
        schema = FieldExtractSchema(css="h1.title::text")
        assert schema.css == "h1.title::text"
        assert schema.get_all is False

    def test_xpath_selector(self):
        schema = FieldExtractSchema(xpath="//h1[@class='title']/text()")
        assert schema.xpath == "//h1[@class='title']/text()"

    def test_get_all_flag(self):
        schema = FieldExtractSchema(css="div.item", get_all=True)
        assert schema.get_all is True

    def test_with_processors(self):
        schema = FieldExtractSchema(
            css="span.price::text",
            processors=[
                {"type": "strip"},
                {"type": "regex", "pattern": r"(\d+)"},
                {"type": "cast", "to": "int"},
            ],
        )
        assert len(schema.processors) == 3
        assert schema.processors[0].type == "strip"

    def test_nested_list(self):
        schema = FieldExtractSchema(
            type="nested_list",
            selector="div.item",
            extract={
                "name": {"css": "h3::text"},
                "price": {"css": "span.price::text"},
            },
        )
        assert schema.type == "nested_list"
        assert schema.selector == "div.item"
        assert "name" in schema.extract

    def test_missing_selector_fails(self):
        # Must have either css/xpath or be nested_list
        with pytest.raises(ValidationError) as exc_info:
            FieldExtractSchema(get_all=True)
        assert "selector" in str(exc_info.value).lower()

    def test_nested_list_missing_fields_fails(self):
        # nested_list requires both selector and extract
        with pytest.raises(ValidationError) as exc_info:
            FieldExtractSchema(type="nested_list", selector="div.item")
        assert "extract" in str(exc_info.value).lower()


class TestCallbackSchema:
    def test_valid_callback(self):
        schema = CallbackSchema(
            extract={
                "title": {"css": "h1::text"},
                "price": {"css": "span.price::text"},
            }
        )
        assert len(schema.extract) == 2

    def test_empty_extract_fails(self):
        # Must have at least one of extract (non-empty) or iterate
        with pytest.raises(ValidationError):
            CallbackSchema(extract={})

    def test_callback_with_iterate_only(self):
        schema = CallbackSchema(
            iterate={
                "selector": "table tr",
                "follow": {
                    "url": {"css": "td a::attr(href)"},
                    "callback": "parse_detail",
                },
            }
        )
        assert schema.iterate is not None
        assert schema.extract is None

    def test_callback_with_both_extract_and_iterate(self):
        schema = CallbackSchema(
            extract={"rank": {"css": "span.rank::text"}},
            iterate={
                "selector": "table tr",
                "follow": {
                    "url": {"css": "td a::attr(href)"},
                    "callback": "parse_detail",
                },
            },
        )
        assert schema.iterate is not None
        assert len(schema.extract) == 1

    def test_callback_requires_extract_or_iterate(self):
        with pytest.raises(ValidationError) as exc_info:
            CallbackSchema()
        assert (
            "extract" in str(exc_info.value).lower()
            or "iterate" in str(exc_info.value).lower()
        )

    def test_callback_none_extract_no_iterate_fails(self):
        with pytest.raises(ValidationError):
            CallbackSchema(extract=None, iterate=None)


class TestSpiderConfigSchemaWithCallbacks:
    def test_valid_callbacks(self):
        config = SpiderConfigSchema(
            name="test_spider",
            source_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com"],
            callbacks={
                "parse_product": {
                    "extract": {
                        "name": {"css": "h1.title::text"},
                        "price": {"css": "span.price::text"},
                    }
                }
            },
        )
        assert "parse_product" in config.callbacks

    def test_reserved_callback_name_fails(self):
        reserved_names = [
            "parse_article",
            "parse_start_url",
            "start_requests",
            "from_crawler",
            "closed",
            "parse",
        ]
        for reserved in reserved_names:
            with pytest.raises(ValidationError) as exc_info:
                SpiderConfigSchema(
                    name="test_spider",
                    source_url="https://example.com",
                    allowed_domains=["example.com"],
                    start_urls=["https://example.com"],
                    callbacks={reserved: {"extract": {"title": {"css": "h1::text"}}}},
                )
            assert "reserved" in str(exc_info.value).lower()

    def test_invalid_callback_identifier_fails(self):
        # Callback names must be valid Python identifiers
        with pytest.raises(ValidationError):
            SpiderConfigSchema(
                name="test_spider",
                source_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com"],
                callbacks={
                    "parse-product": {  # Hyphens not allowed
                        "extract": {"title": {"css": "h1::text"}}
                    }
                },
            )

    def test_rule_callback_cross_validation(self):
        # Rule references undefined callback (when callbacks dict exists but callback not in it)
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(
                name="test_spider",
                source_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com"],
                rules=[{"allow": [r"/product/\d+"], "callback": "parse_product"}],
                callbacks={"parse_review": {"extract": {"title": {"css": "h1::text"}}}},
            )
        assert "undefined callback" in str(exc_info.value).lower()

    def test_rule_callback_defined_succeeds(self):
        # Rule references defined callback - should succeed
        config = SpiderConfigSchema(
            name="test_spider",
            source_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com"],
            rules=[{"allow": [r"/product/\d+"], "callback": "parse_product"}],
            callbacks={"parse_product": {"extract": {"title": {"css": "h1::text"}}}},
        )
        assert config.rules[0].callback == "parse_product"

    def test_parse_article_always_allowed(self):
        # Built-in parse_article callback doesn't need to be defined
        config = SpiderConfigSchema(
            name="test_spider",
            source_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com"],
            rules=[{"allow": [r"/article/\d+"], "callback": "parse_article"}],
        )
        assert config.rules[0].callback == "parse_article"


class TestFieldExtraction:
    """Test field extraction logic (mocking spider methods)."""

    def test_extract_field_css(self):
        from spiders.base import BaseDBSpiderMixin

        html = "<div><h1>Test Title</h1></div>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        result = mixin._extract_field(selector, {"css": "h1::text"})
        assert result == "Test Title"

    def test_extract_field_css_get_all(self):
        from spiders.base import BaseDBSpiderMixin

        html = "<ul><li>A</li><li>B</li><li>C</li></ul>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        result = mixin._extract_field(selector, {"css": "li::text", "get_all": True})
        assert result == ["A", "B", "C"]

    def test_extract_field_xpath(self):
        from spiders.base import BaseDBSpiderMixin

        html = "<div><span class='price'>$99</span></div>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        result = mixin._extract_field(
            selector, {"xpath": "//span[@class='price']/text()"}
        )
        assert result == "$99"

    def test_extract_field_missing_selector(self):
        from spiders.base import BaseDBSpiderMixin

        html = "<div>Test</div>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        result = mixin._extract_field(selector, {})
        assert result is None

    def test_extract_nested_list(self):
        from spiders.base import BaseDBSpiderMixin

        html = """
        <div class='products'>
            <div class='item'>
                <h3>Product A</h3>
                <span class='price'>$10</span>
            </div>
            <div class='item'>
                <h3>Product B</h3>
                <span class='price'>$20</span>
            </div>
        </div>
        """
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        config = {
            "selector": "div.item",
            "extract": {
                "name": {"css": "h3::text"},
                "price": {"css": "span.price::text"},
            },
        }

        result = mixin._extract_nested_list(selector, config, depth=0, max_depth=3)

        assert len(result) == 2
        assert result[0]["name"] == "Product A"
        assert result[0]["price"] == "$10"
        assert result[1]["name"] == "Product B"
        assert result[1]["price"] == "$20"

    def test_extract_nested_list_max_depth(self):
        from spiders.base import BaseDBSpiderMixin

        html = "<div class='item'><div class='nested'>Test</div></div>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        config = {
            "selector": "div.nested",
            "extract": {"text": {"css": "::text"}},
        }

        # Depth = 3, max_depth = 3 -> should return empty list
        result = mixin._extract_nested_list(selector, config, depth=3, max_depth=3)
        assert result == []


class TestIterateSchemas:
    """Test iterate-related schema validation."""

    def test_url_context_valid_regex(self):
        schema = UrlContextFieldSchema(regex=r"/(\w{2})/")
        assert schema.regex == r"/(\w{2})/"

    def test_url_context_invalid_regex(self):
        with pytest.raises(ValidationError) as exc_info:
            UrlContextFieldSchema(regex=r"[invalid")
        assert "Invalid regex" in str(exc_info.value)

    def test_url_context_no_capture_group(self):
        with pytest.raises(ValidationError) as exc_info:
            UrlContextFieldSchema(regex=r"/\w+/")
        assert "capture group" in str(exc_info.value).lower()

    def test_url_context_multiple_capture_groups(self):
        with pytest.raises(ValidationError) as exc_info:
            UrlContextFieldSchema(regex=r"(\w+)/(\w+)")
        assert "capture group" in str(exc_info.value).lower()

    def test_iterate_follow_schema(self):
        schema = IterateFollowSchema(
            url={"css": "td a::attr(href)"},
            callback="parse_detail",
        )
        assert schema.callback == "parse_detail"

    def test_iterate_follow_invalid_callback(self):
        with pytest.raises(ValidationError):
            IterateFollowSchema(
                url={"css": "td a::attr(href)"},
                callback="invalid-name",
            )

    def test_iterate_schema_full(self):
        schema = IterateSchema(
            selector="table tr",
            follow={
                "url": {"css": "td a::attr(href)"},
                "callback": "parse_detail",
            },
            url_context={"country": {"regex": r"/(\w{2})/"}},
        )
        assert schema.selector == "table tr"
        assert schema.follow.callback == "parse_detail"
        assert "country" in schema.url_context

    def test_iterate_schema_without_url_context(self):
        schema = IterateSchema(
            selector="table tr",
            follow={
                "url": {"css": "td a::attr(href)"},
                "callback": "parse_detail",
            },
        )
        assert schema.url_context is None


class TestIterateCrossValidation:
    """Test cross-validation of iterate.follow.callback in SpiderConfigSchema."""

    def test_iterate_follow_callback_references_defined(self):
        config = SpiderConfigSchema(
            name="test_spider",
            source_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com"],
            callbacks={
                "parse_listing": {
                    "iterate": {
                        "selector": "table tr",
                        "follow": {
                            "url": {"css": "td a::attr(href)"},
                            "callback": "parse_detail",
                        },
                    },
                },
                "parse_detail": {
                    "extract": {"name": {"css": "h1::text"}},
                },
            },
        )
        assert (
            config.callbacks["parse_listing"].iterate.follow.callback == "parse_detail"
        )

    def test_iterate_follow_callback_undefined_fails(self):
        with pytest.raises(ValidationError) as exc_info:
            SpiderConfigSchema(
                name="test_spider",
                source_url="https://example.com",
                allowed_domains=["example.com"],
                start_urls=["https://example.com"],
                callbacks={
                    "parse_listing": {
                        "iterate": {
                            "selector": "table tr",
                            "follow": {
                                "url": {"css": "td a::attr(href)"},
                                "callback": "parse_nonexistent",
                            },
                        },
                    },
                },
            )
        assert "undefined callback" in str(exc_info.value).lower()

    def test_iterate_follow_callback_parse_article_allowed(self):
        """parse_article is a built-in callback and should always be valid."""
        config = SpiderConfigSchema(
            name="test_spider",
            source_url="https://example.com",
            allowed_domains=["example.com"],
            start_urls=["https://example.com"],
            callbacks={
                "parse_listing": {
                    "iterate": {
                        "selector": "table tr",
                        "follow": {
                            "url": {"css": "td a::attr(href)"},
                            "callback": "parse_article",
                        },
                    },
                },
            },
        )
        assert (
            config.callbacks["parse_listing"].iterate.follow.callback == "parse_article"
        )


class TestIterateRuntime:
    """Test iterate runtime logic in BaseDBSpiderMixin."""

    def _make_mixin(self):
        """Create a BaseDBSpiderMixin with mock spider attributes."""
        from spiders.base import BaseDBSpiderMixin

        mixin = BaseDBSpiderMixin()
        mixin.spider_name = "test_spider"
        mixin.spider_config = MagicMock()
        mixin.spider_config.id = 1
        mixin._items_scraped = 0
        return mixin

    def _make_response(self, url, html):
        """Create a Scrapy HtmlResponse for testing."""
        request = Request(url=url)
        return HtmlResponse(url=url, body=html.encode(), request=request)

    def test_extract_url_context(self):
        mixin = self._make_mixin()
        url = "https://example.com/us/california.htm"
        config = {
            "country_code": {"regex": r"/(\w{2})/"},
            "state": {"regex": r"/\w{2}/([\w-]+)\.htm"},
        }
        result = mixin._extract_url_context(url, config)
        assert result["country_code"] == "us"
        assert result["state"] == "california"

    def test_extract_url_context_no_match(self):
        mixin = self._make_mixin()
        url = "https://example.com/page"
        config = {"code": {"regex": r"/(\d{5})/"}}
        result = mixin._extract_url_context(url, config)
        assert result["code"] is None

    def test_iterate_callback_yields_requests(self):
        mixin = self._make_mixin()
        # Register a dummy detail callback
        detail_called = []

        async def parse_detail(response):
            detail_called.append(response.url)
            yield {"url": response.url}

        setattr(mixin, "parse_detail", parse_detail)

        callback_config = {
            "iterate": {
                "selector": "table tr",
                "follow": {
                    "url": {"css": "td a::attr(href)"},
                    "callback": "parse_detail",
                },
            },
            "extract": {
                "name": {"css": "td.name::text"},
            },
        }

        html = """
        <table>
            <tr>
                <td class="name">Item A</td>
                <td><a href="/detail/1">Link</a></td>
            </tr>
            <tr>
                <td class="name">Item B</td>
                <td><a href="/detail/2">Link</a></td>
            </tr>
        </table>
        """
        response = self._make_response("https://example.com/listing", html)
        callback = mixin._make_callback("parse_listing", callback_config)

        # Collect yielded objects
        results = list(
            asyncio.get_event_loop().run_until_complete(
                self._collect_async(callback(response))
            )
        )

        assert len(results) == 2
        # Should yield Request objects (response.follow returns Request)
        assert all(hasattr(r, "url") for r in results)
        assert "/detail/1" in results[0].url
        assert "/detail/2" in results[1].url
        # Check meta contains listing_data
        assert results[0].meta["listing_data"]["name"] == "Item A"
        assert results[1].meta["listing_data"]["name"] == "Item B"

    def test_iterate_skips_rows_without_url(self):
        mixin = self._make_mixin()

        async def parse_detail(response):
            yield {"url": response.url}

        setattr(mixin, "parse_detail", parse_detail)

        callback_config = {
            "iterate": {
                "selector": "table tr",
                "follow": {
                    "url": {"css": "td a::attr(href)"},
                    "callback": "parse_detail",
                },
            },
        }

        html = """
        <table>
            <tr><td class="name">Has link</td><td><a href="/detail/1">Link</a></td></tr>
            <tr><td class="name">No link</td><td>No anchor tag here</td></tr>
        </table>
        """
        response = self._make_response("https://example.com/listing", html)
        callback = mixin._make_callback("parse_listing", callback_config)

        results = list(
            asyncio.get_event_loop().run_until_complete(
                self._collect_async(callback(response))
            )
        )

        # Only one row has a URL, so only one request
        assert len(results) == 1
        assert "/detail/1" in results[0].url

    def test_iterate_with_url_context(self):
        mixin = self._make_mixin()

        async def parse_detail(response):
            yield {"url": response.url}

        setattr(mixin, "parse_detail", parse_detail)

        callback_config = {
            "iterate": {
                "selector": "table tr",
                "url_context": {
                    "country": {"regex": r"/([a-z]{2})/listing"},
                },
                "follow": {
                    "url": {"css": "td a::attr(href)"},
                    "callback": "parse_detail",
                },
            },
            "extract": {
                "name": {"css": "td.name::text"},
            },
        }

        html = """
        <table>
            <tr><td class="name">Item A</td><td><a href="/detail/1">Link</a></td></tr>
        </table>
        """
        response = self._make_response("https://example.com/us/listing", html)
        callback = mixin._make_callback("parse_listing", callback_config)

        results = list(
            asyncio.get_event_loop().run_until_complete(
                self._collect_async(callback(response))
            )
        )

        assert len(results) == 1
        listing_data = results[0].meta["listing_data"]
        assert listing_data["country"] == "us"
        assert listing_data["name"] == "Item A"

    def test_detail_callback_merges_listing_data(self):
        mixin = self._make_mixin()

        callback_config = {
            "extract": {
                "website": {"css": "a.site::attr(href)"},
            },
        }

        html = '<div><a class="site" href="https://news.com">Visit</a></div>'
        response = self._make_response("https://example.com/detail/1", html)
        # Simulate meta from iterate parent
        response.request.meta["listing_data"] = {
            "rank": 1,
            "name": "News Site",
            "country": "us",
        }

        callback = mixin._make_callback("parse_detail", callback_config)

        results = list(
            asyncio.get_event_loop().run_until_complete(
                self._collect_async(callback(response))
            )
        )

        assert len(results) == 1
        item = results[0]
        # Merged listing_data fields
        assert item["rank"] == 1
        assert item["name"] == "News Site"
        assert item["country"] == "us"
        # Extracted detail field
        assert item["website"] == "https://news.com"
        assert item["url"] == "https://example.com/detail/1"

    def test_backward_compat_no_iterate(self):
        """Standard callbacks without iterate should work unchanged."""
        mixin = self._make_mixin()

        callback_config = {
            "extract": {
                "title": {"css": "h1::text"},
            },
        }

        html = "<div><h1>Test Title</h1></div>"
        response = self._make_response("https://example.com/page", html)

        callback = mixin._make_callback("parse_page", callback_config)

        results = list(
            asyncio.get_event_loop().run_until_complete(
                self._collect_async(callback(response))
            )
        )

        assert len(results) == 1
        assert results[0]["title"] == "Test Title"
        assert results[0]["url"] == "https://example.com/page"
        assert mixin._items_scraped == 1

    async def _collect_async(self, async_gen):
        """Collect all items from an async generator."""
        items = []
        async for item in async_gen:
            items.append(item)
        return items


class TestProcessorIntegration:
    """Test processors applied to extracted fields."""

    def test_field_with_processors(self):
        from spiders.base import BaseDBSpiderMixin
        from core.processors import apply_processors

        html = "<span class='price'>  $99.99  </span>"
        selector = Selector(text=html)

        mixin = BaseDBSpiderMixin()
        value = mixin._extract_field(selector, {"css": "span.price::text"})

        processors = [
            {"type": "strip"},
            {"type": "regex", "pattern": r"\$(\d+\.\d+)"},
            {"type": "cast", "to": "float"},
        ]
        result = apply_processors(value, processors)

        assert result == 99.99
