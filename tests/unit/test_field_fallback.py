"""A field selector is PRIMARY; the built-in reader is the BACKUP.

When a selector returns null it must NOT overwrite the value the reader already
produced for a core field — so a broken/missing selector can never wipe content.
Non-core fields have nothing to fall back to, so they stay null.
"""

import pytest
from scrapy.http import HtmlResponse

from spiders.base import BaseDBSpiderMixin

pytestmark = pytest.mark.unit


def _mixin(fields, schema_fields):
    s = BaseDBSpiderMixin()
    s.custom_settings = {"FIELDS": fields}

    class _Cfg:
        project = "proj"

    s.spider_config = _Cfg()
    s._load_project_schema_fields = lambda project: schema_fields
    return s


def _resp(html):
    return HtmlResponse(url="https://x.com/a", body=html.encode(), encoding="utf-8")


def test_null_selector_keeps_reader_value_for_core_field():
    s = _mixin({"author": {"css": ".nope::text"}}, ["title", "content", "author"])
    item = {"title": "T", "content": "Body", "author": "Reader Author"}
    s._apply_field_extract(item, _resp("<h1>T</h1><div>Body</div>"))
    assert item["author"] == "Reader Author"  # broken selector did NOT wipe it


def test_nonnull_selector_overrides_reader_value():
    s = _mixin({"author": {"css": "span.by::text"}}, ["title", "content", "author"])
    item = {"title": "T", "content": "Body", "author": "Reader Author"}
    s._apply_field_extract(item, _resp('<span class="by">Real Author</span>'))
    assert item["author"] == "Real Author"  # selector wins when it has a value


def test_null_selector_on_non_core_field_is_none():
    s = _mixin({"price": {"css": ".nope::text"}}, ["title", "price"])
    item = {"title": "T"}
    s._apply_field_extract(item, _resp("<h1>T</h1>"))
    assert item.get("price") is None  # non-core: nothing to fall back to


def test_nonnull_selector_on_non_core_field_is_set():
    s = _mixin({"price": {"css": ".p::text"}}, ["title", "price"])
    item = {"title": "T"}
    s._apply_field_extract(item, _resp('<span class="p">42</span>'))
    assert item["price"] == "42"
