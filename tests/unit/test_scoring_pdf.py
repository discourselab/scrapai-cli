"""score_spider under the PDF row model: HTML-only extraction/coverage math,
same-org/external split from the DB allowed_domains, the pdf-only flag, and
dupe math staying total. classify's thresholds are pinned unchanged."""

from types import SimpleNamespace

import pytest

from core.quality.crawl_audit import scoring
from core.quality.crawl_audit.scoring import ScoreContext, classify, score_spider

pytestmark = pytest.mark.unit


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(scoring, "crawl_stats_liveness", lambda p, s: None)
    monkeypatch.setattr(scoring, "crawl_ran", lambda p, s: True)
    monkeypatch.setattr(scoring, "crawl_stats_sitemap", lambda p, s: None)
    monkeypatch.setattr(scoring, "deltafetch_estimate", lambda p, s: 0)
    return ScoreContext(
        project="proj",
        opts=SimpleNamespace(no_browser_retry=True),
        cache_dir=str(tmp_path),
        state={"global": 0, "global_cap": 0, "per_cap": 0},
        skip={},
        notes={},
        has_cache=lambda n: False,
        mark_no_sitemap=lambda n: None,
        should_fetch=lambda n: False,
    )


def _sp(domains=("x.org",)):
    return {
        "start_urls": [],
        "use_sitemap": False,
        "rules": [],
        "deny": [],
        "n_rules": 0,
        "browser": False,
        "host": "x.org",
        "domains": list(domains),
    }


def _corpus(unique, content, pdf, pdf_hosts, rows=None, uc=None):
    return {
        "unique": unique,
        "content": content,
        "pdf": pdf,
        "pdf_hosts": pdf_hosts,
        "rows": rows if rows is not None else unique,
        "uc": uc if uc is not None else unique,
        "files": 1,
        "content_med": 3000,
        "newest": None,
        "urlset": set(),
        "_files": [],
    }


def test_pdf_rows_never_fake_extraction_broken(ctx):
    # 30 healthy articles + 70 pdf harvest rows: old math said content%=30 → broken
    row = score_spider(
        "sp", _sp(), _corpus(100, 30, 70, {"x.org": 50, "ext.org": 20}), ctx
    )
    assert row["status"] != "extraction broken"
    assert row["scraped"] == 30  # HTML articles only
    assert row["unique"] == 100  # totals stay total
    assert row["content_pct"] == 100
    assert row["pdf"] == 70
    assert row["pdf_own"] == 50 and row["pdf_ext"] == 20


def test_same_org_split_dot_boundary(ctx):
    row = score_spider(
        "sp",
        _sp(domains=["unep.org"]),
        _corpus(10, 5, 5, {"wedocs.unep.org": 3, "iea.org": 2}),
        ctx,
    )
    assert row["pdf_own"] == 3 and row["pdf_ext"] == 2


def test_split_falls_back_to_host_without_domains(ctx):
    sp = _sp(domains=[])
    row = score_spider("sp", sp, _corpus(10, 5, 4, {"x.org": 3, "ext.org": 1}), ctx)
    assert row["pdf_own"] == 3 and row["pdf_ext"] == 1


def test_pdf_only_spider_flagged_not_ran_empty(ctx):
    row = score_spider("sp", _sp(), _corpus(40, 0, 40, {"x.org": 40}), ctx)
    assert row["status"] == "too few pages"  # nothing to judge HTML on
    assert "pdf-only (40)" in row["flags"]
    assert "ran-empty" not in row["flags"] and "never-ran" not in row["flags"]
    assert row["scraped"] == 0


def test_dupes_math_stays_total(ctx):
    # 120 rows, 110 distinct (url,fp), 100 unique urls (of which 70 pdf)
    row = score_spider(
        "sp", _sp(), _corpus(100, 30, 70, {"x.org": 70}, rows=120, uc=110), ctx
    )
    assert row["true_dupes"] == 10  # rows - uc
    assert row["versions"] == 10  # uc - unique_total
    assert row["unique"] == 100


def test_classify_thresholds_pinned():
    """The classify() contract is untouched — args are now HTML-only by caller
    convention, but signature and thresholds are identical."""
    assert classify(None, 0, 0)[0] == "too few pages"
    assert classify(None, 100, 20)[0] == "extraction broken"  # <70% at scale
    assert classify(None, 5, 1)[0] == "extraction broken"  # <30% small
    assert classify(100, 80, 80)[0] == "incomplete"  # cov < 90
    assert classify(100, 95, 95)[0] == "ok"
    assert classify(None, 30, 30)[0] == "too few pages"  # <50 unverifiable


def test_review_note_never_promotes_empty_corpus(ctx):
    """A migrated/stale 'ok' note must not promote a spider with ZERO rows —
    the note vouches for data that isn't there (found live: migrated notes
    masked three ran-empty spiders as ok)."""
    ctx.notes["sp"] = {"status": "ok", "flag": "genuinely tiny"}
    c = _corpus(0, 0, 0, {}, rows=0, uc=0)
    row = score_spider("sp", _sp(), c, ctx)
    assert row["status"] == "too few pages"  # NOT promoted
    assert "reviewed-stale" in row["flags"]


def test_review_note_still_promotes_populated_corpus(ctx):
    ctx.notes["sp"] = {"status": "ok", "flag": "small site, verified"}
    row = score_spider("sp", _sp(), _corpus(40, 40, 0, {}), ctx)
    assert row["status"] == "ok"
    assert "✓ reviewed" in row["flags"]
