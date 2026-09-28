"""score_spider / report / dashboard behaviour for the coverage fixes: the full
rule-eligible denominator (no liveness scaling). Every test runs against a
tmp DATA_DIR and a fetch guard — no test may reach the network."""

import json
import os
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


# ---------------------------------------------------------------- item 1
INDEX = "https://example.org/sitemap_index.xml"


def _kids(*names):
    return [f"https://example.org/{n}-sitemap.xml" for n in names]


def _index_xml(urls):
    locs = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in urls)
    return f"<sitemapindex>{locs}</sitemapindex>"


class FakeFetch:
    """Stands in for sitemaps.fetch: serves `pages`, counts every call, and
    honours the fetch budget like the real one. Nothing leaves the process."""

    def __init__(self, pages=None):
        self.pages, self.calls = pages or {}, []

    def __call__(self, url, outdir, project, browser, state):
        self.calls.append(url)
        if state["global"] >= state["global_cap"]:
            return None
        state["global"] += 1
        text = self.pages.get(url)
        if not text:
            return None
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "page.html"), "w") as fh:
            fh.write(text)
        return text


def _robots_snapshot(data, sitemaps_, host="example_org", date="2026-09-01"):
    """A compliance snapshot on disk whose robots.txt declares `sitemaps_`."""
    d = data / "proj" / "_audit" / "compliance" / host / date
    d.mkdir(parents=True, exist_ok=True)
    rec = {"robots": {"fetched": True, "sitemaps": list(sitemaps_)}}
    (d / "compliance.json").write_text(json.dumps(rec))
    lines = "".join(f"Sitemap: {u}\n" for u in sitemaps_)
    (d / "robots.txt").write_text("User-agent: *\nDisallow:\n" + lines)


def _yes_row(data, ctx, start_urls, spider="example_org"):
    _stats(data, spider, status={"200": 90}, sitemap_total=100, eligible=100)
    sp = _sp(start_urls=start_urls)
    return score_spider(spider, sp, _corpus(90), ctx)


def test_given_index_counts_all_children(data, monkeypatch):
    kids = _kids("post", "page", "category", "event", "report")
    fake = FakeFetch({INDEX: _index_xml(kids)})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    _robots_snapshot(data, [INDEX])
    # the given index is spelled differently (www, trailing slash): norm_url
    given = ["https://www.example.org/sitemap_index.xml/"]
    row = _yes_row(data, _ctx(data, no_fetch=False), given)
    assert fake.calls == [INDEX]
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (5, 5)
    assert [e["url"] for e in row["sitemap_list"]] == kids  # taxonomy counts
    assert row["sitemap"] == "yes"  # the label itself never changes


def test_given_not_in_index_added(data, monkeypatch):
    kids = _kids("post", "page", "tag")
    fake = FakeFetch({INDEX: _index_xml(kids)})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    _robots_snapshot(data, [INDEX])
    extra = "https://example.org/news/news-sitemap.xml"
    row = _yes_row(data, _ctx(data, no_fetch=False), [kids[1], kids[0], extra])
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (3, 4)
    lst = row["sitemap_list"]
    # given first, then not given
    assert [e["given"] for e in lst] == [True, True, True, False]
    assert lst[2] == {"url": extra, "given": True, "in_index": False}
    assert lst[3]["url"] == kids[2]


def test_robots_sitemaps_read_from_disk_no_fetch(data):
    # nothing on disk → None ("never looked"), not []
    on_disk = spiders_db.robots_sitemaps_on_disk
    assert on_disk("proj", "example.org", "x") is None
    leaf = "https://example.org/pages-sitemap.xml"
    _robots_snapshot(data, [INDEX])
    crawls = data / "proj" / "example_org" / "crawls"
    crawls.mkdir(parents=True)
    witness = f"Sitemap: {leaf}\nSitemap: {INDEX}\n"
    (crawls / "robots_27092026.txt").write_text(witness)
    got = on_disk("proj", "www.example.org", "example_org")
    assert got == [INDEX, leaf]
    # manifests already cached → a default-mode run lists them with ZERO
    # fetches (the fixture's fetch raises on any call)
    cache = str(data / "proj" / "_audit" / "sitemap_cache")
    sitemaps._save_manifest(INDEX, cache, _index_xml(_kids("post", "page")))
    urlset = "<urlset><url><loc>x</loc></url></urlset>"
    sitemaps._save_manifest(leaf, cache, urlset)
    row = _yes_row(data, _ctx(data, no_fetch=False), [INDEX])
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (2, 3)


