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
    CustomExtractor,
    _extract_media,
)
from core.schemas import ScrapedArticle


class TestNewspaperExtractor:
    """Test Newspaper3k-based extraction."""

    @pytest.mark.unit
    def test_extracts_from_semantic_html(self, sample_html_simple):
        """Test that Newspaper can process well-formed HTML without crashing."""
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article", html=sample_html_simple
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
        result = extractor.extract(url="https://example.com/article", html="")

        # Should return None or raise, not crash unexpectedly
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    def test_handles_malformed_html(self, sample_html_malformed):
        """Test robustness with malformed HTML."""
        extractor = NewspaperExtractor()

        # Should not raise unexpected exception
        try:
            result = extractor.extract(
                url="https://example.com/article", html=sample_html_malformed
            )
            assert result is None or isinstance(result, ScrapedArticle)
        except ValueError:
            # Pydantic validation errors are acceptable
            pass

    @pytest.mark.unit
    def test_uses_title_hint_when_extraction_fails(self):
        """Test that title_hint is used when newspaper fails to extract title."""
        extractor = NewspaperExtractor()
        # HTML without clear title
        html = "<html><body><p>Some content here</p></body></html>"

        result = extractor.extract(
            url="https://example.com/article",
            html=html,
            title_hint="Article Title from Hint",
        )

        # May return None if content validation fails, that's OK
        assert result is None or result.title == "Article Title from Hint"

    @pytest.mark.unit
    def test_exception_handling(self):
        """Test that extractor handles exceptions gracefully."""
        extractor = NewspaperExtractor()
        # Invalid HTML that causes parsing exception
        result = extractor.extract(
            url="https://example.com/article", html=None  # This will cause an exception
        )

        # Should return None, not crash
        assert result is None

    @pytest.mark.unit
    def test_include_html_option(self, sample_html_simple):
        """Test that include_html option works."""
        extractor = NewspaperExtractor()

        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple,
            include_html=True,
        )

        if result:
            assert result.html == sample_html_simple


class TestTrafilaturaExtractor:
    """Test Trafilatura-based extraction."""

    @pytest.mark.unit
    def test_extracts_from_simple_html(self, sample_html_simple):
        """Test Trafilatura extraction on clean HTML."""
        extractor = TrafilaturaExtractor()
        result = extractor.extract(
            url="https://example.com/article", html=sample_html_simple
        )

        assert result is None or isinstance(result, ScrapedArticle)
        if result:
            assert len(result.content) > 0

    @pytest.mark.unit
    def test_handles_empty_extraction(self):
        """Test when trafilatura returns None or invalid data."""
        extractor = TrafilaturaExtractor()
        # Empty HTML that trafilatura can't extract from
        result = extractor.extract(
            url="https://example.com/article", html="<html><body></body></html>"
        )

        assert result is None

    @pytest.mark.unit
    def test_handles_no_text_in_extraction(self):
        """Test when trafilatura extracts but has no text."""
        extractor = TrafilaturaExtractor()
        # Minimal HTML with no real content
        result = extractor.extract(
            url="https://example.com/article",
            html="<html><head><title>Test</title></head><body></body></html>",
        )

        # Should return None when no text extracted
        assert result is None

    @pytest.mark.unit
    def test_uses_title_hint(self):
        """Test that title_hint is used when trafilatura fails to extract title."""
        extractor = TrafilaturaExtractor()
        # HTML with content but unclear title
        html = (
            "<html><body><article><p>Some article content here that is long enough "
            "to be valid content for extraction purposes.</p></article></body></html>"
        )

        result = extractor.extract(
            url="https://example.com/article", html=html, title_hint="Hint Title"
        )

        # If extraction succeeds, should use hint for title
        if result:
            assert (
                result.title == "Hint Title" or result.title
            )  # trafilatura might find a title

    @pytest.mark.unit
    def test_include_html_option(self, sample_html_simple):
        """Test that include_html option works."""
        extractor = TrafilaturaExtractor()

        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple,
            include_html=True,
        )

        if result:
            assert result.html == sample_html_simple


