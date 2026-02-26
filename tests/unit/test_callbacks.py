"""Unit tests for callback schemas and extraction logic."""

import pytest
from pydantic import ValidationError
from scrapy.selector import Selector
from core.schemas import (
    ProcessorSchema,
    FieldExtractSchema,
    CallbackSchema,
    SpiderConfigSchema,
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
        # Must have at least one field
        with pytest.raises(ValidationError):
            CallbackSchema(extract={})


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
