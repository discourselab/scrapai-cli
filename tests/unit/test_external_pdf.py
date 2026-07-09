"""The PDF-harvest lens (external_pdf.py) under the row model: own/external
split, degrade order for own-domains, legacy field rows ignored, found_on in
the report."""

import json
import os

import pytest

from core.quality import external_pdf

pytestmark = pytest.mark.unit


def _row(url, found_on="https://x.org/a", content_type="pdf"):
    return json.dumps(
        {
            "url": url,
            "title": url.rsplit("/", 1)[-1],
            "content": "",
            "metadata_json": {"content_type": content_type, "found_on": found_on},
        }
    )


@pytest.fixture
def proj(tmp_path, monkeypatch):
    monkeypatch.setattr(external_pdf, "DATA_DIR", str(tmp_path))
    d = tmp_path / "proj" / "x_org" / "crawls"
    d.mkdir(parents=True)
    cfg = tmp_path / "proj" / "x_org" / "final_spider.json"
    cfg.write_text(
        json.dumps({"allowed_domains": ["x.org"], "source_url": "https://x.org"})
    )
    # DB unavailable in tests → forces the final_spider.json fallback path
    monkeypatch.setattr(external_pdf, "own_domains", lambda p: {})
    return tmp_path, d


def test_own_external_split_and_found_on(proj, capsys):
    tmp_path, d = proj
    rows = [
        _row("https://x.org/own1.pdf"),  # same-org
        _row("https://docs.x.org/own2.pdf"),  # same-org subdomain
        _row("https://iea.org/cite.pdf", found_on="https://x.org/article-7"),
        _row(
            "https://iea.org/cite.pdf", found_on="https://x.org/article-9"
        ),  # 2nd occurrence
        _row("https://s3.amazonaws.com/bucket/rep.pdf"),
        # a legacy field-based row must be IGNORED (not a pdf row)
        json.dumps(
            {
                "url": "https://x.org/page",
                "content": "text",
                "external_pdf_urls": ["https://old.example/legacy.pdf"],
            }
        ),
    ]
    (d / "crawl_01012026.jsonl").write_text("\n".join(rows) + "\n")
    res = external_pdf.run("proj")
    s = res["spiders"][0]
    assert s["spider"] == "x_org"
    assert s["own_unique"] == 2 and s["own_total"] == 2
    assert s["total"] == 3 and s["unique"] == 2  # ext occurrences vs unique
    hosts = {h["host"]: h for h in s["hosts"]}
    assert hosts["iea.org"]["count"] == 2  # citation frequency
    assert hosts["iea.org"]["found_on"].startswith("https://x.org/article")
    assert "s3.amazonaws.com" in hosts
    assert not any("legacy" in u for h in s["hosts"] for u in h["urls"])
    md = open(res["report_path"]).read()
    assert "| host | links | sample | found on |" in md
    assert "· 2 same-org PDFs" in md


def test_no_domains_resolvable_everything_external(proj, capsys):
    tmp_path, d = proj
    os.remove(tmp_path / "proj" / "x_org" / "final_spider.json")
    (d / "crawl_01012026.jsonl").write_text(_row("https://x.org/own.pdf") + "\n")
    res = external_pdf.run("proj")
    s = res["spiders"][0]
    assert s["total"] == 1 and s["own_unique"] == 0  # degraded: all external
    assert "no own-domains resolvable" in capsys.readouterr().out


def test_empty_spider(proj):
    res = external_pdf.run("proj")
    s = res["spiders"][0]
    assert s == {
        "spider": "x_org",
        "total": 0,
        "unique": 0,
        "own_total": 0,
        "own_unique": 0,
        "hosts": [],
    }
