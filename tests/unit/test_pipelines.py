"""
Unit tests for ``DatabasePipeline._flush``.

Covers two recently-fixed behaviors:
1. Per-spider URL deduplication — the same URL across different spiders is
   NOT a duplicate (scraped_items.spider_id is part of the unique key).
2. Per-row fallback on bulk-insert failure — a single bad row in a batch
   must not drop the rest of the batch.
"""

import logging
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.db as core_db
from core.db import Base
from core.models import Spider, ScrapedItem
from pipelines import DatabasePipeline


@pytest.fixture
def pipeline_db(monkeypatch):
    """Patch core.db.SessionLocal to a fresh in-memory DB and return a session.

    DatabasePipeline.__init__ calls SessionLocal() at construction time, so
    the patch must happen BEFORE the pipeline is constructed.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(core_db, "SessionLocal", TestSession)

    # Inspector session for assertions, separate from the pipeline's session
    inspect = TestSession()
    try:
        yield inspect, TestSession
    finally:
        inspect.close()
        engine.dispose()


def _seed_spiders(session, *names):
    """Insert Spider rows and return their ids in the order given."""
    spiders = []
    for name in names:
        sp = Spider(
            name=name,
            project="p",
            allowed_domains=["example.com"],
            start_urls=["https://example.com/"],
        )
        session.add(sp)
        spiders.append(sp)
    session.commit()
    return [sp.id for sp in spiders]


def _item(spider_id, url, title="t", content="c"):
    return {
        "spider_id": spider_id,
        "url": url,
        "title": title,
        "content": content,
        "author": None,
        "published_date": None,
        "metadata": None,
    }


class _FakeSpider:
    """Minimal stand-in for a Scrapy Spider — only ``logger`` is used."""

    def __init__(self):
        self.logger = logging.getLogger("test.fake_spider")


class TestPerSpiderDedup:
    @pytest.mark.unit
    def test_same_url_different_spider_is_inserted(self, pipeline_db):
        """A URL already stored under spider_id=1 must NOT block spider_id=2."""
        inspect, _ = pipeline_db
        sid1, sid2 = _seed_spiders(inspect, "spider_one", "spider_two")

        # Pre-existing item under spider 1
        inspect.add(
            ScrapedItem(spider_id=sid1, url="https://example.com/a", title="orig")
        )
        inspect.commit()

        pipe = DatabasePipeline()
        pipe.buffer = [_item(sid2, "https://example.com/a", title="new")]
        pipe._flush(_FakeSpider())

        # Both rows should now exist
        rows = (
            inspect.query(ScrapedItem)
            .filter(ScrapedItem.url == "https://example.com/a")
            .order_by(ScrapedItem.spider_id)
            .all()
        )
        assert len(rows) == 2
        assert {r.spider_id for r in rows} == {sid1, sid2}

    @pytest.mark.unit
    def test_same_url_same_spider_is_skipped(self, pipeline_db):
        """A URL already stored under spider_id=1 must be skipped for spider_id=1."""
        inspect, _ = pipeline_db
        (sid1,) = _seed_spiders(inspect, "spider_one")

        inspect.add(
            ScrapedItem(spider_id=sid1, url="https://example.com/a", title="orig")
        )
        inspect.commit()

        pipe = DatabasePipeline()
        pipe.buffer = [_item(sid1, "https://example.com/a", title="dup")]
        pipe._flush(_FakeSpider())

        # Should remain a single row, with the original title.
        rows = (
            inspect.query(ScrapedItem)
            .filter(ScrapedItem.url == "https://example.com/a")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].title == "orig"


class TestPerRowQuarantineFallback:
    @pytest.mark.unit
    def test_bad_row_does_not_drop_rest_of_batch(self, pipeline_db):
        """If one of N items in the batch fails, the others must still land.

        The pipeline's pre-flush dedup query checks the DB BEFORE the batch
        runs — so if a duplicate row appears between the dedup query and the
        commit (race), or if any other constraint trips on commit, the bulk
        ``add_all`` will fail. The fallback path should then commit the good
        rows individually.

        We force this by using ``session.expunge_all()`` + a manual insert
        of a duplicate AFTER the pipeline's dedup query has already happened.
        Easiest reliable way: put two items in the batch that BOTH have the
        same (spider_id, url) — the in-batch ``seen_in_batch`` set catches
        consecutive dups, so we mix in another row whose duplicate has been
        pre-inserted *bypassing* the cache — by patching the dedup query to
        return an empty set.
        """
        inspect, _ = pipeline_db
        (sid,) = _seed_spiders(inspect, "spider_one")

        # Pre-insert a row that will collide with item #2 in our batch.
        inspect.add(
            ScrapedItem(spider_id=sid, url="https://example.com/dup", title="orig")
        )
        inspect.commit()

        pipe = DatabasePipeline()

        # Force the dedup query to return no matches so the duplicate slips
        # past the pre-check and only fails at commit time. This exercises
        # the per-row fallback (add_all -> rollback -> add+commit per row).
        original_query = pipe.db.query

        def stub_query(*args, **kwargs):
            q = original_query(*args, **kwargs)
            # Only neutralize the dedup query (selecting ScrapedItem.url).
            arg_strs = [str(a) for a in args]
            if any("scraped_items.url" in s for s in arg_strs):

                class _EmptyQuery:
                    def filter(self, *a, **kw):
                        return self

                    def all(self):
                        return []

                return _EmptyQuery()
            return q

        pipe.db.query = stub_query  # type: ignore[assignment]

        pipe.buffer = [
            _item(sid, "https://example.com/a", title="good-1"),
            _item(sid, "https://example.com/dup", title="bad-collides"),
            _item(sid, "https://example.com/b", title="good-2"),
        ]
        pipe._flush(_FakeSpider())

        urls = {
            r.url
            for r in inspect.query(ScrapedItem).filter(ScrapedItem.spider_id == sid)
        }
        # Both good rows must have landed despite the collision in the middle.
        assert "https://example.com/a" in urls
        assert "https://example.com/b" in urls
        # The duplicate URL still has exactly one row (the original).
        dup_rows = (
            inspect.query(ScrapedItem)
            .filter(ScrapedItem.url == "https://example.com/dup")
            .all()
        )
        assert len(dup_rows) == 1
        assert dup_rows[0].title == "orig"
