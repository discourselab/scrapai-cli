"""Spider identity is (name, project), not name alone (docs/requests/28).

The schema allows one name in several projects (uq_spider_name_project), but
`spiders import`, `spiders delete` and the crawl-time config loaders looked a
spider up by name only. Importing a same-named spider into a second project
moved the first project's row over (items included) and rewrote its config,
and a crawl could load another project's row. These tests pin the scoped
behaviour against a real in-memory SQLite database, never the working DB.
"""

import json
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base, ScrapedItem, Spider, SpiderSetting
from spiders.database_spider import DatabaseSpider
from spiders.sitemap_spider import SitemapDatabaseSpider

pytestmark = pytest.mark.unit

DELAY = "DOWNLOAD_DELAY"


@pytest.fixture
def db(monkeypatch, tmp_path):
    """In-memory SQLite session wired into every get_db() the code under test
    uses, so nothing can reach the working database."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()

    @contextmanager
    def fake_get_db():
        yield session

    for target in (
        "core.db.get_db",
        "spiders.database_spider.get_db",
        "spiders.sitemap_spider.get_db",
    ):
        monkeypatch.setattr(target, fake_get_db)
    # No project.json under DATA_DIR, so import skips schema coverage.
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path))
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _add(db, project, name="example_org", delay="1"):
    spider = Spider(
        name=name,
        project=project,
        allowed_domains=["example.org"],
        start_urls=[f"https://example.org/{project}/"],
    )
    db.add(spider)
    db.flush()
    setting = SpiderSetting(spider_id=spider.id, key=DELAY, value=delay)
    db.add(setting)
    db.commit()
    return spider


def _import(tmp_path, project, delay=2):
    from cli.spiders import spiders

    cfg = tmp_path / "final_spider.json"
    cfg.write_text(
        json.dumps(
            {
                "name": "example_org",
                "allowed_domains": ["example.org"],
                "start_urls": [f"https://example.org/{project}/"],
                "source_url": "https://example.org/",
                "settings": {DELAY: delay},
            }
        )
    )
    args = ["import", str(cfg), "--project", project]
    return CliRunner().invoke(spiders, args, catch_exceptions=False)


def _delay(spider):
    return {s.key: s.value for s in spider.settings}[DELAY]


# --- spiders import ---------------------------------------------------------


def test_import_into_second_project_leaves_first_untouched(db, tmp_path):
    news = _add(db, "news")
    db.add(ScrapedItem(spider_id=news.id, url="https://example.org/a"))
    db.commit()

    res = _import(tmp_path, "proj")

    assert "imported successfully" in res.output, res.output
    assert "also exists in project(s) news" in res.output
    rows = db.query(Spider).filter(Spider.name == "example_org").all()
    assert sorted(r.project for r in rows) == ["news", "proj"]
    db.refresh(news)
    assert news.project == "news"  # not moved
    assert _delay(news) == "1"  # config not rewritten
    # items stay with their spider
    assert [i.url for i in news.items] == ["https://example.org/a"]


def test_reimport_into_same_project_updates_in_place(db, tmp_path):
    news = _add(db, "news")
    res = _import(tmp_path, "news", delay=3)

    assert "exists in project 'news'. Updating" in res.output, res.output
    assert db.query(Spider).count() == 1
    db.refresh(news)
    assert _delay(news) == "3.0"  # stored as validated (float)


# --- crawl-time config load -------------------------------------------------


def _load(cls, **kwargs):
    with patch.object(cls, "_load_settings_from_db"), patch.object(
        cls, "_setup_cloudflare_handlers"
    ):
        return cls(spider_name="example_org", **kwargs)


SPIDER_CLASSES = [DatabaseSpider, SitemapDatabaseSpider]


@pytest.mark.parametrize("cls", SPIDER_CLASSES)
def test_load_picks_the_row_of_the_given_project(db, cls):
    _add(db, "news")
    proj = _add(db, "proj")

    spider = _load(cls, project="proj")

    assert spider.spider_config.id == proj.id
    assert spider.spider_config.project == "proj"


@pytest.mark.parametrize("cls", SPIDER_CLASSES)
def test_scrapy_a_project_reaches_the_lookup(db, cls):
    """`scrapy crawl ... -a project=<p>` reaches __init__ via from_crawler."""
    from scrapy.utils.test import get_crawler

    _add(db, "news")
    proj = _add(db, "proj")

    # _apply_cf_to_crawler writes crawler settings; get_crawler() froze them.
    with patch.object(cls, "_apply_cf_to_crawler"):
        spider = cls.from_crawler(
            get_crawler(cls), spider_name="example_org", project="proj"
        )

    assert spider.project == "proj"
    assert spider.spider_config.id == proj.id


@pytest.mark.parametrize("cls", SPIDER_CLASSES)
def test_load_without_project_refuses_an_ambiguous_name(db, cls):
    _add(db, "news")
    _add(db, "proj")

    ambiguous = r"more than one project \(news, proj\)"
    with pytest.raises(ValueError, match=ambiguous):
        _load(cls)


@pytest.mark.parametrize("cls", SPIDER_CLASSES)
def test_load_without_project_still_resolves_a_unique_name(db, cls):
    news = _add(db, "news")

    assert _load(cls).spider_config.id == news.id


@pytest.mark.parametrize("cls", SPIDER_CLASSES)
def test_load_with_project_not_holding_the_name_fails(db, cls):
    _add(db, "news")

    with pytest.raises(ValueError, match="not found in database"):
        _load(cls, project="proj")


def test_crawl_command_passes_the_project_to_the_spider(db, monkeypatch):
    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    _add(db, "news")
    calls = []
    monkeypatch.setattr(
        crawl_mod.subprocess,
        "run",
        lambda cmd, *a, **k: calls.append(cmd) or Mock(returncode=0),
    )

    crawl_mod._run_spider("news", "example_org", limit=5)

    (cmd,) = calls
    i = cmd.index("project=news")
    assert cmd[i - 1] == "-a"
    assert "spider_name=example_org" in cmd


# --- spiders delete ---------------------------------------------------------


def _delete(*args):
    from cli.spiders import spiders

    args = ["delete", "example_org", "--force", *args]
    return CliRunner().invoke(spiders, args)


def test_delete_without_project_refuses_an_ambiguous_name(db):
    _add(db, "news")
    _add(db, "proj")

    res = _delete()

    assert "more than one project (news, proj)" in res.output
    assert db.query(Spider).count() == 2


def test_delete_with_project_removes_only_that_row(db):
    _add(db, "news")
    _add(db, "proj")

    res = _delete("--project", "proj")

    assert "deleted" in res.output, res.output
    assert [s.project for s in db.query(Spider).all()] == ["news"]


def test_delete_without_project_still_works_for_a_unique_name(db):
    _add(db, "news")

    res = _delete()

    assert "deleted" in res.output, res.output
    assert db.query(Spider).count() == 0
