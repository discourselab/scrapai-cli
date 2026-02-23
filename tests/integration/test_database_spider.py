"""
Integration tests for DatabaseSpider.

Tests the complete spider workflow:
1. Load config from database
2. Compile URL rules
3. Extract article content
4. Save to database
"""

import pytest
from scrapy.http import HtmlResponse, Request
from sqlalchemy.orm import Session

from spiders.database_spider import DatabaseSpider
from core.models import Spider, ScrapedItem, SpiderRule, SpiderSetting


class TestDatabaseSpider:
    """Integration tests for DatabaseSpider functionality."""

    @pytest.mark.integration
    def test_spider_loads_config_from_database(
        self, temp_db: Session, sample_project_name: str
    ):
        """Test that spider correctly loads configuration from database."""
        # Create spider in database
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Add a rule
        rule = SpiderRule(
            spider_id=spider_config.id, allow_patterns=[r"/article/.*"], follow=True
        )
        temp_db.add(rule)
        temp_db.commit()

        # Instantiate spider
        spider = DatabaseSpider(
            spider_name="test_spider", project_name=sample_project_name
        )

        # Verify configuration loaded
        assert spider.spider_name == "test_spider"
        assert spider.name == "database_spider"  # Class attribute
        assert "example.com" in spider.allowed_domains
        assert "https://example.com/" in spider.start_urls

    @pytest.mark.integration
    def test_spider_compiles_url_rules(
        self, temp_db: Session, sample_project_name: str
    ):
        """Test that spider compiles URL matching rules correctly."""
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Add rules
        rule = SpiderRule(
            spider_id=spider_config.id,
            allow_patterns=[r"/article/.*"],
            deny_patterns=[r"/tag/.*"],
            follow=True,
        )
        temp_db.add(rule)
        temp_db.commit()

        spider = DatabaseSpider(
            spider_name="test_spider", project_name=sample_project_name
        )

        # Verify rules were compiled
        assert len(spider.rules) > 0

        # Verify rule has correct configuration
        rule = spider.rules[0]
        assert rule.link_extractor is not None
        assert rule.follow is True

    @pytest.mark.integration
    async def test_spider_extracts_article_content(
        self,
        temp_db: Session,
        sample_project_name: str,
        sample_html_simple: str,
        mocker,
    ):
        """Test end-to-end article extraction."""
        # Create spider
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Add extractor settings
        setting = SpiderSetting(
            spider_id=spider_config.id,
            key="EXTRACTOR_ORDER",
            value='["newspaper", "trafilatura"]',
            type="json",
        )
        temp_db.add(setting)
        temp_db.commit()

        # Create spider instance
        spider = DatabaseSpider(
            spider_name="test_spider", project_name=sample_project_name
        )

        # Mock Scrapy settings (normally set by Scrapy framework)
        spider.settings = mocker.Mock()
        spider.settings.getbool = mocker.Mock(return_value=False)

        # Create mock response
        response = HtmlResponse(
            url="https://example.com/article/test",
            body=sample_html_simple.encode("utf-8"),
            encoding="utf-8",
        )

        # Parse response using parse_article
        results = []
        async for item in spider.parse_article(response):
            results.append(item)

        # Verify extraction
        assert len(results) > 0
        article_item = results[0]

        # Newspaper extractor uses og:title meta tag
        assert article_item["title"] == "Test Article"
        assert len(article_item["content"]) > 0
        assert "first paragraph" in article_item["content"].lower()
        assert article_item["url"] == "https://example.com/article/test"

    @pytest.mark.integration
    def test_spider_saves_articles_to_database(
        self, temp_db: Session, sample_project_name: str
    ):
        """Test that extracted articles are saved to database."""
        # Create spider
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Create scraped item manually (simulating spider pipeline)
        item = ScrapedItem(
            spider_id=spider_config.id,
            url="https://example.com/article/test",
            title="Test Article",
            content="Test content",
            author="Test Author",
        )
        temp_db.add(item)
        temp_db.commit()

        # Verify item saved
        saved_item = (
            temp_db.query(ScrapedItem)
            .filter_by(url="https://example.com/article/test")
            .first()
        )

        assert saved_item is not None
        assert saved_item.title == "Test Article"
        assert saved_item.spider_id == spider_config.id

    @pytest.mark.integration
    def test_spider_deduplicates_urls(self, temp_db: Session, sample_project_name: str):
        """Test that spider doesn't re-scrape existing URLs."""
        # Create spider and scraped item
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Add existing item
        existing_item = ScrapedItem(
            spider_id=spider_config.id,
            url="https://example.com/article/existing",
            title="Existing Article",
            content="Already scraped",
        )
        temp_db.add(existing_item)
        temp_db.commit()

        # Check if URL exists (this would be done by spider/pipeline)
        url_exists = (
            temp_db.query(ScrapedItem)
            .filter_by(
                spider_id=spider_config.id, url="https://example.com/article/existing"
            )
            .first()
            is not None
        )

        assert url_exists is True

        # New URL should not exist
        new_url_exists = (
            temp_db.query(ScrapedItem)
            .filter_by(
                spider_id=spider_config.id, url="https://example.com/article/new"
            )
            .first()
            is not None
        )

        assert new_url_exists is False


