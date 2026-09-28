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


# ---------------------------------------------------------------- item 3
TIMEOUT = "twisted.internet.error.TimeoutError"


def _final_stats(data, spider, responses=100, final_status=None, **kw):
    """A crawl-stats file carrying the final-outcome keys (final=True)."""
    _stats(
        data,
        spider,
        status={"200": responses},
        requests=responses,
        responses=responses,
        final_status=final_status or {},
        exceptions=kw.pop("exceptions", {}),
        retries=kw.pop("retries", {}),
        sitemap_total=100,
        eligible=100,
        **kw,
    )


def test_failed_excludes_retried_and_ignorerequest(data):
    # 10 timeouts raised, 7 of them retried → 3 final failures; the 50
    # IgnoreRequest drops (offsite / robots) are not failures at all
    _final_stats(
        data,
        "example_org",
        exceptions={TIMEOUT: 10, "scrapy.exceptions.IgnoreRequest": 50},
        retries={TIMEOUT: 7, "503 Service Unavailable": 4},
    )
    out = spiders_db.crawl_stats_outcomes("proj", "example_org")
    assert out == {
        "dead": 0,
        "blocked": 0,
        "failed": 3,
        "base": 103,
        "final": True,
        "resumed": False,
        "summed": False,
    }
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["failed"] == "3 (2.9%)"
    assert "failed" not in row["flags"]  # 3 < the 5-count floor


def test_status_blind_shows_dash(data):
    _final_stats(
        data,
        "example_org",
        final_status={"403": 30, "404": 10},
        exceptions={TIMEOUT: 2},
    )
    sp = _sp(status_blind=True)
    row = score_spider("example_org", sp, _corpus(100), _ctx(data))
    assert row["dead"] == "–" and row["blocked"] == "–"
    assert row["failed"] == "2 (2.0%)"  # no response at all is still visible
    assert "blocked" not in row["flags"]


def test_load_spiders_status_blind_excludes_curl_cffi(monkeypatch):
    def fake_query(sql):
        if "FROM spiders WHERE" in sql:
            return [
                dict(name=n, start_urls="[]", source_url=f"https://{n}.test")
                for n in ("cf", "br", "cc")
            ]
        if "spider_settings" in sql:
            return [
                {"name": "cf", "key": "CLOUDFLARE_ENABLED", "value": "true"},
                {"name": "br", "key": "BROWSER_ENABLED", "value": "1"},
                {"name": "cc", "key": "CURL_CFFI_ENABLED", "value": "true"},
            ]
        return []

    monkeypatch.setattr(spiders_db, "db_query", fake_query)
    sps = spiders_db.load_spiders("proj")
    assert sps["cf"]["status_blind"] and sps["br"]["status_blind"]
    assert not sps["cc"]["status_blind"]
    assert all(sps[n]["browser"] for n in ("cf", "br", "cc"))  # unchanged


def test_old_stats_failed_dash(data):
    # attempt-level counts only: shown, but never a flag — even at 50% 403
    _stats(
        data,
        "example_org",
        status={"200": 100, "403": 100},
        sitemap_total=100,
        eligible=100,
    )
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["failed"] == "–"
    assert row["blocked"] == "100 (50%)"
    assert "blocked" not in row["flags"]
    assert row["status"] == "ok"


def test_blocked_over_5pct_manual_review(data):
    _final_stats(data, "example_org", final_status={"403": 6, "429": 4})
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["blocked"] == "10 (10%)"
    assert "blocked 10 (10%)" in row["flags"]
    assert row["status"] == "manual review"


def test_blocked_min_count(data):
    # 4 of 20 is 20% — but four blocked requests is noise, not a wall
    _final_stats(data, "example_org", responses=20, final_status={"403": 4})
    c = _corpus(100)
    row = score_spider("example_org", _sp(), c, _ctx(data))
    assert row["blocked"] == "4 (20%)"
    assert "blocked" not in row["flags"]


def test_dead_never_flags(data):
    _final_stats(data, "example_org", final_status={"404": 40, "410": 10})
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["dead"] == "50 (50%)"
    assert row["flags"] == ""
    assert row["status"] == "ok"


