"""
Unit tests for ``core.db.get_db`` context manager semantics.

``get_db`` must:
- Yield a usable session on success.
- Roll back on exception so partial writes are NOT persisted.
- Always close the session.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.db as core_db
from core.db import get_db, Base
from core.models import Spider


@pytest.fixture
def in_memory_db(monkeypatch):
    """Point core.db.SessionLocal at a fresh in-memory SQLite for each test.

    Uses a single shared connection so the in-memory DB is visible across
    sessions opened during the test.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(core_db, "SessionLocal", TestSession)

    yield engine

    engine.dispose()


class TestGetDbSuccess:
    @pytest.mark.unit
    def test_yields_working_session(self, in_memory_db):
        """A successful with-block commits and the row is queryable afterward."""
        with get_db() as db:
            db.add(
                Spider(
                    name="ok_spider",
                    project="p",
                    allowed_domains=["x.com"],
                    start_urls=["https://x.com"],
                )
            )
            db.commit()

        with get_db() as db:
            assert db.query(Spider).filter_by(name="ok_spider").count() == 1


class TestGetDbRollback:
    @pytest.mark.unit
    def test_rollback_on_exception(self, in_memory_db):
        """If the with-block raises, uncommitted writes must NOT persist."""

        class BoomError(RuntimeError):
            pass

        with pytest.raises(BoomError):
            with get_db() as db:
                db.add(
                    Spider(
                        name="will_be_lost",
                        project="p",
                        allowed_domains=["x.com"],
                        start_urls=["https://x.com"],
                    )
                )
                db.flush()  # send INSERT to the DB but don't commit
                raise BoomError("kaboom")

        # The exception should have triggered a rollback — row must be gone.
        with get_db() as db:
            assert db.query(Spider).filter_by(name="will_be_lost").count() == 0

    @pytest.mark.unit
    def test_rollback_preserves_prior_committed_data(self, in_memory_db):
        """A failed transaction shouldn't undo previously-committed rows."""
        with get_db() as db:
            db.add(
                Spider(
                    name="kept",
                    project="p",
                    allowed_domains=["x.com"],
                    start_urls=["https://x.com"],
                )
            )
            db.commit()

        class BoomError(RuntimeError):
            pass

        with pytest.raises(BoomError):
            with get_db() as db:
                db.add(
                    Spider(
                        name="lost",
                        project="p",
                        allowed_domains=["y.com"],
                        start_urls=["https://y.com"],
                    )
                )
                db.flush()
                raise BoomError("nope")

        with get_db() as db:
            assert db.query(Spider).filter_by(name="kept").count() == 1
            assert db.query(Spider).filter_by(name="lost").count() == 0
