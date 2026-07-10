"""Unit tests for the quality dashboard — pure render + command builders.

No filesystem, no network, no DB (the crawl_audit/compliance engines' no-drift correctness is
covered by the byte-diff acceptance checks in docs/plans/quality-audit-tool.md and
quality-dashboard.md, not here). These test the interactive HTML projection in isolation.
"""

import pytest

from core.quality.dashboard import dupe_command, bulk_dedupe_command, render_dashboard

pytestmark = pytest.mark.unit


def test_dupe_command():
    assert (
        dupe_command("gscc", "rmi_org")
        == "./scrapai dedupe --project gscc --only rmi_org"
    )


def test_bulk_dedupe_command():
    assert (
        bulk_dedupe_command("gscc", ["a", "b", "c"])
        == "./scrapai dedupe --project gscc --only a b c"
    )


def _cov_rows():
    return [
        {
            "spider": "rmi_org",
            "status": "ok",
            "sitemap": "yes",
            "eligible": "100",
            "sitemap_total": 100,
            "scraped": 100,
            "rows": 100,
            "versions": 0,
            "files": 1,
            "content_med": 5000,
            "content_pct": 99,
            "coverage_pct": 100,
            "true_dupes": 0,
            "dup_pct": 0,
            "stale": "",
            "flags": "",
        },
        {
            "spider": "dupey_org",
            "status": "manual review",
            "sitemap": "no",
            "eligible": "-",
            "sitemap_total": "-",
            "scraped": 50,
            "rows": 62,
            "versions": 0,
            "files": 2,
            "content_med": 900,
            "content_pct": 80,
            "coverage_pct": "",
            "true_dupes": 12,
            "dup_pct": 20,
            "stale": "⚠ 40d",
            "flags": "thin? 0.9k",
        },
    ]


def _compl_rows():
    return [
        {
            "domain": "rmi.org",
            "checked": "2026-06-01",
            "failed": False,
            "source": "live",
            "crawl_emoji": "🟢",
            "crawl_sev": 2,
            "crawl_reasons": ["nothing blocks our crawl"],
            "reuse_emoji": "🟡",
            "reuse_sev": 3,
            "reuse_reasons": ["licence restricts reuse"],
            "facet": "open",
            "robots_cell": "✓ 0/5 blocked",
            "pdf_cell": "ok",
            "blocked_paths": [],
            "pdf_evidence": [],
            "comments": [],
            "notes": "AI-reuse reserved",
            "llms": {"present": True, "verdict": "allows"},
            "license": "CC BY-NC 4.0",
            "license_scope": "home",
            "license_url": "https://rmi.org/",
            "license_quote": "You may reuse…",
            "license_low": False,
            "license_review": False,
            "all_rights_reserved": True,
            "bespoke": None,
            "copyright": "© 2024 RMI",
            "copyright_holder": "RMI",
            "copyright_year": "2024",
            "copyright_discrepancy": None,
            "robots_present": True,
            "ai_evidence": [
                {
                    "label": "TDMRep reservation file present",
                    "url": "https://rmi.org/.well-known/tdmrep.json",
                }
            ],
            "clauses": [
                (
                    "Anti-scraping clause",
                    "https://rmi.org/terms",
                    "you may not scrape this site",
                )
            ],
            "cross_check": {},
        }
    ]


def _pdf_spiders():
    return [
        {
            "spider": "rmi_org",
            "total": 3,
            "unique": 3,
            "hosts": [
                {
                    "host": "s3.amazonaws.com",
                    "count": 2,
                    "sample": "https://s3.amazonaws.com/a.pdf",
                    "urls": [
                        "https://s3.amazonaws.com/a.pdf",
                        "https://s3.amazonaws.com/b.pdf",
                    ],
                },
                {
                    "host": "example.org",
                    "count": 1,
                    "sample": "https://example.org/b.pdf",
                    "urls": ["https://example.org/b.pdf"],
                },
            ],
        },
        {"spider": "empty_org", "total": 0, "unique": 0, "hosts": []},
    ]


