"""`show` reads production crawls/*.jsonl by default (docs/requests/20).

The reader must mirror the DB branch's semantics: newest items first
(append-only files -> newest file first, lines bottom-up), case-insensitive
substring filters, hard limit.
"""

import json
import os

import pytest

from cli.show import _matches, _read_crawl_rows

pytestmark = pytest.mark.unit


def _write(path, rows, mtime):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def crawls(tmp_path):
    _write(
        tmp_path / "crawl_01072026.jsonl",
        [
            {"url": "https://x.com/old-1", "title": "Old one", "content": "alpha"},
            {"url": "https://x.com/old-2", "title": "Old two", "content": "beta"},
        ],
        mtime=1_000,
    )
    _write(
        tmp_path / "crawl_02072026_101500.jsonl",
        [
            {"url": "https://x.com/new-1", "title": "New one", "content": "gamma"},
            {"url": "https://x.com/new-2", "title": "New TWO", "content": "delta"},
        ],
        mtime=2_000,
    )
    return tmp_path


def test_newest_rows_first(crawls):
    rows, nfiles = _read_crawl_rows(crawls, limit=3)
    assert nfiles == 2
    # Newest file first, its lines bottom-up, then the older file.
    assert [r["url"].rsplit("/", 1)[1] for r in rows] == ["new-2", "new-1", "old-2"]


def test_limit_and_filters(crawls):
    rows, _ = _read_crawl_rows(crawls, limit=10, title="two")
    assert {r["title"] for r in rows} == {"Old two", "New TWO"}  # case-insensitive
    rows, _ = _read_crawl_rows(crawls, limit=1, text="alpha")
    assert rows[0]["url"] == "https://x.com/old-1"
    rows, _ = _read_crawl_rows(crawls, limit=10, url="/new-")
    assert len(rows) == 2


def test_garbage_lines_skipped(tmp_path):
    (tmp_path / "crawl_x.jsonl").write_text('not json\n{"url": "https://x.com/a"}\n')
    rows, _ = _read_crawl_rows(tmp_path, limit=5)
    assert [r["url"] for r in rows] == ["https://x.com/a"]


def test_matches_semantics():
    rec = {"url": "https://x.com/A", "title": "Solar Report", "content": "wind text"}
    assert _matches(rec, url="x.com", text=None, title=None)
    assert _matches(rec, url=None, text="WIND", title=None)  # content, any case
    assert _matches(rec, url=None, text="solar", title=None)  # or title
    assert not _matches(rec, url=None, text=None, title="wind")  # title only