def test_no_refetch_when_index_cached(data, monkeypatch):
    fake = FakeFetch({INDEX: _index_xml(_kids("post", "page"))})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    _robots_snapshot(data, [INDEX])
    ctx = _ctx(data, no_fetch=False)
    _yes_row(data, ctx, [INDEX], spider="example_org")
    # a second spider on the same host shares the host-keyed manifest
    _yes_row(data, ctx, _kids("post"), spider="site01_org")
    assert fake.calls == [INDEX]
    # next run (fresh budget state): still no fetch
    row = _yes_row(data, _ctx(data, no_fetch=False), [INDEX])
    assert fake.calls == [INDEX]
    assert row["sitemaps_total"] == 2


def test_failed_index_marker_blocks_refetch(data, monkeypatch):
    fake = FakeFetch()  # the site answers nothing
    monkeypatch.setattr(sitemaps, "fetch", fake)
    _robots_snapshot(data, [INDEX])
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert fake.calls == [INDEX]
    assert row["sitemaps_total"] == "?"
    assert "fetch failed" in row["sitemaps_note"]
    host = data / "proj" / "_audit" / "sitemap_cache" / "_host" / "example.org"
    assert list(host.glob("sm_*.failed.json"))
    # every later default run remembers the failure: no fetch at all
    monkeypatch.setattr(sitemaps, "fetch", _no_network)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert row["sitemaps_total"] == "?"
    assert "fetch failed" in row["sitemaps_note"]


def test_fetch_all_reprobes_failed(data, monkeypatch):
    monkeypatch.setattr(sitemaps, "fetch", FakeFetch())
    _robots_snapshot(data, [INDEX])
    # a first run leaves a failure marker
    _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    fake = FakeFetch({INDEX: _index_xml(_kids("post", "page"))})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    ctx = _ctx(data, no_fetch=False, fetch_all=True)
    row = _yes_row(data, ctx, _kids("post"))
    _yes_row(data, ctx, _kids("page"), spider="site01_org")  # once per run
    assert fake.calls == [INDEX]
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)
    host = data / "proj" / "_audit" / "sitemap_cache" / "_host" / "example.org"
    assert not list(host.glob("sm_*.failed.json"))


def test_no_fetch_shows_unknown_total(data):
    _robots_snapshot(data, [INDEX])
    kids = _kids("post", "page", "event", "report")
    row = _yes_row(data, _ctx(data, no_fetch=True), kids)
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (4, "?")
    assert "--no-fetch" in row["sitemaps_note"]
    from core.quality.crawl_audit.report import sitemap_cell

    assert sitemap_cell(row) == "[4/?](#sm-example_org)"
    # a total that's unknown can't call anything "not listed"
    assert all(e["in_index"] for e in row["sitemap_list"])


def test_index_fetch_no_cap_hit_for_crawl_stats_spider(data, monkeypatch):
    monkeypatch.setattr(
        sitemaps, "fetch", FakeFetch({INDEX: _index_xml(_kids("post"))})
    )
    _robots_snapshot(data, [INDEX])
    ctx = _ctx(data, no_fetch=False)
    ctx.state["global_cap"] = 1
    row = _yes_row(data, ctx, _kids("post"))
    # coverage came from the crawl, so the cap can't have truncated it
    assert "sitemap-cap-hit" not in row["flags"]


def test_index_fetches_have_own_budget(data, monkeypatch):
    # the listing's index fetch must not use up --global-cap: a LATER spider
    # whose coverage does depend on fetches isn't flagged sitemap-cap-hit
    monkeypatch.setattr(
        sitemaps, "fetch", FakeFetch({INDEX: _index_xml(_kids("post"))})
    )
    _robots_snapshot(data, [INDEX])
    ctx = _ctx(data, no_fetch=False)
    ctx.state["global_cap"] = 1
    _yes_row(data, ctx, _kids("post"))
    assert ctx.state["global"] == 0
    assert ctx.state["index_budget"]["global"] == 1
    later = score_spider("site01_org", _sp(start_urls=_kids("post")), _corpus(60), ctx)
    assert "sitemap-cap-hit" not in later["flags"]


def _two_rows(data):
    _robots_snapshot(data, [INDEX])
    cache = str(data / "proj" / "_audit" / "sitemap_cache")
    index = _index_xml(_kids("post", "page", "tag"))
    sitemaps._save_manifest(INDEX, cache, index)
    yes = _yes_row(data, _ctx(data), _kids("post", "page"))
    sp = _sp(use_sitemap=False)
    no = score_spider("site01_org", sp, _corpus(60), _ctx(data))
    return [yes, no]