def test_render_basic_structure():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    # self-contained: inline style/script, no external assets
    assert "<style>" in html and "<script>" in html
    assert 'src="http' not in html
    # compliance + pdf lens tables, and the coverage all-spiders table
    for t in ('data-tab="compliance"', 'data-tab="pdfs"', 'data-tab="cov-all"'):
        assert t in html
    assert 'class="meter"' in html  # bar-meters
    assert "fx-row" in html and "fx-detail" in html and "data-type=" in html


def test_coverage_mirrors_md_sections():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    # audit-MD sections, in the coverage tab
    assert "Status labels" in html  # summary table
    assert "Duplicate rows (" in html  # dupes section
    assert "manual review (" in html
    assert "full sortable grid (" in html  # all-spiders grid (collapsed)
    assert '<details class="drawer allgrid">' in html  # …and it is collapsed by default
    assert 'class="healthstrip"' in html  # at-a-glance status bar
    assert "Notes &amp; definitions" in html  # definitions drawer
    # the MD columns the user built are present as columns
    for col in (">total<", ">eligible<", ">scraped<", ">stale<", ">true dupes<"):
        assert col in html
    # per-status fix-hint intro is shown
    assert 'class="fixhint"' in html


def test_styled_tooltips_and_plain_surface():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    # the styled-tooltip primitive: data-tip everywhere, the popover engine present, native title
    # kept only as the SR/no-JS fallback (paired with data-tip on the same element)
    assert html.count("data-tip=") > 20
    assert "class='fx-tip'" in html or "'fx-tip'" in html  # runtime popover element
    assert ".fx-tip{" in html  # its style
    # plain-language surface
    assert "Each row is a website" in html  # coverage tab intro
    assert "may we legally" in html  # compliance tab intro
    assert "Two independent axes" in html  # the core concept, visible
    assert "don’t fetch / can’t reuse" in html  # plain compliance legend
    # decluttered walls: status summary shows the short lead, full meaning lives in the chip tip
    assert ">in short<" in html  # trimmed summary column
    assert 'details class="howto"' in html  # fix-hint folded into a collapse


def test_tooltip_values_xss_safe():
    cov = [
        {
            "spider": "x",
            "status": "ok",
            "sitemap": "yes",
            "eligible": "1",
            "sitemap_total": 1,
            "scraped": 1,
            "rows": 1,
            "versions": 0,
            "files": 1,
            "content": 1,
            "content_pct": 100,
            "coverage_pct": 100,
            "true_dupes": 0,
            "dup_pct": 0,
            "stale": "",
            "flags": "<img src=x onerror=alert(1)>",
        }
    ]
    html = render_dashboard("p", cov, [], [])
    assert "<img src=x onerror=alert(1)>" not in html  # never raw
    assert (
        "&lt;img src=x onerror=alert(1)&gt;" in html
    )  # escaped (incl. inside data-tip)


def test_select_and_bulk_command():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    assert 'class="fx-check"' in html  # checkboxes on the Duplicate-rows table
    assert 'id="selbar-cov-dupes"' in html and 'data-project="gscc"' in html
    # the dupey spider surfaces its dedupe command in the Duplicate-rows section
    assert "./scrapai dedupe --project gscc --only dupey_org" in html


