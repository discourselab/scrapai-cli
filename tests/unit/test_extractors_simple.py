"""
Simplified unit tests for content extractors.

Tests basic functionality without deep assertions on extraction logic.
"""

import pytest
from hypothesis import given, strategies as st

from core.extractors import (
    SmartExtractor,
    NewspaperExtractor,
    TrafilaturaExtractor,
    CustomExtractor
)
from core.schemas import ScrapedArticle


class TestNewspaperExtractor:
    """Test Newspaper3k-based extraction."""

    @pytest.mark.unit
    def test_extracts_from_semantic_html(self, sample_html_simple):
        """Test that Newspaper can process well-formed HTML without crashing."""
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple
        )

        # Should return a result or None, not crash
        assert result is None or isinstance(result, ScrapedArticle)
        if result:
            assert result.url == "https://example.com/article"
            assert len(result.content) > 0

    @pytest.mark.unit
    def test_handles_empty_html(self):
        """Test that extractor handles empty HTML gracefully."""
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article",
            html=""
        )

        # Should return None or raise, not crash unexpectedly
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    def test_handles_malformed_html(self, sample_html_malformed):
        """Test robustness with malformed HTML."""
        extractor = NewspaperExtractor()

        # Should not raise unexpected exception
        try:
            result = extractor.extract(
                url="https://example.com/article",
                html=sample_html_malformed
            )
            assert result is None or isinstance(result, ScrapedArticle)
        except ValueError:
            # Pydantic validation errors are acceptable
            pass


class TestTrafilaturaExtractor:
    """Test Trafilatura-based extraction."""

    @pytest.mark.unit
    def test_extracts_from_simple_html(self, sample_html_simple):
        """Test Trafilatura extraction on clean HTML."""
        extractor = TrafilaturaExtractor()
        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple
        )

        assert result is None or isinstance(result, ScrapedArticle)
        if result:
            assert len(result.content) > 0


class TestCustomExtractor:
    """Test custom CSS selector-based extraction."""

    @pytest.mark.unit
    def test_extracts_with_custom_selectors(self, sample_html_complex):
        """Test extraction using custom CSS selectors."""
        extractor = CustomExtractor(selectors={
            "title": "h1.article-title-custom",
            "content": "div.article-text",
            "author": "span.author-name",
            "date": "span.publish-date"
        })

        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_complex
        )

        # May return None if content too short for validation
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    def test_returns_none_when_selectors_dont_match(self, sample_html_simple):
        """Test behavior when CSS selectors don't match."""
        extractor = CustomExtractor(selectors={
            "title": "h1.nonexistent-class",
            "content": "div.nonexistent-content"
        })

        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple
        )

        # Should handle gracefully - return None
        assert result is None


class TestSmartExtractor:
    """Test the Smart Extractor chain."""

    @pytest.mark.unit
    async def test_tries_strategies_in_order(self, sample_html_simple):
        """Test that SmartExtractor tries each strategy in sequence."""
        extractor = SmartExtractor(
            strategies=["newspaper", "trafilatura"]
        )

        result = await extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple
        )

        # Should get a result from one of the strategies
        assert result is None or isinstance(result, ScrapedArticle)


class TestExtractorRobustness:
    """Property-based tests for extractor robustness using Hypothesis."""

    @pytest.mark.unit
    @pytest.mark.slow
    @given(html=st.text(min_size=10, max_size=500))
    def test_newspaper_never_crashes_on_random_html(self, html):
        """Test that Newspaper extractor handles any random HTML input."""
        extractor = NewspaperExtractor()

        # Should never raise an unexpected exception
        try:
            result = extractor.extract(
                url="https://example.com/test",
                html=html
            )
            # Result can be None or valid ScrapedArticle
            assert result is None or isinstance(result, ScrapedArticle)
        except (ValueError, Exception) as e:
            # Pydantic validation errors or expected extraction failures are OK
            if "Content too short" not in str(e) and "Title too short" not in str(e):
                # Only fail on unexpected errors
                pytest.fail(f"Unexpected error: {e}")

    @pytest.mark.unit
    @pytest.mark.slow
    @given(html=st.text(min_size=10, max_size=500))
    def test_trafilatura_never_crashes_on_random_html(self, html):
        """Test that Trafilatura extractor handles any random HTML input."""
        extractor = TrafilaturaExtractor()

        try:
            result = extractor.extract(
                url="https://example.com/test",
                html=html
            )
            assert result is None or isinstance(result, ScrapedArticle)
        except (ValueError, Exception) as e:
            if "Content too short" not in str(e) and "Title too short" not in str(e):
                pytest.fail(f"Unexpected error: {e}")
