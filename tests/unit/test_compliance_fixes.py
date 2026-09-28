"""Unit tests for the compliance_capture fixes: snapshot write-order (unreachable
domains get a failure marker, never a 'checked today' snapshot), the legacy-snapshot
AI-reuse recompute (stored concrete evidence is honoured when the derived keys are
absent), the llms.txt link honouring the recorded well-known path, and the report
outputs: a partial (some-paths) AI-bot restriction rendered as its own fact.
"""

import importlib
import json
import os

import pytest

from core.quality import compliance_capture as cc

# capture()'s stage module — monkeypatch targets live where the lookups happen
# (`cc.capture` is the function, so the module is fetched via importlib; mirrors
# the crawl_audit split, which repointed ca.fetch -> ca.sitemaps.fetch).
capture_mod = importlib.import_module("core.quality.compliance_capture.capture")

pytestmark = pytest.mark.unit

_HDRS_BLOCKED = {
    "fetch_status": "blocked",
    "x_robots_tag": None,
    "tdm_reservation": None,
    "tdm_policy": None,
    "noai": None,
}

ROBOTS = "User-agent: *\nDisallow: /admin/\n"
HOME = "<html><head><title>Example</title></head><body><p>Welcome to Example.</p></body></html>"


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(cc.store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(capture_mod, "header_signals", lambda url: dict(_HDRS_BLOCKED))
    return tmp_path


def test_unreachable_domain_gets_marker_not_snapshot(tmp_data, monkeypatch):
    monkeypatch.setattr(
        capture_mod, "inspect", lambda url, project, outdir, browser, proxy: None
    )
    status = cc.capture(
        "dead.example", "proj", browser=False, proxy="auto", update=False
    )
    assert status == "failed"
    org_base = cc.org_compliance_dir("proj", "dead.example")
    assert cc.existing_snapshots(org_base) == []  # NO dated 'checked' snapshot
    assert cc.has_capture_failed("proj", "dead.example")  # marker present
    assert not any(
        f.endswith(".tmp") for f in os.listdir(org_base)  # atomic marker write
    )


def test_reachable_domain_writes_snapshot_and_clears_marker(tmp_data, monkeypatch):
    def fake_inspect(url, project, outdir, browser, proxy):
        os.makedirs(outdir, exist_ok=True)
        if url.endswith("/robots.txt"):
            return ROBOTS
        if url.rstrip("/").endswith("live.example"):
            return HOME
        return None  # well-known probes 404

    monkeypatch.setattr(capture_mod, "inspect", fake_inspect)
    cc.mark_capture_failed("proj", "live.example", "old failure")
    status = cc.capture(
        "live.example", "proj", browser=False, proxy="auto", update=False
    )
    assert status == "ok"
    org_base = cc.org_compliance_dir("proj", "live.example")
    snaps = cc.existing_snapshots(org_base)
    assert len(snaps) == 1  # dated snapshot written
    assert not cc.has_capture_failed("proj", "live.example")  # marker cleared
    rec = json.load(open(os.path.join(org_base, snaps[0], "compliance.json")))
    assert rec["domain"] == "live.example"
    assert rec["robots"]["fetched"]


def test_failed_refresh_keeps_older_snapshot(tmp_data, monkeypatch):
    org_base = cc.org_compliance_dir("proj", "flaky.example")
    old = os.path.join(org_base, "2026-01-01")
    os.makedirs(old)
    with open(os.path.join(old, "compliance.json"), "w") as fh:
        json.dump({"domain": "flaky.example", "checked": "2026-01-01"}, fh)
    monkeypatch.setattr(
        capture_mod, "inspect", lambda url, project, outdir, browser, proxy: None
    )
    status = cc.capture(
        "flaky.example", "proj", browser=False, proxy="auto", update=True
    )
    assert status == "failed"
    assert cc.existing_snapshots(org_base) == ["2026-01-01"]  # history intact
    assert cc.has_capture_failed("proj", "flaky.example")


def test_capture_failed_rescued_from_crawl_robots(tmp_data):
    # A live-probe TOTAL failure (neither robots nor homepage) leaves only a marker — but when
    # the spider captured robots.txt at crawl time, the report falls back to that witness so the
    # domain is answered on the CRAWL axis '(via crawl)' instead of staying 'NOT CHECKED'; the
    # REUSE axis stays a review (homepage/licence genuinely unread → header probe marked blocked).
    from core.quality.compliance_capture import report as rpt

    dom = "walled.example"
    cc.mark_capture_failed(
        "proj", dom, "unreachable — neither robots.txt nor homepage fetched"
    )
    crawls = os.path.join(str(tmp_data), "proj", cc.store.slug(dom), "crawls")
    os.makedirs(crawls)
    with open(os.path.join(crawls, "robots_01012026.txt"), "w") as fh:
        fh.write(ROBOTS)

    captured, unchecked, failures = rpt.build_report_data("proj")

    assert dom in captured  # promoted out of NOT CHECKED
    _, _, rec = captured[dom]
    assert rec["robots"]["source"] == "crawl-capture"
    assert rec["robots"]["fetched"]
    assert rec["http_headers"]["fetch_status"] == "blocked"  # reuse stays a review
    assert dom not in unchecked
    assert all(f.get("domain") != dom for f in failures)  # dropped from the banner


def test_capture_failed_without_crawl_witness_stays_unchecked(tmp_data):
    # No crawl-time robots witness → the rescue must NOT fabricate a result; the domain stays a
    # genuine capture-failure so it's still flagged for investigation.
    from core.quality.compliance_capture import report as rpt

    dom = "dark.example"
    cc.mark_capture_failed("proj", dom, "unreachable")
    captured, unchecked, failures = rpt.build_report_data("proj")
    assert dom not in captured
    assert any(f.get("domain") == dom for f in failures)


def test_summary_agrees_with_report_on_rescue(tmp_data):
    # The audit's per-spider compliance summary (feeds audit_<project>.md) must AGREE with
    # build_report_data: a capture-failed domain rescued by its crawl-captured robots is NOT
    # reported 'failed', and the crawl axis is answered.
    from core.quality.crawl_audit.engine import compliance_summary

    dom = "walled.example"
    cc.mark_capture_failed(
        "proj", dom, "unreachable — neither robots.txt nor homepage fetched"
    )
    crawls = os.path.join(str(tmp_data), "proj", cc.store.slug(dom), "crawls")
    os.makedirs(crawls)
    with open(os.path.join(crawls, "robots_01012026.txt"), "w") as fh:
        fh.write(ROBOTS)

    summary = compliance_summary("proj", {"walled_example": {"host": dom}})
    e = summary["walled_example"]
    assert e["failed"] is False  # rescued via crawl-captured robots → not a failure
    assert e["access"] is not None  # crawl axis answered


def test_summary_still_failed_without_witness(tmp_data):
    # No crawl-time robots witness → the summary must still report 'failed' (nothing fabricated).
    from core.quality.crawl_audit.engine import compliance_summary

    dom = "dark.example"
    cc.mark_capture_failed("proj", dom, "unreachable")
    summary = compliance_summary("proj", {"dark_example": {"host": dom}})
    assert summary["dark_example"]["failed"] is True


def _seed_snapshot(tmp_path, org, ai_block):
    d = os.path.join(str(tmp_path), "proj", "_audit", "compliance", org, "2026-01-01")
    os.makedirs(d)
    rec = {
        "domain": org.replace("_", "."),
        "checked": "2026-01-01",
        "robots": {},
        "legal_pages": [],
        "ai": ai_block,
    }
    with open(os.path.join(d, "compliance.json"), "w") as fh:
        json.dump(rec, fh)
    return rec["domain"]


def test_legacy_snapshot_evidence_survives_recompute(tmp_data):
    # legacy format: concrete evidence present, derived keys ABSENT — a genuine
    # machine-readable reservation must not be recomputed away to False
    dom = _seed_snapshot(
        tmp_data,
        "legacy_org",
        {
            "tdmrep": {"present": True},
            "tdm_meta": None,
            "robots_meta": None,
            "site_wide_ai": True,
        },
    )
    captured, _, _ = cc.build_report_data("proj")
    ai = captured[dom][2]["ai"]
    assert ai["tdm_reserved"] is True  # derived from evidence
    assert ai["ai_reuse_reserved"] is True
    assert ai["site_wide_ai"] is True


def test_legacy_stale_flag_without_evidence_is_cleared(tmp_data):
    # legacy false positive: site_wide_ai=True but NO concrete evidence → recompute clears it
    dom = _seed_snapshot(
        tmp_data,
        "stale_org",
        {
            "tdmrep": {"present": False},
            "tdm_meta": None,
            "robots_meta": None,
            "site_wide_ai": True,
        },
    )
    captured, _, _ = cc.build_report_data("proj")
    ai = captured[dom][2]["ai"]
    assert ai["ai_reuse_reserved"] is False
    assert ai["site_wide_ai"] is False


def test_new_format_derived_keys_respected(tmp_data):
    # a new-format snapshot's explicit derived keys pass through untouched
    dom = _seed_snapshot(
        tmp_data,
        "new_org",
        {
            "tdm_reserved": True,
            "noai": False,
            "tdmrep": {"present": True},
            "site_wide_ai": True,
        },
    )
    captured, _, _ = cc.build_report_data("proj")
    ai = captured[dom][2]["ai"]
    assert ai["tdm_reserved"] is True and ai["ai_reuse_reserved"] is True


def test_llms_cell_uses_recorded_path():
    rec = {
        "_llms_display": {
            "present": True,
            "verdict": "present-unclear",
            "path": "/.well-known/llms.txt",
        }
    }
    assert cc.llms_cell(rec, "x.org") == "[✓](https://x.org/.well-known/llms.txt)"
    rec2 = {
        "_llms_display": {"present": True, "verdict": "prohibits"}
    }  # no path recorded
    assert cc.llms_cell(rec2, "x.org") == "[⚠✗](https://x.org/llms.txt)"


# ---- report outputs: partial AI-bot blocks, per-row failure isolation, failed rows ----


@pytest.fixture
def no_net(tmp_data, monkeypatch):
    """tmp_data + every fetch path raising, so a report/render test can never go online."""
    from core.quality.compliance_capture import fetch as fetch_mod
    from core.quality.compliance_capture import report as rpt

    def _boom(*a, **k):
        raise AssertionError("network access in a unit test")

    monkeypatch.setattr(capture_mod, "inspect", _boom)
    monkeypatch.setattr(capture_mod, "header_signals", _boom)
    monkeypatch.setattr(fetch_mod, "http_response_headers", _boom)
    monkeypatch.setattr(fetch_mod.urllib.request, "urlopen", _boom)
    monkeypatch.setattr(fetch_mod.subprocess, "run", _boom)
    monkeypatch.setattr(rpt, "DATA_DIR", str(tmp_data))  # write_report's output dir
    return tmp_data


def _md(project="proj"):
    from core.quality.compliance_capture import report as rpt

    return open(rpt.write_report(project), encoding="utf-8").read()


def _html(project="proj"):
    from core.quality.dashboard.compliance_tab import build_compliance_rows
    from core.quality.dashboard.render import render_dashboard

    return render_dashboard(project, [], build_compliance_rows(project))


# a stored snapshot is JSON: partial pairs come back as [bot, [paths]] LISTS
_PARTIAL_ONLY_AI = {
    "ai_bots_blocked": [],
    "ai_scrape_block": True,
    "ai_bot_signals": {
        "full": [],
        "partial": [
            ["GPTBot", ["/config", "/search", "/account$", "/account/"]],
            ["CCBot", ["/config", "/search", "/account$", "/account/"]],
        ],
        "allowed": [],
        "heuristic": [],
        "channel": [],
    },
}


def test_partial_formatter_accepts_lists_and_tuples():
    paths = ["/config", "/search", "/account$", "/account/"]
    as_tuples = {
        "ai_bot_signals": {"full": ["Bytespider"], "partial": [("GPTBot", paths)]}
    }
    as_lists = json.loads(json.dumps(as_tuples))  # the stored-snapshot shape
    assert isinstance(as_lists["ai_bot_signals"]["partial"][0], list)
    for ai in (as_tuples, as_lists):
        full, partial = cc.ai_bot_lines(ai)
        assert full == "AI crawlers disallowed in robots.txt: Bytespider"
        assert partial == (
            "AI crawlers restricted on some paths: GPTBot (/config, /search, /account$, …)"
        )
    # a bare-name entry (malformed) is tolerated, not a crash
    assert cc.ai_bot_lines({"ai_bot_signals": {"partial": ["CCBot"]}}) == (
        None,
        "AI crawlers restricted on some paths: CCBot",
    )
    assert cc.ai_bot_lines({}) == (None, None)


def test_partial_only_no_crash_and_rendered(no_net):
    dom = _seed_snapshot(no_net, "site01_example", dict(_PARTIAL_ONLY_AI))
    rec = cc.build_report_data("proj")[0][dom][2]

    # the verdict text says restricted, never "disallowed", for a partial-only site
    _, emoji, reasons = cc.assess_crawl(rec)
    assert emoji == "🟡"
    assert any("restricted on some paths" in r for r in reasons)
    assert not any("disallowed" in r for r in reasons)
    assert cc.crawl_notes(rec) == "AI-scrape restricted on some paths (robots)"

    html = _html()
    assert "No compliance snapshots yet" not in html
    assert "site01.example" in html
    assert (
        "AI crawlers restricted on some paths: GPTBot, CCBot (/config, /search, "
        "/account$, …)" in html
    )
    assert "AI crawlers disallowed in robots.txt" not in html

    md = _md()
    assert "AI-scrape restricted on some paths (robots)" in md  # notes cell
    assert (
        "- **AI crawlers restricted on some paths:** GPTBot, CCBot (`/config`, "
        "`/search`, `/account$`, …)" in md
    )  # crawl detail block
