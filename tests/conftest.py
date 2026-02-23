"""
Pytest configuration and shared fixtures for ScrapAI CLI tests.

This module provides:
- Database fixtures (temporary SQLite DB for testing)
- Spider configuration fixtures
- Sample HTML content fixtures
- Mock browser clients
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from core.models import Base, Spider, ScrapedItem, SpiderRule, SpiderSetting


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="function")
def temp_db() -> Generator[Session, None, None]:
    """
    Create a temporary SQLite database for testing.

    Yields:
        SQLAlchemy Session connected to temporary database

    Usage:
        def test_spider_creation(temp_db):
            spider = Spider(name="test", project_id=1)
            temp_db.add(spider)
            temp_db.commit()
            assert spider.id is not None
    """
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}")

    # Create all tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        os.close(db_fd)
        os.unlink(db_path)


@pytest.fixture(scope="function")
def sample_project_name() -> str:
    """
    Return a sample project name for testing.

    Usage:
        def test_spider_in_project(sample_project_name):
            spider = Spider(name="test", project=sample_project_name)
    """
    return "test_project"


@pytest.fixture(scope="function")
def sample_spider_config(sample_project_name: str) -> dict:
    """
    Return a valid spider configuration for testing.

    Returns:
        dict: Spider configuration with all required fields

    Usage:
        def test_spider_import(sample_spider_config):
            spider = Spider(**sample_spider_config)
            assert spider.name == "test_spider"
    """
    return {
        "name": "test_spider",
        "project": sample_project_name,
        "allowed_domains": ["example.com"],
        "start_urls": ["https://example.com/"],
    }


@pytest.fixture(scope="session")
def sample_html_simple() -> str:
    """
    Simple, well-formed HTML article for testing extractors.

    Contains semantic HTML with <article>, <h1>, <time>, etc.
    """
    return """<!DOCTYPE html>
<html>
<head>
    <title>Test Article - Example Site</title>
    <meta property="og:title" content="Test Article">
    <meta property="og:description" content="This is a test article description">
</head>
<body>
    <article>
        <header>
            <h1>Test Article Title</h1>
            <p class="byline">
                By <span class="author">John Doe</span>
                <time datetime="2026-02-22">February 22, 2026</time>
            </p>
        </header>
        <div class="content">
            <p>This is the first paragraph of the article content. It contains important information.</p>
            <p>This is the second paragraph with more details about the topic being discussed.</p>
            <p>The article continues with a third paragraph providing additional context.</p>
        </div>
    </article>
</body>
</html>"""


@pytest.fixture(scope="session")
def sample_html_complex() -> str:
    """
    Complex HTML with custom classes requiring custom selectors.

    No semantic HTML - requires CSS selectors to extract content.
    """
    return """<!DOCTYPE html>
<html>
<head>
    <title>Complex Article Example</title>
</head>
<body>
    <div class="container">
        <div class="header-section">
            <h1 class="article-title-custom">Complex Article Title</h1>
            <div class="meta-info">
                <span class="author-name">Jane Smith</span>
                <span class="publish-date">2026-02-22</span>
            </div>
        </div>
        <div class="body-section">
            <div class="article-text">
                <div class="paragraph">First paragraph of complex article.</div>
                <div class="paragraph">Second paragraph with more information.</div>
                <div class="paragraph">Third paragraph concluding the article.</div>
            </div>
        </div>
        <!-- Sidebar with ads and navigation -->
        <div class="sidebar">
            <div class="ad">Advertisement content</div>
            <div class="navigation">Related links</div>
        </div>
    </div>
</body>
</html>"""


@pytest.fixture(scope="session")
def sample_html_malformed() -> str:
    """
    Malformed HTML for robustness testing.

    Tests that extractors don't crash on bad HTML.
    """
    return """<html>
<head><title>Broken HTML
<body>
<h1>Missing closing tags
<p>Unclosed paragraph
<div>Nested without closing
<span>More broken content
"""


@pytest.fixture
def mock_scrapy_response(mocker):
    """
    Create a mock Scrapy Response object.

    Usage:
        def test_spider_parse(mock_scrapy_response):
            response = mock_scrapy_response(
                url="https://example.com/article",
                html="<html>...</html>"
            )
            spider = DatabaseSpider()
            results = list(spider.parse(response))
    """

    def _make_response(url: str, html: str):
        response = mocker.Mock()
        response.url = url
        response.text = html
        response.body = html.encode("utf-8")
        response.status = 200
        return response

    return _make_response


@pytest.fixture
def mock_browser_client(mocker):
    """
    Mock browser automation client (Playwright/nodriver).

    Prevents actual browser launches during tests.

    Usage:
        def test_cloudflare_bypass(mock_browser_client):
            client = mock_browser_client()
            cookies = await client.get_cookies()
            assert cookies is not None
    """
    client = mocker.Mock()
    client.get_cookies = mocker.AsyncMock(return_value={"cf_clearance": "test_token"})
    client.fetch_page = mocker.AsyncMock(return_value="<html>Mocked page</html>")
    client.close = mocker.AsyncMock()
    return client


@pytest.fixture(scope="function")
def temp_data_dir(tmp_path: Path) -> Path:
    """
    Create temporary data directory for test outputs.

    Returns:
        Path: Temporary directory that will be cleaned up after test

    Usage:
        def test_crawl_output(temp_data_dir):
            output_file = temp_data_dir / "crawl_output.jsonl"
            # Write test output
            assert output_file.exists()
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    """
    Reset global configuration between tests.

    Prevents test pollution from environment variables or config changes.
    """
    # Store original env vars
    import core.config as config_module

    original_data_dir = config_module.DATA_DIR
    original_log_level = config_module.LOG_LEVEL

    yield

    # Restore original values
    config_module.DATA_DIR = original_data_dir
    config_module.LOG_LEVEL = original_log_level
