"""Page assembly — `render_dashboard()` (pure: no filesystem, no network; unit-tested)
and `write_dashboard()`, whose one side effect is `_audit/dashboard_<project>.html`."""

import os

from core.quality._env import DATA_DIR
from core.quality.crawl_audit import LEGEND

from .assets import CSS as _CSS, JS as _JS
from .compliance_tab import _compliance_table, build_compliance_rows
from .coverage_tab import (
    _all_spiders_table,
    _dupes_section,
    _health_strip,
    _notes_definitions,
    _status_section,
    _status_summary,
)
from .pdfs_tab import _ensure_pdf_exclude, _pdf_table
from .widgets import _esc, _md_strip


def render_dashboard(
    project, coverage_rows, compliance_rows, pdf_spiders, config_warnings=()
):
    """Render the full self-contained interactive HTML from the engines' structured data.
    Pure — no filesystem, no network; unit-testable. `coverage_rows` = crawl_audit rows;
    `compliance_rows` = build_compliance_rows() output; `pdf_spiders` = external_pdf spiders.
    """
    coverage_rows = coverage_rows or []
    compliance_rows = compliance_rows or []
    pdf_spiders = pdf_spiders or []

    n_spiders = len(coverage_rows)
    n_compl = sum(
        1 for e in compliance_rows if e.get("checked") is not None or e.get("failed")
    )
    n_pdf = sum(1 for s in pdf_spiders if s.get("total"))

    warn = ""
    if config_warnings:
        items = "".join("<li>" + _esc(_md_strip(w)) + "</li>" for w in config_warnings)
        warn = (
            '<div class="banner warnbanner"><b>Config warnings</b><ul>'
            + items
            + "</ul></div>"
        )
    fails = [e for e in compliance_rows if e.get("failed")]
    failbanner = ""
    if fails:
        doms = ", ".join("<code>" + _esc(e["domain"]) + "</code>" for e in fails)
        failbanner = (
            '<div class="banner">‼️ Compliance capture failed — '
            + doms
            + ". Re-run with <code>--refresh</code> "
            "(and <code>--browser</code> / a proxy).</div>"
        )

    # Coverage tab mirrors audit_<project>.md: summary → dupes → per-status tables → all spiders
    # → notes. One search box filters spiders across every table on the tab.
    cov_search = (
        '<div class="covsearch"><input class="cov-q" '
        'placeholder="filter spider across all coverage tables…" aria-label="filter spiders">'
        '<button class="cov-clear" type="button">clear</button></div>'
    )
    # actionable problems first, then the orthogonal duplicates, then the clean spiders, then the
    # collapsed full grid + definitions.
    problem_sections = "".join(
        _status_section(project, lbl, coverage_rows)
        for lbl, _ in LEGEND
        if lbl not in ("ok", "discarded")
    )
    clean_sections = "".join(
        _status_section(project, lbl, coverage_rows) for lbl in ("ok", "discarded")
    )
    cov_intro = (
        '<p class="tabintro">Each row is a website we scrape. This shows whether we got all '
        "its pages (<b>coverage</b>) and pulled the text out of them (<b>content%</b>), "
        'grouped by what needs fixing. <span class="axes">Two independent axes — '
        "<b>coverage</b> = did we get enough of the right pages · <b>content%</b> = did "
        "extraction work on what we got.</span> "
        "<b>The goal is to get every row into <i>ok</i></b> (or deliberately "
        "<i>discarded</i>) — each group header names the one action that moves it there. "
        "Rows that turn out to be fine are promoted by a human note in "
        "<code>audit_notes.json</code>; a sitemap that is the wrong yardstick is silenced "
        "in <code>audit_sitemap_skip.json</code> (both suggest-only for agents).</p>"
    )
    coverage_body = (
        (
            cov_intro
            + _health_strip(coverage_rows)
            + _status_summary(coverage_rows)
            + cov_search
            + problem_sections
            + _dupes_section(project, coverage_rows)
            + clean_sections
            + _all_spiders_table(project, coverage_rows)
            + _notes_definitions()
        )
        if coverage_rows
        else '<p class="empty">No spiders / no crawl output for this project.</p>'
    )
    selbar_pdf = (
        f'<div class="selbar" id="selbar-pdfs" data-project="{_esc(project)}" '
        'data-mode="pdf-json">'
        '<b><span class="n">0</span> hosts to include</b> → save as '
        "<code>data/&lt;project&gt;/_audit/pdf_hosts.json</code> "
        '<button class="copy" type="button">copy JSON</button>'
        '<button class="dl" type="button">download pdf_hosts.json</button>'
        '<button class="savepage" type="button">save page with choices</button>'
        '<code class="cmd json"></code></div>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(project)} — quality audit</title>
<style>{_CSS}</style></head>
<body>
<header>
 <h1>{_esc(project)} — quality audit</h1>
 <div class="meta">{n_spiders} spiders · {n_compl} compliance-checked · {n_pdf} with external PDFs
 · click a row to expand · click a header to sort · click a chip to filter · hover for detail.
 The markdown reports are the untouched ground truth; this is the interactive view.</div>
 <details class="howto">
  <summary>How to regenerate this dashboard</summary>
  <p class="fixhint">Run the audit for this project — it rebuilds the markdown reports, the CSVs,
  and this HTML dashboard. See <code>./scrapai audit --help</code> for the flags.</p>
  <pre><code>./scrapai audit --project {_esc(project)}</code></pre>
 </details>
</header>
<nav>
 <button class="active" onclick="tab('coverage',this)">Coverage</button>
 <button onclick="tab('compliance',this)">Compliance</button>
 <button onclick="tab('pdfs',this)">PDFs</button>
</nav>
<main>
 <section id="coverage" class="active">
  {warn}{coverage_body}
 </section>
 <section id="compliance">
  {failbanner}{_compliance_table(compliance_rows)}
 </section>
 <section id="pdfs">
  {_pdf_table(pdf_spiders, project)}{selbar_pdf}
 </section>
</main>
<script>{_JS}</script>
</body></html>
"""


def write_dashboard(project, audit_result, pdf_result):
    """Assemble the structured inputs (coverage rows + full compliance snapshots + PDF hosts),
    render, and write `_audit/dashboard_<project>.html`; return its path."""
    audit_result = audit_result or {}
    pdf_result = pdf_result or {}
    coverage_rows = audit_result.get("rows", []) or []
    config_warnings = audit_result.get("config_warnings", []) or []
    try:
        # reuse the audit's already-computed snapshot data when present (single pass);
        # compute here otherwise (e.g. --no-compliance runs, standalone calls)
        compliance_rows = build_compliance_rows(
            project, data=audit_result.get("_compliance_data")
        )
    except Exception as e:  # never let the dashboard break the audit
        print(f"      ⚠ dashboard: compliance detail unavailable ({e})", flush=True)
        compliance_rows = []
    pdf_spiders = pdf_result.get("spiders", []) or []

    out_dir = os.path.join(DATA_DIR, project, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    _ensure_pdf_exclude(project)  # give a new project the standard (inert) layout
    path = os.path.join(out_dir, f"dashboard_{project}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            render_dashboard(
                project, coverage_rows, compliance_rows, pdf_spiders, config_warnings
            )
        )
    return path