def test_per_status_action_commands():
    rows = [
        {
            "spider": "gov_uk",
            "status": "incomplete",
            "sitemap": "found",
            "eligible": "497",
            "sitemap_total": 868,
            "scraped": 237,
            "rows": 237,
            "true_dupes": 0,
            "versions": 0,
            "dup_pct": 0,
            "files": 1,
            "content": 237,
            "content_pct": 93,
            "content_med": 900,
            "coverage_pct": 48,
            "stale": "",
            "flags": "thin? 0.9k",
        },
        {
            "spider": "small_org",
            "status": "too few pages",
            "sitemap": "no",
            "eligible": "-",
            "sitemap_total": "-",
            "scraped": 40,
            "rows": 40,
            "true_dupes": 0,
            "versions": 0,
            "dup_pct": 0,
            "files": 1,
            "content": 40,
            "content_pct": 100,
            "content_med": 2000,
            "coverage_pct": "",
            "stale": "",
            "flags": "small/partial",
        },
        {
            "spider": "news_org",
            "status": "manual review",
            "sitemap": "found",
            "eligible": "1027",
            "sitemap_total": 1030,
            "scraped": 1119,
            "rows": 1119,
            "true_dupes": 0,
            "versions": 0,
            "dup_pct": 0,
            "files": 1,
            "content": 1119,
            "content_pct": 100,
            "content_med": 3000,
            "coverage_pct": 109,
            "stale": "",
            "flags": "sitemap-drift (0/1030)",
        },
    ]
    html = render_dashboard("kb", rows, [], [])
    # each problem section has checkboxes and a select-bar in the right mode
    assert 'id="selbar-cov-incomplete"' in html and 'data-mode="repair"' in html
    assert 'id="selbar-cov-too-few-pages"' in html and 'data-mode="crawl"' in html
    assert 'id="selbar-cov-manual-review"' in html and 'data-mode="review"' in html
    assert html.count('class="fx-check"') >= 3
    # the JS knows how to build each group's command
    # both action modes emit the UNIFIED /spider-review (it absorbed /spider-repair)
    assert html.count("/spider-review ") >= 2 and "./scrapai crawl " in html
    assert "/spider-repair" not in html


def test_fix_hint_is_bulleted():
    rows = [
        {
            "spider": "x",
            "status": "incomplete",
            "sitemap": "found",
            "eligible": "10",
            "sitemap_total": 10,
            "scraped": 4,
            "rows": 4,
            "true_dupes": 0,
            "versions": 0,
            "dup_pct": 0,
            "files": 1,
            "content": 4,
            "content_pct": 100,
            "content_med": 900,
            "coverage_pct": 40,
            "stale": "",
            "flags": "",
        }
    ]
    html = render_dashboard("kb", rows, [], [])
    # the how-to-fix is a lead paragraph + a bullet list, not one blob
    assert '<details class="howto"><summary>how to fix</summary>' in html
    assert "<ul><li>" in html  # structured, not a paragraph blob


def test_compliance_evidence_rendered():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    assert "rmi.org" in html
    assert "CC BY-NC 4.0" in html
    assert "You may reuse" in html  # licence quote
    assert "Anti-scraping clause" in html  # quoted clause block


def test_pdf_flat_and_empty_spider_omitted():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    assert "s3.amazonaws.com" in html
    assert "empty_org" not in html  # zero-PDF spider produces no rows


def test_pdf_urls_lazy_seeded_sample():
    # URLs are NOT in the initial DOM — they live in the #pdf-urls island and are built on expand.
    # Only a SEEDED sample of ≤5 URLs per host is embedded (keeps the tab light); deterministic.
    import json

    urls = [f"https://s3.amazonaws.com/doc{i}.pdf" for i in range(30)]
    spiders = [
        {
            "spider": "rmi_org",
            "total": 30,
            "unique": 30,
            "hosts": [
                {
                    "host": "s3.amazonaws.com",
                    "count": 30,
                    "sample": urls[0],
                    "urls": urls,
                }
            ],
        }
    ]
    html = render_dashboard("gscc", [], [], spiders)
    html2 = render_dashboard("gscc", [], [], spiders)
    assert html == html2  # seeded → reproducible
    assert 'id="pdf-urls"' in html  # JSON island present
    assert 'class="pdfurls" data-n="5"' in html  # only 5 sampled, not 30
    assert "random sample of 30" in html  # labelled as a sample
    assert html.count("<a href=") == 0  # no PDF links in the initial DOM
    blob = html.split('id="pdf-urls">', 1)[1].split("</script>", 1)[0]
    blob = blob.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
    assert len(list(json.loads(blob).values())[0]) == 5  # island carries exactly 5


