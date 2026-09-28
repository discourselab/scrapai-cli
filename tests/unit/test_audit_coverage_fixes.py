"""score_spider / report / dashboard behaviour for the coverage fixes: the full
rule-eligible denominator (no liveness scaling). Every test runs against a
tmp DATA_DIR and a fetch guard — no test may reach the network."""

import json
from types import SimpleNamespace

import pytest

from core.quality.crawl_audit import scoring, sitemaps, spiders_db
from core.quality.crawl_audit.scoring import ScoreContext, score_spider

pytestmark = pytest.mark.unit


def _no_network(*a, **k):
    raise AssertionError("test tried to fetch")


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A tmp DATA_DIR with every fetch path patched to raise."""
    monkeypatch.setattr(spiders_db, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sitemaps, "fetch", _no_network)
    monkeypatch.setattr(sitemaps.subprocess, "run", _no_network)
    monkeypatch.setattr(scoring, "deltafetch_estimate", lambda p, s: 0)
    return tmp_path


def _ctx(data, **opts):
    return ScoreContext(
        project="proj",
        opts=SimpleNamespace(
            no_browser_retry=True,
            no_fetch=opts.get("no_fetch", True),
            fetch_all=opts.get("fetch_all", False),
        ),
        cache_dir=str(data / "proj" / "_audit" / "sitemap_cache"),
        state={"global": 0, "global_cap": 100, "per_cap": 10},
        skip={},
        notes={},
        has_cache=lambda n: False,
        mark_no_sitemap=lambda n: None,
        should_fetch=lambda n: False,
    )


def _sp(use_sitemap=True, start_urls=(), **kw):
    sp = {
        "start_urls": list(start_urls),
        "use_sitemap": use_sitemap,
        "rules": [],
        "deny": [],
        "n_rules": 0,
        "browser": False,
        "host": "example.org",
        "domains": ["example.org"],
    }
    sp.update(kw)
    return sp


def _corpus(unique, content=None, med=3000):
    return {
        "unique": unique,
        "content": unique if content is None else content,
        "pdf": 0,
        "pdf_hosts": {},
        "rows": unique,
        "uc": unique,
        "files": 1,
        "content_med": med,
        "newest": None,
        "urlset": set(),
        "_files": [],
    }


def _stats(data, spider, **d):
    p = data / "proj" / "_audit" / "crawl_stats"
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{spider}.json").write_text(json.dumps({"spider": spider, **d}))


# ---------------------------------------------------------------- item 2
def test_coverage_not_scaled_by_liveness(data):
    # 100 eligible, 50 of the attempts 404/403: the old math scaled eligible to
    # 50 and read 50 scraped as 100% ok. Now it is a 50% shortfall.
    _stats(
        data,
        "example_org",
        status={"200": 50, "404": 25, "403": 25},
        sitemap_total=100,
        eligible=100,
    )
    row = score_spider("example_org", _sp(), _corpus(50), _ctx(data))
    assert row["eligible"] == "100"
    assert row["coverage_pct"] == 50
    assert row["status"] == "incomplete"
    assert "liveness" not in row["flags"]


# ---------------------------------------------------------------- item 4
def test_over_115_flags_on_crawl_stats_path(data):
    # counts came from the crawl (no URL set, so drift can't run) — the
    # coverage figure alone must still catch 300%
    _stats(
        data,
        "example_org",
        status={"200": 300},
        sitemap_total=100,
        eligible=100,
    )
    row = score_spider("example_org", _sp(), _corpus(300), _ctx(data))
    assert row["coverage_pct"] == 300
    assert "scraped more than expected (300%)" in row["flags"]
    assert row["status"] == "manual review"


def test_over_115_needs_more_than_20_scraped(data):
    # 15 scraped against a 2-URL sitemap reads 750% but says nothing: no flag
    _stats(data, "example_org", status={"200": 15}, sitemap_total=2, eligible=2)
    row = score_spider("example_org", _sp(), _corpus(15), _ctx(data))
    assert row["coverage_pct"] == 750
    assert "scraped more than expected" not in row["flags"]
    # a small sitemap is still a yardstick: 60 scraped of a 10-URL urlset flags
    _stats(data, "example_org", status={"200": 60}, sitemap_total=10, eligible=10)
    row = score_spider("example_org", _sp(), _corpus(60), _ctx(data))
    assert "scraped more than expected (600%)" in row["flags"]
    assert row["status"] == "manual review"


def _cache_urlset(data, spider, urls):
    d = data / "proj" / "_audit" / "sitemap_cache" / f"{spider}_0"
    d.mkdir(parents=True, exist_ok=True)
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    (d / "page.html").write_text(f"<urlset>{locs}</urlset>")


def test_drift_no_double_flag(data):
    # fetched-sitemap path: every sitemap URL was scraped, plus 200 more —
    # the overlap is perfect, so only the over-expected flag may fire
    listed = [f"https://example.org/a/{i}" for i in range(100)]
    extra = [f"https://example.org/b/{i}" for i in range(200)]
    _cache_urlset(data, "example_org", listed)
    c = _corpus(300)
    c["urlset"] = set(listed + extra)
    row = score_spider("example_org", _sp(), c, _ctx(data))
    assert row["coverage_pct"] == 300
    assert "scraped more than expected (300%)" in row["flags"]
    assert "sitemap-drift" not in row["flags"]
    assert row["status"] == "manual review"


def test_meter_label_unclamped():
    from core.quality.dashboard import _meter

    m = _meter(300)
    assert ">300%<" in m  # the label is the true value
    assert "width:100%" in m  # only the bar is clamped
    assert "bar green" in m
    assert "width:0%" in _meter(-5) and ">-5%<" in _meter(-5)