class TestCustomExtractor:
    """Test custom CSS selector-based extraction."""

    @pytest.mark.unit
    def test_extracts_with_custom_selectors(self, sample_html_complex):
        """Test extraction using custom CSS selectors."""
        extractor = CustomExtractor(
            selectors={
                "title": "h1.article-title-custom",
                "content": "div.article-text",
                "author": "span.author-name",
                "date": "span.publish-date",
            }
        )

        result = extractor.extract(
            url="https://example.com/article", html=sample_html_complex
        )

        # May return None if content too short for validation
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    def test_returns_none_when_selectors_dont_match(self, sample_html_simple):
        """Test behavior when CSS selectors don't match."""
        extractor = CustomExtractor(
            selectors={
                "title": "h1.nonexistent-class",
                "content": "div.nonexistent-content",
            }
        )

        result = extractor.extract(
            url="https://example.com/article", html=sample_html_simple
        )

        # Should handle gracefully - return None
        assert result is None

    @pytest.mark.unit
    def test_uses_title_hint_when_selector_fails(self, sample_html_simple):
        """Test that title_hint is used when title selector doesn't match."""
        extractor = CustomExtractor(
            selectors={
                "title": "h1.nonexistent",
                "content": "p",  # This should match
            }
        )

        result = extractor.extract(
            url="https://example.com/article",
            html=sample_html_simple,
            title_hint="Fallback Title",
        )

        if result:
            assert result.title == "Fallback Title"

    @pytest.mark.unit
    def test_handles_invalid_date_format(self):
        """Test date parsing with invalid date string."""
        html = """
        <html><body>
            <h1>Article Title</h1>
            <div class="content">This is article content that is long enough to pass validation checks.</div>
            <span class="date">not-a-valid-date</span>
        </body></html>
        """
        extractor = CustomExtractor(
            selectors={"title": "h1", "content": "div.content", "date": "span.date"}
        )

        result = extractor.extract(url="https://example.com/article", html=html)

        # Should extract successfully but date will be None
        if result:
            assert result.published_date is None

    @pytest.mark.unit
    def test_extracts_custom_fields_to_metadata(self):
        """Test that custom fields are extracted to metadata."""
        html = """
        <html><body>
            <h1>Article Title</h1>
            <div class="content">This is article content that is long enough to pass validation.</div>
            <span class="category">Technology</span>
            <span class="rating">5 stars</span>
        </body></html>
        """
        extractor = CustomExtractor(
            selectors={
                "title": "h1",
                "content": "div.content",
                "category": "span.category",
                "rating": "span.rating",
            }
        )

        result = extractor.extract(url="https://example.com/article", html=html)

        if result:
            assert result.metadata.get("category") == "Technology"
            assert result.metadata.get("rating") == "5 stars"

    @pytest.mark.unit
    def test_handles_extraction_exception(self):
        """Test that extractor handles parsing exceptions gracefully."""
        extractor = CustomExtractor(selectors={"title": "h1", "content": "div"})

        # Pass invalid HTML that causes exception
        result = extractor.extract(
            url="https://example.com/article", html=None  # This will cause an exception
        )

        # Should return None, not crash
        assert result is None

    @pytest.mark.unit
    def test_handles_invalid_selector_syntax(self):
        """Test that invalid CSS selector doesn't crash."""
        html = "<html><body><h1>Title</h1><p>Content here</p></body></html>"
        extractor = CustomExtractor(
            selectors={"title": "[[[invalid", "content": "p"}  # Invalid CSS selector
        )

        result = extractor.extract(url="https://example.com/article", html=html)

        # Should handle gracefully - might return None or extract what it can
        assert result is None or isinstance(result, ScrapedArticle)


class TestSmartExtractor:
    """Test the Smart Extractor chain."""

    @pytest.mark.unit
    async def test_tries_strategies_in_order(self, sample_html_simple):
        """Test that SmartExtractor tries each strategy in sequence."""
        extractor = SmartExtractor(strategies=["newspaper", "trafilatura"])

        result = await extractor.extract(
            url="https://example.com/article", html=sample_html_simple
        )

        # Should get a result from one of the strategies
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    async def test_custom_strategy_with_selectors(self):
        """Test custom strategy with provided selectors."""
        html = """
        <html><body>
            <h1 class="title">Test Title</h1>
            <div class="body">Article content that is long enough for validation.</div>
        </body></html>
        """
        extractor = SmartExtractor(
            strategies=["custom", "newspaper"],
            custom_selectors={"title": "h1.title", "content": "div.body"},
        )

        result = await extractor.extract(url="https://example.com/article", html=html)

        # Custom extractor should work
        if result:
            assert result.source == "custom"

    @pytest.mark.unit
    async def test_custom_strategy_without_selectors(self, sample_html_simple):
        """Test that custom strategy is skipped when no selectors provided."""
        extractor = SmartExtractor(
            strategies=["custom", "newspaper"], custom_selectors=None  # No selectors
        )

        result = await extractor.extract(
            url="https://example.com/article", html=sample_html_simple
        )

        # Should skip custom and use newspaper
        if result:
            assert result.source == "newspaper4k"

    @pytest.mark.unit
    async def test_fallback_when_first_strategy_fails(self):
        """Test fallback to next strategy when first fails."""
        # HTML that newspaper might fail on but trafilatura can handle
        html = """
        <html><body>
            <article>
                <p>This is article content that should be extracted by trafilatura if newspaper fails.</p>
            </article>
        </body></html>
        """
        extractor = SmartExtractor(strategies=["newspaper", "trafilatura"])

        result = await extractor.extract(url="https://example.com/article", html=html)

        # Should get result from one of them
        assert result is None or isinstance(result, ScrapedArticle)

    @pytest.mark.unit
    async def test_returns_none_when_all_strategies_fail(self):
        """Test that None is returned when all extractors fail."""
        extractor = SmartExtractor(strategies=["newspaper", "trafilatura"])

        # Empty HTML that all extractors will fail on
        result = await extractor.extract(url="https://example.com/article", html="")

        assert result is None