def test_pdf_share_floor_and_slider():
    # ONE gate: a host's share of the org's PDFs. Below the render floor (0.1%) → not rendered;
    # the slider gates the rest. No hard 1-link rule.
    # org total is recomputed from host counts → 1999 + 1 = 2000; tinycite = 0.05% < 0.1% floor
    spiders = [
        {
            "spider": "big_org",
            "total": 2000,
            "unique": 2000,
            "hosts": [
                {
                    "host": "bigrepo.com",
                    "count": 1999,
                    "sample": "https://bigrepo.com/0.pdf",
                    "urls": ["https://bigrepo.com/a.pdf", "https://bigrepo.com/b.pdf"],
                },
                {
                    "host": "tinycite.org",
                    "count": 1,
                    "sample": "https://tinycite.org/x.pdf",
                    "urls": ["https://tinycite.org/x.pdf"],
                },
            ],
        }
    ]
    html = render_dashboard("kb", [], [], spiders)
    assert 'data-host="bigrepo.com"' in html  # 5% share → rendered
    assert 'data-host="tinycite.org"' not in html  # 0.05% < 0.1% floor → not rendered
    assert (
        "data-share=" in html and 'class="pdf-share"' in html
    )  # per-host share + the single slider
    assert ">sample</th>" not in html  # sample column dropped (lighter)


def test_pdf_storage_hosts_flagged_only():
    from core.quality.dashboard import _is_storage_host

    assert _is_storage_host("iea.blob.core.windows.net") and _is_storage_host(
        "files.wri.org"
    )
    assert not _is_storage_host("energy.gov")
    spiders = [
        {
            "spider": "iea_org",
            "total": 10,
            "unique": 10,
            "hosts": [
                {
                    "host": "files.iea.org",
                    "count": 2,
                    "sample": "https://files.iea.org/a.pdf",
                    "urls": [
                        "https://files.iea.org/a.pdf",
                        "https://files.iea.org/b.pdf",
                    ],
                },
                {
                    "host": "energy.gov",
                    "count": 8,
                    "sample": "https://energy.gov/0.pdf",
                    "urls": [f"https://energy.gov/{i}.pdf" for i in range(8)],
                },
            ],
        }
    ]
    html = render_dashboard("kb", [], [], spiders)
    # storage host is FLAGGED ☁ but not special-cased in the gate (no keep/pin/exempt attribute)
    assert 'data-host="files.iea.org"' in html and 'class="stor"' in html
    assert "data-storage" not in html


def test_pdf_include_list_selbar():
    html = render_dashboard("gscc", _cov_rows(), _compl_rows(), _pdf_spiders())
    assert 'id="selbar-pdfs"' in html and 'data-mode="pdf-json"' in html
    assert "save page with choices" in html and "download pdf_hosts.json" in html
    assert (
        'data-spider="rmi_org"' in html
    )  # rows carry spider+host for the {spider:{keep:[…]}} JSON


def test_coverage_detail_flag_targeted():
    import re
    from core.quality.dashboard import _coverage_detail

    r = {
        "spider": "dupey_org",
        "status": "manual review",
        "flags": "thin? 0.9k",
        "scraped": 50,
        "rows": 62,
        "versions": 0,
        "files": 2,
        "content_med": 900,
        "eligible": "-",
        "sitemap_total": "-",
        "true_dupes": 0,
        "dup_pct": 0,
    }
    d = _coverage_detail("gscc", r)  # the ROW expand, in isolation
    visible = re.sub(
        r"<details.*?</details>", "", d, flags=re.S
    )  # strip the tucked-away prose
    assert "thin?" in visible  # the row's ONLY flag is shown
    assert "CF site may be a block" not in visible  # other flags' prose not dumped
    assert (
        'class="fullguide"' in d and "CF site may be a block" in d
    )  # full guidance kept, collapsed


