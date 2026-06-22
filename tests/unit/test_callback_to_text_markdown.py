"""
Tests for to_text / to_markdown support on callback field extraction.

These directives already existed on FIELDS (FieldExtractDirective); this brings
the callback path (FieldExtractSchema + _extract_field) to parity so per-section
extraction via callbacks can produce clean text / markdown.
"""

import pytest
from pydantic import ValidationError
from scrapy import Selector

from core.schemas import FieldExtractSchema
from spiders.base import BaseDBSpiderMixin

pytestmark = pytest.mark.unit

HTML = '<div class="body"><p>Hello <b>world</b></p><p>Second para</p></div>'


def _extract(html, config):
    return BaseDBSpiderMixin()._extract_field(Selector(text=html), config)


class TestCallbackSchema:
    def test_accepts_to_text(self):
        FieldExtractSchema(css="div.body", to_text=True)

    def test_accepts_to_markdown(self):
        FieldExtractSchema(css="div.body", to_markdown=True)

    def test_rejects_to_text_with_get_all(self):
        with pytest.raises(ValidationError):
            FieldExtractSchema(css="div.body", to_text=True, get_all=True)

    def test_rejects_to_text_and_to_markdown_together(self):
        with pytest.raises(ValidationError):
            FieldExtractSchema(css="div.body", to_text=True, to_markdown=True)


class TestExtractField:
    def test_to_text_joins_descendant_text(self):
        value = _extract(HTML, {"css": "div.body", "to_text": True})
        assert value == "Hello world Second para"

    def test_to_text_with_text_pseudo_element(self):
        value = _extract(HTML, {"css": "div.body p::text", "to_text": True})
        assert "Hello" in value and "Second para" in value

    def test_to_markdown_converts_html(self):
        value = _extract(HTML, {"css": "div.body", "to_markdown": True})
        assert "**world**" in value
        assert "Second para" in value

    def test_get_all_still_works(self):
        value = _extract(HTML, {"css": "div.body p::text", "get_all": True})
        assert value == ["Hello ", "Second para"]

    def test_plain_css_still_works(self):
        value = _extract(HTML, {"css": "b::text"})
        assert value == "world"