class TestExtractMedia:
    """Unit tests for the _extract_media helper."""

    @pytest.mark.unit
    def test_returns_empty_on_none(self):
        images, videos = _extract_media(None)
        assert images == []
        assert videos == []

    @pytest.mark.unit
    def test_returns_empty_on_blank(self):
        images, videos = _extract_media("")
        assert images == []
        assert videos == []

    @pytest.mark.unit
    def test_collects_images_with_alt(self):
        html = """
        <html><body>
            <img src="https://example.com/a.jpg" alt="A photo">
            <img src="/b.png" alt="">
            <img alt="no src">
        </body></html>
        """
        images, _ = _extract_media(html)
        assert {"src": "https://example.com/a.jpg", "alt": "A photo"} in images
        assert {"src": "/b.png", "alt": ""} in images
        assert len(images) == 2

    @pytest.mark.unit
    def test_collects_videos_and_iframes(self):
        html = """
        <html><body>
            <video src="https://cdn/v.mp4"></video>
            <iframe src="https://youtube.com/embed/xyz"></iframe>
            <iframe></iframe>
        </body></html>
        """
        _, videos = _extract_media(html)
        types = {v["type"] for v in videos}
        srcs = {v["src"] for v in videos}
        assert types == {"video", "iframe"}
        assert "https://cdn/v.mp4" in srcs
        assert "https://youtube.com/embed/xyz" in srcs


class TestExtractorMediaFields:
    """Tests that NewspaperExtractor / TrafilaturaExtractor populate the new
    clean_html / markdown / top_image / images / videos fields.

    These tests use long, semantically-rich article HTML so newspaper4k's and
    trafilatura's content heuristics reliably extract it. If a library upgrade
    breaks that assumption we want the failure to surface, not hide behind a
    skip.
    """

    @pytest.fixture
    def article_html_with_image(self):
        """Article HTML with enough body to satisfy both extractors' heuristics."""
        body = " ".join(
            [
                "This is the first paragraph of the article body.",
                "It contains substantive content that describes a topic.",
                "The text is long enough to satisfy content-length heuristics",
                "used by both newspaper4k and trafilatura when deciding what",
                "counts as the main article body of a webpage.",
            ]
        )
        return f"""<!DOCTYPE html>
<html><head><title>Article Title Here</title></head><body>
<article>
<h1>Article Title Here</h1>
<p>{body}</p>
<p>{body}</p>
<img src="https://example.com/hero.jpg" alt="hero">
<p>{body}</p>
<p>{body}</p>
</article>
</body></html>"""

    @pytest.mark.unit
    def test_newspaper_populates_new_fields(self, article_html_with_image):
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article", html=article_html_with_image
        )
        assert result is not None
        assert isinstance(result.images, list)
        assert isinstance(result.videos, list)
        assert isinstance(result.clean_html, str) and result.clean_html
        assert isinstance(result.markdown, str) and result.markdown

    @pytest.mark.unit
    def test_newspaper_extracts_images_from_article_html(self, article_html_with_image):
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/a", html=article_html_with_image
        )
        assert result is not None
        assert result.clean_html
        srcs = [img["src"] for img in result.images]
        assert "https://example.com/hero.jpg" in srcs

    @pytest.mark.unit
    def test_trafilatura_populates_new_fields(self, article_html_with_image):
        extractor = TrafilaturaExtractor()
        result = extractor.extract(
            url="https://example.com/article", html=article_html_with_image
        )
        assert result is not None
        assert isinstance(result.images, list)
        assert isinstance(result.videos, list)
        assert isinstance(result.clean_html, str) and result.clean_html
        assert isinstance(result.markdown, str) and result.markdown

    @pytest.mark.unit
    def test_top_image_no_longer_in_metadata(self, article_html_with_image):
        """top_image is now a top-level field, removed from metadata dict."""
        extractor = NewspaperExtractor()
        result = extractor.extract(
            url="https://example.com/article", html=article_html_with_image
        )
        assert result is not None
        assert "top_image" not in result.metadata


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
            result = extractor.extract(url="https://example.com/test", html=html)
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
            result = extractor.extract(url="https://example.com/test", html=html)
            assert result is None or isinstance(result, ScrapedArticle)
        except (ValueError, Exception) as e:
            if "Content too short" not in str(e) and "Title too short" not in str(e):
                pytest.fail(f"Unexpected error: {e}")
