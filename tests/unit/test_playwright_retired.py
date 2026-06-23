"""The legacy playwright extractor strategy is no longer in the default order,
but stays available and is auto-enabled for INFINITE_SCROLL."""

import pytest

from core.extractors import SmartExtractor
from spiders.base import with_scroll_fallback

pytestmark = pytest.mark.unit


def test_default_order_excludes_playwright():
    assert SmartExtractor().strategies == ["trafilatura", "newspaper"]
    assert "playwright" not in SmartExtractor().strategies


def test_scroll_fallback_adds_playwright_when_infinite_scroll():
    assert with_scroll_fallback(["trafilatura"], {"INFINITE_SCROLL": True}) == [
        "trafilatura",
        "playwright",
    ]


def test_scroll_fallback_noop_without_infinite_scroll():
    assert with_scroll_fallback(["trafilatura"], {}) == ["trafilatura"]


def test_scroll_fallback_no_duplicate():
    assert with_scroll_fallback(["playwright"], {"INFINITE_SCROLL": True}) == [
        "playwright"
    ]


def test_explicit_playwright_still_valid():
    # Explicitly requesting playwright is still honored (legacy / JS opt-in).
    assert SmartExtractor(strategies=["playwright", "trafilatura"]).strategies == [
        "playwright",
        "trafilatura",
    ]