def test_escapes_untrusted_values():
    cov = [
        {
            "spider": "<script>alert(1)</script>",
            "status": "ok",
            "sitemap": "yes",
            "eligible": "1",
            "sitemap_total": 1,
            "scraped": 1,
            "rows": 1,
            "versions": 0,
            "files": 1,
            "content_med": 100,
            "content_pct": 100,
            "coverage_pct": 100,
            "true_dupes": 0,
            "dup_pct": 0,
            "stale": "",
            "flags": "<img src=x onerror=alert(1)>",
        }
    ]
    compl = _compl_rows()
    compl[0]["clauses"] = [
        ("Anti-scraping clause", "https://x/t", "<script>evil()</script>")
    ]
    html = render_dashboard("p", cov, compl, [])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "<script>evil()</script>" not in html
    assert "&lt;script&gt;evil()&lt;/script&gt;" in html


def test_found_empty_sitemap_flag_rendered():
    """A discovered-but-unusable sitemap surfaces its flag + the skip-note guidance (D)."""
    rows = [
        {
            "spider": "who_int",
            "status": "manual review",
            "sitemap": "found",
            "eligible": "0",
            "sitemap_total": 0,
            "scraped": 500,
            "rows": 500,
            "versions": 0,
            "files": 1,
            "content_med": 4000,
            "content_pct": 99,
            "coverage_pct": "",
            "true_dupes": 0,
            "dup_pct": 0,
            "stale": "",
            "flags": "found sitemap empty (0 usable URLs)",
        }
    ]
    html = render_dashboard("p", rows, [], [])
    assert "found sitemap empty (0 usable URLs)" in html
    assert (
        "audit_sitemap_skip.json" in html
    )  # glossary points at the skip-note workflow


def test_compliance_robots_llms_columns():
    html = render_dashboard("gscc", [], _compl_rows(), [])
    assert ">robots</th>" in html and ">llms</th>" in html  # dedicated columns
    assert '<a href="https://rmi.org/robots.txt"' in html  # clickable robots.txt ✓
    assert '<a href="https://rmi.org/llms.txt"' in html  # clickable llms.txt
    # the domain cell no longer links to robots.txt
    assert (
        '"https://rmi.org/robots.txt" target="_blank" rel="noopener">rmi.org<'
        not in html
    )


def test_ai_evidence_drawer_has_source_links():
    html = render_dashboard("gscc", [], _compl_rows(), [])
    assert "AI signals" in html
    assert '<a href="https://rmi.org/.well-known/tdmrep.json"' in html  # receipt link
    assert "TDMRep reservation file present" in html


def test_pdf_grouped_by_org():
    html = render_dashboard("gscc", [], [], _pdf_spiders())
    assert (
        'class="fx-group"' in html and 'data-group="rmi_org"' in html
    )  # per-org sections
    assert "1 hosts" in html or "hosts</span>" in html  # group header summary
    assert 'data-host="s3.amazonaws.com"' in html  # host rows under the group
    assert ">spider</th>" not in html  # redundant column dropped


def test_assess_reuse_factual_no_ai_kb():
    from core.quality.compliance_capture import assess_reuse

    rec = {
        "ai": {"tdm_reserved": True},
        "license": "CC BY 4.0",
        "license_source": "home",
    }
    _, emoji, reasons = assess_reuse(rec)
    joined = " ".join(reasons)
    assert (
        "knowledge-base" not in joined
        and "AI KB" not in joined
        and "retrieval/RAG" not in joined
    )
    assert "machine-readable AI/TDM reservation" in joined  # the fact remains


def test_ai_training_needs_anchor():
    """Bare 'training' no longer flags a no-AI-training clause; it needs an AI/ML anchor."""
    from core.quality.compliance_capture import ai_training_prohibition as ait

    # false positives — 'training' with no AI/ML context
    assert not ait(
        "UNFCCC does not charge a fee at any stage of its recruitment process "
        "(application, interview, processing, training, visa or other fee)."
    )
    assert not ait("Registration for our staff training courses is not permitted.")
    # true positives — an AI/ML anchor beside 'train'
    assert ait("The content may not be used to train any AI model.")
    assert ait(
        "You are prohibited from using this material to train machine learning systems."
    )
    # a standalone unambiguous term still flags without 'train'
    assert ait("This material must not be used for machine learning.")


