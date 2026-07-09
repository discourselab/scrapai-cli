"""Unit tests for the sitemap-cache lifecycle in core/quality/crawl_audit.py.

The contract: a FAILED fetch leaves no cache dir at all (so default 'missing' mode
retries next run), a successful fetch's returned text is always this run's bytes
(never a stale leftover), and a re-fetch replaces the spider's whole previous
cache generation instead of unioning with it.
"""

import os

import pytest

from core.quality import crawl_audit as ca

pytestmark = pytest.mark.unit

URLSET = (
    '<?xml version="1.0"?><urlset>'
    "<loc>https://example.org/a</loc><loc>https://example.org/b</loc></urlset>"
)


def _state(cap=100):
    return {"global": 0, "global_cap": cap, "per_cap": cap}


def _fake_run(write_html):
    """A subprocess.run stand-in for `scrapai inspect`: writes `write_html` (if not
    None) into the --output-dir it is given, mimicking the inspector's mkdir-first
    behaviour (the dir exists even when nothing was fetched)."""

    def run(cmd, **kw):
        outdir = cmd[cmd.index("--output-dir") + 1]
        os.makedirs(outdir, exist_ok=True)
        if write_html is not None:
            with open(os.path.join(outdir, "page.html"), "w") as fh:
                fh.write(write_html)
        return None

    return run


def test_fetch_success_swaps_in(tmp_path, monkeypatch):
    monkeypatch.setattr(ca.subprocess, "run", _fake_run(URLSET))
    outdir = str(tmp_path / "spider_0")
    text = ca.fetch("https://example.org/sitemap.xml", outdir, "p", False, _state())
    assert "example.org/a" in text
    assert os.path.exists(os.path.join(outdir, "page.html"))
    assert not os.path.exists(outdir + ".tmp")  # no temp residue


def test_fetch_failure_leaves_nothing(tmp_path, monkeypatch):
    # inspector created the dir but produced no page.html (blocked/timeout)
    monkeypatch.setattr(ca.subprocess, "run", _fake_run(None))
    outdir = str(tmp_path / "spider_0")
    assert (
        ca.fetch("https://example.org/sitemap.xml", outdir, "p", False, _state())
        is None
    )
    assert not os.path.exists(outdir)  # nothing to poison has_cache
    assert not os.path.exists(outdir + ".tmp")


def test_fetch_failure_never_serves_stale(tmp_path, monkeypatch):
    # a previous run left content at outdir; this run's fetch fails → None, not the leftover
    outdir = tmp_path / "spider_0"
    outdir.mkdir()
    (outdir / "page.html").write_text(
        "<urlset><loc>https://old.example/x</loc></urlset>"
    )
    monkeypatch.setattr(ca.subprocess, "run", _fake_run(None))
    assert (
        ca.fetch("https://example.org/sitemap.xml", str(outdir), "p", False, _state())
        is None
    )
    # the old content survives as cache (a failed refresh keeps history)...
    assert (outdir / "page.html").exists()


def test_empty_page_html_counts_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ca.subprocess, "run", _fake_run(""))
    outdir = str(tmp_path / "spider_0")
    assert (
        ca.fetch("https://example.org/sitemap.xml", outdir, "p", False, _state())
        is None
    )
    assert not os.path.exists(outdir)


def test_refetch_prunes_previous_generation(tmp_path, monkeypatch):
    cache = str(tmp_path)
    # previous generation: two sub-sitemaps
    for i, loc in enumerate(("https://example.org/old1", "https://example.org/old2")):
        d = tmp_path / f"sp_{i}"
        d.mkdir()
        (d / "page.html").write_text(f"<urlset><loc>{loc}</loc></urlset>")

    # this run's sitemap has consolidated to ONE urlset with new locs
    def fake_fetch(url, outdir, project, browser, state):
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "page.html"), "w") as fh:
            fh.write(URLSET)
        return URLSET

    monkeypatch.setattr(ca.sitemaps, "fetch", fake_fetch)
    sp = {"browser": False, "start_urls": ["https://example.org/sitemap.xml"]}
    ca.fetch_spider_sitemaps("sp", sp, "p", cache, _state(), browser_retry=False)
    pages = ca.collect_pages("sp", cache)
    assert pages == {"https://example.org/a", "https://example.org/b"}  # no old1/old2


def test_collect_pages_skips_empty_files(tmp_path):
    d = tmp_path / "sp_0"
    d.mkdir()
    (d / "page.html").write_text("")  # legacy failed-fetch residue
    d1 = tmp_path / "sp_1"
    d1.mkdir()
    (d1 / "page.html").write_text(URLSET)
    assert ca.collect_pages("sp", str(tmp_path)) == {
        "https://example.org/a",
        "https://example.org/b",
    }


def test_ensure_review_configs_atomic_and_preserving(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(ca.spiders_db, "DATA_DIR", str(tmp_path))
    d = tmp_path / "proj" / "_audit"
    d.mkdir(parents=True)
    # existing file with a stale _instructions and a human entry
    path = d / "audit_notes.json"
    path.write_text(json.dumps({"_instructions": "old", "rmi_org": {"status": "ok"}}))
    ca.ensure_review_configs("proj")
    data = json.loads(path.read_text())
    assert data["rmi_org"] == {"status": "ok"}  # human entry preserved
    assert data["_instructions"] != "old"  # refreshed
    assert not list(d.glob("*.tmp"))  # atomic write left no residue
