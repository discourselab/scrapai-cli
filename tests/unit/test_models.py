"""
Unit tests for SQLAlchemy schema constraints.

Guards against regressions in the unique constraints that scope:
- Spider names per project (``uq_spider_name_project``)
- Scraped item URLs per spider (``uq_item_spider_url``)
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.models import Spider, ScrapedItem


@pytest.fixture
def session():
    """Fresh in-memory SQLite session per test."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _make_spider(name, project="default"):
    return Spider(
        name=name,
        project=project,
        allowed_domains=["example.com"],
        start_urls=["https://example.com/"],
    )


class TestSpiderUniqueness:
    @pytest.mark.unit
    def test_same_name_different_projects_succeeds(self, session):
        """Same spider name is allowed across different projects."""
        session.add(_make_spider("my_spider", project="proj_a"))
        session.add(_make_spider("my_spider", project="proj_b"))
        session.commit()

        assert session.query(Spider).filter_by(name="my_spider").count() == 2

    @pytest.mark.unit
    def test_same_name_same_project_fails(self, session):
        """Duplicate (name, project) must raise IntegrityError."""
        session.add(_make_spider("dupe_spider", project="proj_a"))
        session.commit()

        session.add(_make_spider("dupe_spider", project="proj_a"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestScrapedItemUniqueness:
    @pytest.mark.unit
    def test_same_url_different_spiders_succeeds(self, session):
        """Same URL across different spider_id values is allowed."""
        s1 = _make_spider("s1", project="p")
        s2 = _make_spider("s2", project="p")
        session.add_all([s1, s2])
        session.commit()

        url = "https://example.com/article"
        session.add(ScrapedItem(spider_id=s1.id, url=url, title="A"))
        session.add(ScrapedItem(spider_id=s2.id, url=url, title="B"))
        session.commit()

        assert session.query(ScrapedItem).filter_by(url=url).count() == 2

    @pytest.mark.unit
    def test_same_url_same_spider_fails(self, session):
        """Duplicate (spider_id, url) must raise IntegrityError."""
        s1 = _make_spider("s1", project="p")
        session.add(s1)
        session.commit()

        url = "https://example.com/article"
        session.add(ScrapedItem(spider_id=s1.id, url=url, title="A"))
        session.commit()

        session.add(ScrapedItem(spider_id=s1.id, url=url, title="B"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