def test_meter_invert():
    """Lower-is-better metrics (null-date %, thin %) colour by 100-p; default unchanged."""
    from core.quality.dashboard import _meter

    assert "bar green" in _meter(95) and "bar red" in _meter(5)  # higher-is-better
    assert "bar red" in _meter(95, invert=True)  # 95% null dates = bad
    assert "bar green" in _meter(5, invert=True)  # 5% null dates = good
    assert ">95%<" in _meter(95, invert=True)  # label still shows p


def test_license_low_data_key_is_clean():
    """The ⚠ warn-span (which contains quotes) must never leak into the sort key —
    it used to terminate data-key early and break the <td> markup."""
    import re

    compl = _compl_rows()
    compl[0]["license_low"] = True
    html = render_dashboard("p", [], compl, [])
    m = re.search(r'<td data-key="([^"]*)">[^<]*cc by-nc', html, re.I)
    assert m, "licence cell missing"
    assert "<" not in m.group(1) and "data-tip" not in m.group(1)
    assert m.group(1) == "cc by-nc 4.0"
    assert 'class="warn"' in html  # ⚠ still displayed


def test_link_rejects_non_http_schemes():
    from core.quality.dashboard import _link

    assert "<a" not in _link("javascript:alert(1)", "terms")  # XSS-on-click guard
    assert "<a" not in _link("/relative/terms", "terms")
    assert '<a href="https://x.org/terms"' in _link("https://x.org/terms", "terms")


def test_unchecked_rows_have_sortable_cells():
    """Unchecked domains render all 9 cells with data-keys (no colspan) so the sorter
    never compares 'null' strings against misaligned columns."""
    import re

    rows = [{"domain": "unchecked.example", "unchecked": True}]
    html = render_dashboard("p", [], rows, [])
    row = re.search(
        r'<tr class="fx-row"[^>]*data-facet="not-checked".*?</tr>', html, re.S
    )
    assert row, "unchecked row missing"
    assert "colspan" not in row.group(0)
    assert row.group(0).count("<td") == 9
    assert 'data-key="unchecked.example"' in row.group(0)


def test_llms_link_uses_recorded_path():
    compl = _compl_rows()
    compl[0]["llms"] = {
        "present": True,
        "verdict": "allows",
        "path": "/.well-known/llms.txt",
    }
    html = render_dashboard("p", [], compl, [])
    assert '<a href="https://rmi.org/.well-known/llms.txt"' in html


def test_overview_attention_date_null_is_informational():
    from core.quality.overview import _flags

    base = {
        "rows": 100,
        "config_found": True,
        "fields": [],
        "thin_pct": 0,
        "zero_yield_rules": [],
        "degenerate": [],
        "offdomain": 0,
        "suspicious_dates": 0,
        "n_dated": 30,
        "null_date_pct": 70,
    }
    r = _flags(dict(base), 200)
    assert "date-null 70%" in r["flags"]
    assert r["attention"] == 0  # date-null ALONE never flags
    r2 = _flags(dict(base, thin_pct=40), 200)
    assert r2["attention"] == 1  # a hard token still does


def test_overview_parse_date_mixed_tz_comparable():
    """A corpus can mix naive and tz-aware stamps; min/max across them must not raise
    (found live on the thinktanks project)."""
    from core.quality.overview import _parse_date

    naive = _parse_date("2024-01-05 10:00:00")
    aware = _parse_date("2024-01-05T10:00:00+02:00")
    assert naive and aware
    assert min(naive, aware)  # comparable → no TypeError
    assert aware.tzinfo is None


