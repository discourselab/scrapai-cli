"""Pure-CSS spiders (EXTRACTOR_ORDER=['custom']) skip the generic extractor, so
extruct never runs for them. `_apply_meta_fallback` fills published_date/author
from structured metadata when the config's selectors didn't source them — so
structured date/author is universal across both extraction paths.
"""

import pytest

from spiders.base import _apply_meta_fallback

pytestmark = pytest.mark.unit


def test_fills_missing_date_and_author():
    item = {"url": "x"}
    html = (
        '<meta property="article:published_time" content="2026-06-30T11:00:00+00:00">'
        '<script type="application/ld+json">{"author":{"name":"Ana Ruiz"}}</script>'
    )
    _apply_meta_fallback(item, html)
    assert item["published_date"] is not None
    assert item["author"] == "Ana Ruiz"


def test_does_not_override_selector_values():
    item = {"published_date": "SELECTOR_DATE", "author": "Selector Author"}
    html = (
        '<meta property="article:published_time" content="2026-06-30T11:00:00+00:00">'
    )
    _apply_meta_fallback(item, html)
    assert item["published_date"] == "SELECTOR_DATE"
    assert item["author"] == "Selector Author"


def test_stays_none_when_no_metadata():
    item = {"url": "x"}
    _apply_meta_fallback(item, "<html><body>no metadata</body></html>")
    assert item.get("published_date") is None
    assert item.get("author") is None
