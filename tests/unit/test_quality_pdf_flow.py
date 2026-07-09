"""Engine-level flow over a synthetic project: mixed article + PDF-row crawls
through corpus → scoring surfaces → overview profiling, fresh vs cached."""

import json

import pytest

from core.quality import corpus, overview

pytestmark = pytest.mark.unit

ARTICLES = [
    {
        "url": f"https://x.org/post/{i}",
        "title": f"Post {i}",
        "content": "a proper article body " * 30,
        "author": "Jane Doe",
        "published_date": f"2024-0{(i % 8) + 1}-01",
    }
    for i in range(6)
]
PDFS = [
    {
        "url": f"https://x.org/files/r{i}.pdf",
        "title": f"r{i}.pdf",
        "content": "",
        "metadata_json": {"content_type": "pdf", "found_on": "https://x.org/post/1"},
    }
    for i in range(4)
] + [
    {
        "url": "https://iea.org/cite.pdf",
        "title": "cite.pdf",
        "content": "",
        "metadata_json": {"content_type": "pdf", "found_on": "https://x.org/post/2"},
    }
]


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "DATA_DIR", str(tmp_path))
    d = tmp_path / "proj" / "x_org" / "crawls"
    d.mkdir(parents=True)
    rows = [json.dumps(r) for r in ARTICLES + PDFS]
    (d / "crawl_01012026.jsonl").write_text("\n".join(rows) + "\n")
    cfg = {
        "allowed_domains": ["x.org"],
        "sections": [
            {
                "match": ["/post/.*"],
                "extract": {
                    "title": {"css": "h1::text"},
                    "summary": {"css": ".lead::text"},
                },
            }
        ],
    }
    (tmp_path / "proj" / "x_org" / "final_spider.json").write_text(json.dumps(cfg))
    return tmp_path


def test_scan_project_fresh_equals_cached(proj):
    fresh = corpus.scan_project("proj", use_cache=False)["x_org"]
    cached = corpus.scan_project("proj", use_cache=True)["x_org"]
    for k in (
        "unique",
        "uc",
        "content",
        "title",
        "rows",
        "content_med",
        "pdf",
        "pdf_hosts",
    ):
        assert fresh[k] == cached[k], k
    assert fresh["pdf"] == 5
    assert fresh["pdf_hosts"] == {"x.org": 4, "iea.org": 1}
    assert fresh["content"] == 6  # articles only
    assert fresh["unique"] == 11  # total incl. pdf rows


def test_overview_separates_articles_from_pdfs(proj):
    spider_dir = str(proj / "proj" / "x_org")
    cfg = overview._load_config(spider_dir)
    row = overview.profile_spider("x_org", spider_dir, cfg, thin_chars=200)
    overview._flags(row, 200)
    assert row["rows"] == 6 and row["rows_total"] == 11
    assert row["pdf_rows"] == 5 and row["pdf_unique"] == 5 and row["pdf_ext"] == 1
    assert row["thin_pct"] == 0  # pdf rows don't count as thin
    assert row["null_date_pct"] == 0  # nor as undated
    assert row["offdomain"] == 0  # external pdf ≠ off-domain leak
    assert row["attention"] == 0  # a healthy mixed spider is clean
    # sections-authored config desugared → its extract keys are the field list
    assert "summary" in [f["field"] for f in row["fields"]]


def test_overview_reads_fields_key():
    cfg = {"settings": {"FIELDS": {"title": {}, "body": {}}}}
    assert overview._configured_fields(cfg) == ["title", "body"]
    legacy = {"settings": {"FIELD_EXTRACT": {"title": {}}}}
    assert overview._configured_fields(legacy) == ["title"]