def test_overview_unknown_project_creates_nothing(tmp_path, monkeypatch):
    """A typo'd project name must error out, not scaffold data/<typo>/_audit/ with
    empty reports."""
    import os
    import pytest
    from core.quality import overview

    monkeypatch.setattr(overview, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(overview._env, "project_exists", lambda p: False)
    with pytest.raises(SystemExit):
        overview.run("no_such_project", None)
    assert not os.path.exists(tmp_path / "no_such_project")


def test_coverage_detail_no_duplicate_unique():
    from core.quality.dashboard import _coverage_detail

    r = {
        "spider": "x",
        "status": "ok",
        "flags": "",
        "scraped": 50,
        "rows": 62,
        "versions": 0,
        "files": 2,
        "content_med": 900,
        "eligible": "-",
        "sitemap_total": "-",
        "true_dupes": 0,
        "dup_pct": 0,
    }
    d = _coverage_detail("p", r)
    assert "unique" not in d  # was `scraped` printed twice


def test_empty_project():
    html = render_dashboard("empty", [], [], [])
    assert "No spiders" in html
    assert "quality audit" in html
    # no per-row dedupe command when there are no dupey spiders (the regenerate-help
    # legitimately documents the `--only <spider>` FLAG, so match the command itself)
    assert "dedupe --project empty --only" not in html.split("<script>")[0]


# --- PDF row-model surfaces ----------------------------------------------------


def test_coverage_pdf_column_and_detail():
    from core.quality.dashboard import render_dashboard as rd

    rows = [
        {
            "spider": "docs_org",
            "status": "ok",
            "sitemap": "yes",
            "eligible": "100",
            "sitemap_total": 100,
            "scraped": 95,
            "pdf": 214,
            "pdf_own": 176,
            "pdf_ext": 38,
            "unique": 309,
            "rows": 320,
            "versions": 0,
            "files": 1,
            "content_med": 5000,
            "content_pct": 99,
            "coverage_pct": 95,
            "true_dupes": 11,
            "dup_pct": 3,
            "stale": "",
            "flags": "",
        }
    ]
    html = rd("p", rows, [], [])
    assert ">pdf</th>" in html  # the HTML-vs-PDF column
    assert "214 (38 ext)" in html  # split rendered
    assert "own 176" in html and "external 38" in html  # expand detail
    # dupes tables show the true total unique, not the HTML-only scraped
    assert 'data-key="pdf"' in html


def test_pdf_only_spider_renders_na_content():
    from core.quality.dashboard import render_dashboard as rd

    rows = [
        {
            "spider": "repo_org",
            "status": "too few pages",
            "sitemap": "no",
            "eligible": "-",
            "sitemap_total": "-",
            "scraped": 0,
            "pdf": 40,
            "pdf_own": 40,
            "pdf_ext": 0,
            "unique": 40,
            "rows": 40,
            "versions": 0,
            "files": 1,
            "content_med": 0,
            "content_pct": 0,
            "coverage_pct": "",
            "true_dupes": 0,
            "dup_pct": 0,
            "stale": "",
            "flags": "pdf-only (40)",
        }
    ]
    html = rd("p", rows, [], [])
    assert "pdf-only (40)" in html
    # content% must show n/a, not a red 0% meter, when there was no HTML at all
    import re

    row_html = re.search(
        r'<tr class="fx-row"[^>]*data-name="repo_org".*?</tr>', html, re.S
    ).group(0)
    assert "n/a" in row_html


def test_pdfs_tab_same_org_note():
    from core.quality.dashboard import render_dashboard as rd

    spiders = [
        {
            "spider": "x_org",
            "total": 10,
            "unique": 10,
            "own_unique": 176,
            "hosts": [
                {
                    "host": "iea.org",
                    "count": 10,
                    "sample": "https://iea.org/a.pdf",
                    "urls": ["https://iea.org/a.pdf"],
                }
            ],
        }
    ]
    html = rd("p", [], [], spiders)
    assert "176 same-org PDFs" in html