def test_resumed_unsummed_leg_flags_with_caveat(data):
    # a resumed crawl whose earlier legs couldn't be summed: the file covers
    # the last leg only. Its 25% blocked is still real evidence → it flags,
    # with the "last leg" caveat in the cells and in the flag itself
    _final_stats(
        data,
        "example_org",
        final_status={"403": 30},
        exceptions={TIMEOUT: 20},
        resumed=True,
    )
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["blocked"] == "30 (25%) last leg"
    assert row["failed"] == "20 (17%) last leg"
    assert row["outcomes_basis"] == "last leg"
    assert "blocked 30 (25%) last leg" in row["flags"]
    assert "failed 20 (17%) last leg" in row["flags"]
    assert row["status"] == "manual review"
    from core.quality.dashboard.coverage_tab import _coverage_detail
    from core.quality.dashboard.widgets import _flag_title

    assert "last crawl leg only" in _coverage_detail("proj", row)
    assert _flag_title("blocked 30 (25%) last leg").startswith("Many of the crawl")


def test_resumed_summed_is_a_whole_crawl(data):
    # the writer summed the legs (`summed`): whole-crawl figures, no caveat
    _final_stats(
        data,
        "example_org",
        final_status={"403": 30},
        resumed=True,
        summed=True,
    )
    out = spiders_db.crawl_stats_outcomes("proj", "example_org")
    assert out["resumed"] and out["summed"]
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["blocked"] == "30 (30%)"
    assert row["outcomes_basis"] == "final"
    assert "blocked 30 (30%)" in row["flags"].split(" · ")
    assert "last leg" not in row["flags"]


def test_old_format_marked_per_attempt_in_html(data):
    from core.quality.dashboard.coverage_tab import _coverage_detail

    _stats(data, "example_org", status={"200": 100, "403": 100})
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert row["outcomes_basis"] == "attempts"
    html = _coverage_detail("proj", row)
    assert "per attempt, older crawl format" in html
    # the tooltips no longer call such a figure "not recorded"
    from core.quality.dashboard.widgets import COLUMN_DEFS

    assert "older crawl format counts every attempt" in COLUMN_DEFS["blocked"]
    _final_stats(data, "example_org", final_status={"403": 1})
    row = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    assert "per attempt, older crawl format" not in _coverage_detail("proj", row)


def test_old_format_marked_in_md_row(data):
    import io

    from core.quality.crawl_audit.report import write_table

    _stats(data, "example_org", status={"200": 100, "403": 100, "404": 4})
    old = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    _final_stats(data, "site01_org", final_status={"403": 1})
    new = score_spider("site01_org", _sp(), _corpus(100), _ctx(data))
    fh = io.StringIO()
    write_table(fh, [old, new], with_status=True)
    rows = {ln.split(" | ")[0]: ln for ln in fh.getvalue().splitlines()}
    # per-attempt figures carry † in the row itself; "–" (not recorded) doesn't
    assert "| 4 (2.0%)† | 100 (49%)† | – |" in rows["| example_org"]
    assert "†" not in rows["| site01_org"]


def test_outcome_glossary_matches_flag_token_only():
    from core.quality.dashboard.widgets import _flag_title

    assert _flag_title("failed 12 (6.0%)").startswith("Many requests got no")
    assert _flag_title("blocked 9 (8.5%)").startswith("Many of the crawl")
    # a skip reason / review tag that merely says "failed" / "blocked"
    assert _flag_title("sitemap fetch failed on proxy") == ""
    assert _flag_title("✓ reviewed: blocked by design") == _flag_title("✓ reviewed")


def test_outcome_columns_survive_only_merge(data, tmp_path):
    import io

    from core.quality.crawl_audit.report import (
        merge_only_rows,
        read_csv_rows,
        write_csvs,
        write_table,
    )

    _final_stats(
        data,
        "example_org",
        final_status={"404": 3, "403": 9},
        exceptions={TIMEOUT: 6},
    )
    stored = score_spider("example_org", _sp(), _corpus(100), _ctx(data))
    out = tmp_path / "csv"
    out.mkdir()
    write_csvs(str(out), [stored])
    fresh = score_spider("site01_org", _sp(), _corpus(10), _ctx(data))
    stored_rows = read_csv_rows(str(out))
    merged = merge_only_rows([fresh], stored_rows, {"example_org": 1})
    back = next(r for r in merged if r["spider"] == "example_org")
    for k in ("dead", "blocked", "failed", "flags"):
        assert back[k] == stored[k]
    assert (back["dead"], back["blocked"], back["failed"]) == (
        "3 (2.8%)",
        "9 (8.5%)",
        "6 (5.7%)",
    )
    fh = io.StringIO()
    write_table(fh, merged, with_status=False)
    md = fh.getvalue()
    assert "| coverage | dead | blocked | failed |" in md
    assert "| 3 (2.8%) | 9 (8.5%) | 6 (5.7%) |" in md
    # the fresh spider has no crawl-stats → the "not recorded" dash
    assert "| – | – | – |" in md