def test_sitemap_list_survives_only_merge(data, tmp_path):
    from core.quality.crawl_audit.report import merge_only_rows, read_csv_rows
    from core.quality.crawl_audit.report import write_csvs

    rows = _two_rows(data)
    out = tmp_path / "csv"
    out.mkdir()
    write_csvs(str(out), rows)
    present = {"example_org", "site01_org"}
    back = merge_only_rows([], read_csv_rows(str(out)), present)
    keys = ("sitemap", "sitemaps_given", "sitemaps_total", "sitemap_list")
    for fresh, stored in zip(rows, back):
        assert {k: stored[k] for k in keys} == {k: fresh[k] for k in keys}
    assert back[0]["sitemap_list"][2] == {
        "url": _kids("tag")[0],
        "given": False,
        "in_index": True,
    }


def test_coverage_csv_keeps_yes_rows(data, tmp_path):
    import csv

    from core.quality.crawl_audit.report import write_csvs

    write_csvs(str(tmp_path), _two_rows(data))
    with open(tmp_path / "coverage.csv", newline="") as fh:
        cov = list(csv.DictReader(fh))
    got = [(r["spider"], r["sitemap"]) for r in cov]
    assert got == [("example_org", "yes")]
    assert cov[0]["sitemaps_given"] == "2" and cov[0]["sitemaps_total"] == "3"


def test_non_sitemap_spider_no_block(data):
    from core.quality.crawl_audit.report import write_outputs
    from core.quality.dashboard import render_dashboard

    rows = _two_rows(data)
    no = rows[1]
    assert no["sitemap"] == "no" and no["sitemaps_given"] == ""
    assert no["sitemap_list"] == []
    write_outputs("proj", rows)
    md = (data / "proj" / "_audit" / "audit_proj.md").read_text()
    assert "sm-site01_org" not in md
    assert "| site01_org | no |" in md
    html = render_dashboard("proj", rows, [])
    assert "sm-site01_org" not in html
    assert "## Sitemaps given to spiders (1)" in md


def test_md_and_html_anchor_links(data):
    from core.quality.crawl_audit.report import write_outputs
    from core.quality.dashboard import render_dashboard

    rows = _two_rows(data)
    write_outputs("proj", rows)
    md = (data / "proj" / "_audit" / "audit_proj.md").read_text()
    assert "| example_org | [2/3](#sm-example_org) |" in md
    anchor = md.index('<a id="sm-example_org"></a>')
    assert md.index("## all spiders") < anchor  # the section comes last
    block = md[anchor:]
    assert block.index("Given (2):") < block.index("Not given (1):")
    html = render_dashboard("proj", rows, [])
    assert '<a href="#sm-example_org">2/3</a>' in html
    pos = html.index('id="sm-example_org"')
    # top-level: not inside a (collapsed) <details> drawer
    assert html.rfind("</details>", 0, pos) > html.rfind("<details", 0, pos)
    assert pos < html.index("Notes &amp; definitions")


def test_discovery_runs_once_per_host(data, monkeypatch):
    # no robots on disk → discover (robots.txt, then /sitemap.xml) ONCE; the
    # /sitemap.xml probe doubles as the manifest, so it isn't fetched twice
    root = "https://example.org/sitemap.xml"
    fake = FakeFetch({root: _index_xml(_kids("post", "page"))})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert fake.calls == ["https://example.org/robots.txt", root]
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)
    monkeypatch.setattr(sitemaps, "fetch", _no_network)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)


# ------------------------------------------- sitemap listing: politeness fixes
ROOT = "https://example.org/sitemap.xml"
ROBOTS = "https://example.org/robots.txt"


def _cache(data):
    return data / "proj" / "_audit" / "sitemap_cache"


def _cached_page(data, name, text, url=None):
    d = _cache(data) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "page.html").write_text(text)
    if url:
        (d / "url.txt").write_text(url)


def test_robots_on_disk_listing_none_not_refetched(data, monkeypatch):
    # robots.txt on disk lists no sitemap and the spider's earlier /sitemap.xml
    # probe is cached: the listing answers from disk with ZERO fetches
    _robots_snapshot(data, [])
    _cached_page(data, "example_org_smprobe", _index_xml(_kids("post", "page")))
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)
    # nothing cached for /sitemap.xml: only it is fetched — never robots.txt
    fake = FakeFetch({ROOT: _index_xml(_kids("post", "page"))})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"), spider="s2")
    assert fake.calls == []  # the host's declared.json from the first row
    (_cache(data) / "_host" / "example.org" / "declared.json").unlink()
    (_cache(data) / "example_org_smprobe").rename(_cache(data) / "gone")
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert fake.calls == [ROOT]
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)


