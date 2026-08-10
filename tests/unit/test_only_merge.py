"""Unit tests for the --only merge: a narrowed audit/overview run recomputes only
the named spiders' rows and carries every other spider's row over unchanged from
the previous run's stored output (crawl_audit.csv / overview_rows.json), so the
project-wide report never shrinks to the --only subset.
"""

import json
import os

import pytest

from core.quality.crawl_audit.report import (
    CSV_FIELDS,
    merge_only_rows,
    read_csv_rows,
    write_csvs,
)
from core.quality import overview

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------- audit (csv)
def _row(spider, **over):
    """A full crawl_audit row (every CSV_FIELDS key) with plausible defaults."""
    r = {
        "spider": spider,
        "sitemap": "yes",
        "sitemap_total": 120,
        "eligible": "100",
        "scraped": 90,
        "pdf": 3,
        "pdf_own": 2,
        "pdf_ext": 1,
        "unique": 93,
        "rows": 95,
        "true_dupes": 2,
        "versions": 0,
        "pdf_multi": 0,
        "dup_pct": 2,
        "files": 1,
        "content": 88,
        "content_pct": 98,
        "content_med": 4200,
        "coverage_pct": 90,
        "stale": "",
        "flags": "",
        "status": "ok",
    }
    r.update(over)
    return r


def test_read_csv_rows_round_trips_typed(tmp_path):
    rows = [
        _row("a_org"),
        # the placeholder shapes: no sitemap ("-"/"" cells), eligible stays str
        _row(
            "b_org",
            sitemap="no",
            sitemap_total="-",
            eligible="-",
            coverage_pct="",
            stale="⚠ 40d",
            flags="thin? 0.9k",
            status="manual review",
        ),
    ]
    write_csvs(str(tmp_path), rows)
    assert read_csv_rows(str(tmp_path)) == rows


def test_read_csv_rows_missing_returns_none(tmp_path):
    assert read_csv_rows(str(tmp_path)) is None


def test_merge_recomputes_named_and_keeps_rest_byte_identical(tmp_path):
    stored = [_row("a_org"), _row("b_org"), _row("c_org")]
    write_csvs(str(tmp_path), stored)
    with open(tmp_path / "crawl_audit.csv") as fh:
        before = {line.split(",", 1)[0]: line for line in fh}

    fresh = [_row("b_org", scraped=999, status="incomplete")]
    merged = merge_only_rows(
        fresh, read_csv_rows(str(tmp_path)), {"a_org", "b_org", "c_org"}
    )
    assert [r["spider"] for r in merged] == ["a_org", "b_org", "c_org"]
    assert merged[1]["scraped"] == 999  # the named spider was recomputed

    write_csvs(str(tmp_path), merged)
    with open(tmp_path / "crawl_audit.csv") as fh:
        after = {line.split(",", 1)[0]: line for line in fh}
    assert after["a_org"] == before["a_org"]  # untouched rows survive byte-identically
    assert after["c_org"] == before["c_org"]
    assert after["b_org"] != before["b_org"]


def test_merge_drops_row_for_spider_gone_from_working_set(tmp_path):
    write_csvs(str(tmp_path), [_row("a_org"), _row("gone_org")])
    merged = merge_only_rows([_row("a_org")], read_csv_rows(str(tmp_path)), {"a_org"})
    assert [r["spider"] for r in merged] == ["a_org"]


# --------------------------------------------------------------- overview (json)
def _fake_spider(base, name, title):
    d = os.path.join(base, name, "crawls")
    os.makedirs(d, exist_ok=True)
    rec = {
        "url": f"https://{name.replace('_', '.')}/articles/one",
        "title": title,
        "content": "x" * 500,
        "author": "someone",
        "published_date": "2024-03-01",
        "scraped_at": "2026-01-01 00:00:00",
    }
    with open(os.path.join(d, "crawl_01012026.jsonl"), "w") as fh:
        fh.write(json.dumps(rec) + "\n")


def _overview_env(tmp_path, monkeypatch):
    base = str(tmp_path / "proj")
    monkeypatch.setattr(overview, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(overview._env, "project_exists", lambda p: True)
    return base


def _opts(only):
    class O:
        pass

    o = O()
    o.only = only
    o.thin_chars = 200
    return o


def test_overview_only_merges_stored_rows(tmp_path, monkeypatch):
    base = _overview_env(tmp_path, monkeypatch)
    _fake_spider(base, "a_org", "first a title")
    _fake_spider(base, "b_org", "b title")
    overview.run("proj", None)  # full run seeds the row store
    store = os.path.join(base, "_audit", "overview_rows.json")
    with open(store) as fh:
        b_before = next(r for r in json.load(fh) if r["spider"] == "b_org")

    _fake_spider(base, "a_org", "CHANGED a title")  # a_org's crawl changed
    result = overview.run("proj", _opts(["a_org"]))
    assert [r["spider"] for r in result["spiders"]] == ["a_org", "b_org"]
    assert result["spiders"][0]["samples"][0]["title"] == "CHANGED a title"
    with open(store) as fh:
        rows = json.load(fh)
    assert next(r for r in rows if r["spider"] == "b_org") == b_before  # untouched
    assert next(r for r in rows if r["spider"] == "a_org") != b_before


def test_overview_only_drops_row_for_missing_spider_dir(tmp_path, monkeypatch):
    base = _overview_env(tmp_path, monkeypatch)
    _fake_spider(base, "a_org", "a title")
    out_dir = os.path.join(base, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    # stored row for a spider whose data folder does not exist (removed project dir)
    with open(os.path.join(out_dir, "overview_rows.json"), "w") as fh:
        json.dump([{"spider": "ghost_org"}], fh)
    result = overview.run("proj", _opts(["a_org"]))
    assert [r["spider"] for r in result["spiders"]] == ["a_org"]


def test_overview_only_without_store_warns_and_proceeds(tmp_path, monkeypatch, capsys):
    base = _overview_env(tmp_path, monkeypatch)
    _fake_spider(base, "a_org", "a title")
    _fake_spider(base, "b_org", "b title")
    result = overview.run("proj", _opts(["a_org"]))
    assert [r["spider"] for r in result["spiders"]] == ["a_org"]
    assert "no previous overview to merge into" in capsys.readouterr().out
    # the narrowed run still seeds the store for next time
    assert os.path.exists(os.path.join(base, "_audit", "overview_rows.json"))


def test_csv_fields_match_scoring_row_keys():
    """CSV_FIELDS is the lossless-store contract: it must cover exactly the keys
    score_spider() emits (drift here would silently lose a column on merge)."""
    import inspect

    from core.quality.crawl_audit import scoring

    src = inspect.getsource(scoring.score_spider)
    for k in CSV_FIELDS:
        assert f'"{k}":' in src