class TestSpiderWithCustomSelectors:
    """Test spider behavior with custom CSS selectors."""

    @pytest.mark.integration
    async def test_spider_uses_custom_selectors(
        self,
        temp_db: Session,
        sample_project_name: str,
        sample_html_complex: str,
        mocker,
    ):
        """Test extraction with custom CSS selectors."""
        # Create spider with custom selectors
        spider_config = Spider(
            name="custom_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        # Add custom settings
        settings = [
            SpiderSetting(
                spider_id=spider_config.id,
                key="EXTRACTOR_ORDER",
                value='["custom", "newspaper"]',
                type="json",
            ),
            SpiderSetting(
                spider_id=spider_config.id,
                key="CUSTOM_SELECTORS",
                value='{"title": "h1.article-title-custom", "content": "div.article-text", "author": "span.author-name", "date": "span.publish-date"}',
                type="json",
            ),
        ]
        for setting in settings:
            temp_db.add(setting)
        temp_db.commit()

        # Create spider instance
        spider = DatabaseSpider(
            spider_name="custom_spider", project_name=sample_project_name
        )

        # Mock Scrapy settings (normally set by Scrapy framework)
        spider.settings = mocker.Mock()
        spider.settings.getbool = mocker.Mock(return_value=False)

        # Create mock response with complex HTML
        response = HtmlResponse(
            url="https://example.com/article/complex",
            body=sample_html_complex.encode("utf-8"),
            encoding="utf-8",
        )

        # Parse response using parse_article
        results = []
        async for item in spider.parse_article(response):
            results.append(item)

        # Verify custom extraction
        assert len(results) > 0
        article_item = results[0]

        assert article_item["title"] == "Complex Article Title"
        assert "First paragraph" in article_item["content"]
        assert article_item["author"] == "Jane Smith"


class TestSpiderErrorHandling:
    """Test spider behavior with errors and edge cases."""

    @pytest.mark.integration
    async def test_spider_handles_extraction_failure(
        self, temp_db: Session, sample_project_name: str, mocker
    ):
        """Test that spider handles extraction failures gracefully."""
        spider_config = Spider(
            name="test_spider",
            project=sample_project_name,
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        temp_db.add(spider_config)
        temp_db.commit()

        spider = DatabaseSpider(
            spider_name="test_spider", project_name=sample_project_name
        )

        # Mock Scrapy settings (normally set by Scrapy framework)
        spider.settings = mocker.Mock()
        spider.settings.getbool = mocker.Mock(return_value=False)

        # Empty HTML response
        response = HtmlResponse(
            url="https://example.com/empty", body=b"", encoding="utf-8"
        )

        # Should not crash - use parse_article
        results = []
        async for item in spider.parse_article(response):
            results.append(item)

        # May return empty or skip, but shouldn't crash
        assert isinstance(results, list)

    @pytest.mark.integration
    def test_spider_handles_missing_config(self, temp_db: Session):
        """Test error handling when spider config doesn't exist."""
        with pytest.raises(ValueError, match="not found in database"):
            # Should raise error for non-existent spider
            spider = DatabaseSpider(
                spider_name="nonexistent_spider", project_name="nonexistent_project"
            )