def test_coverage_fetch_reused_by_listing(data, monkeypatch):
    # a USE_SITEMAP spider without crawl-recorded counts: the coverage fetch
    # pulls the root index into the spider cache; the listing reuses that copy
    kids = _kids("post", "page")
    pages = {INDEX: _index_xml(kids), ROBOTS: f"Sitemap: {INDEX}\n"}
    pages.update(
        {
            k: "<urlset><url><loc>https://example.org/a</loc></url></urlset>"
            for k in kids
        }
    )
    fake = FakeFetch(pages)
    monkeypatch.setattr(sitemaps, "fetch", fake)
    _robots_snapshot(data, [INDEX])
    ctx = _ctx(data, no_fetch=False)
    ctx.should_fetch = lambda n: True
    row = score_spider("example_org", _sp(start_urls=kids[:1]), _corpus(1), ctx)
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)
    assert sorted(fake.calls) == sorted(set(fake.calls))  # no URL twice
    assert fake.calls.count(INDEX) == 1
    # an older cache (no url.txt) can't be tied to a URL: never guessed —
    # the declared index is fetched once into the host cache, then never again
    for d in _cache(data).glob("example_org_[0-9]*"):
        (d / "url.txt").unlink()
    for d in (_cache(data) / "_host").glob("*/sm_*"):
        for f in d.iterdir():
            f.unlink()
        d.rmdir()
    fake = FakeFetch({INDEX: _index_xml(kids)})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    row = _yes_row(data, _ctx(data, no_fetch=False), kids[:1])
    assert fake.calls == [INDEX]
    monkeypatch.setattr(sitemaps, "fetch", _no_network)
    row = _yes_row(data, _ctx(data, no_fetch=False), kids[:1])
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 2)


def test_given_index_under_other_url_counts_children(data):
    # start_url /sitemap.xml serves the same index robots declares as
    # /sitemap_index.xml: its cached copy is an index → its children are given
    kids = _kids("post", "page", "event")
    _robots_snapshot(data, [INDEX])
    cache = str(_cache(data))
    sitemaps._save_manifest(INDEX, cache, _index_xml(kids))
    _cached_page(data, "example_org_0", _index_xml(kids), url=ROOT)
    row = _yes_row(data, _ctx(data), [ROOT])
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (3, 3)
    assert all(e["in_index"] for e in row["sitemap_list"])


def test_failed_discovery_not_stored_as_none(data, monkeypatch):
    fake = FakeFetch()  # robots.txt and /sitemap.xml both fail
    monkeypatch.setattr(sitemaps, "fetch", fake)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert row["sitemaps_total"] == "?"
    assert "discovery failed" in row["sitemaps_note"]
    host = _cache(data) / "_host" / "example.org"
    assert not (host / "declared.json").exists()
    assert (host / "declared.failed.json").exists()
    # a later default run doesn't retry; --fetch-all does
    monkeypatch.setattr(sitemaps, "fetch", _no_network)
    row = _yes_row(data, _ctx(data, no_fetch=False), _kids("post"))
    assert row["sitemaps_total"] == "?"
    fake = FakeFetch({ROBOTS: "User-agent: *\nDisallow:\n", ROOT: "<html>404</html>"})
    monkeypatch.setattr(sitemaps, "fetch", fake)
    row = _yes_row(data, _ctx(data, no_fetch=False, fetch_all=True), _kids("post"))
    # robots.txt read and /sitemap.xml answered without a sitemap: a fact
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (1, 1)
    assert json.loads((host / "declared.json").read_text())["sitemaps"] == []
    assert not (host / "declared.failed.json").exists()


def test_cache_buster_duplicates_not_double_counted(data):
    kids = _kids("post", "page", "event")
    _robots_snapshot(data, [INDEX])
    sitemaps._save_manifest(INDEX, str(_cache(data)), _index_xml(kids))
    extra = "https://example.org/news-sitemap.xml"
    given = [kids[0], kids[1], extra]
    given += [u + "?v=2" for u in given]
    row = _yes_row(data, _ctx(data), given)
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (3, 4)
    not_listed = [e["url"] for e in row["sitemap_list"] if not e["in_index"]]
    assert not_listed == [extra]


def test_paged_extras_stay_distinct(data):
    _robots_snapshot(data, [INDEX])
    sitemaps._save_manifest(INDEX, str(_cache(data)), _index_xml(_kids("post")))
    paged = [f"https://example.org/news.xml?page={i}" for i in (1, 2)]
    row = _yes_row(data, _ctx(data), paged)
    assert (row["sitemaps_given"], row["sitemaps_total"]) == (2, 3)
