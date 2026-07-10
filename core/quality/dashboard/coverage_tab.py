"""The Coverage tab — mirrors `audit_<project>.md` section-for-section (crawl_audit's
write_outputs): health strip · status summary · per-status tables · duplicate rows · the
all-spiders grid · notes & definitions — plus the copy-paste dedupe command builders."""

import re

from core.quality.crawl_audit import LEGEND, STATUS_LEADS, fix_hints

from .widgets import (
    COLUMN_DEFS,
    GLOSSARY,
    _STATUS_CLASS,
    _chip,
    _copy_btn,
    _esc,
    _flag_title,
    _flags_cell,
    _md_strip,
    _meter,
    _tip,
)

_STATUS_ORDER = {label: i for i, (label, _) in enumerate(LEGEND)}


# NOTE: the dashboard's select bars rebuild these SAME commands client-side — see the
# `dedupe` / `crawl` / `/spider-review` / `/spider-review` template lines inside assets.py's
# JS string (search for "scrapai dedupe --project"). Keep the two in sync.
def dupe_command(project, spider):
    """The copy-paste command that dedupes ONE spider (surfaced, never executed)."""
    return f"./scrapai dedupe --project {project} --only {spider}"


def bulk_dedupe_command(project, spiders):
    """The combined command for a SELECTION of spiders — built live from the row checkboxes."""
    return f"./scrapai dedupe --project {project} --only {' '.join(spiders)}"


# --------------------------------------------------------------------------- Coverage tab
#   Rendered to mirror `audit_<project>.md` section-for-section (crawl_audit.write_outputs):
#   status-labels summary · Duplicate rows · one table per problem status · all spiders ·
#   Notes & definitions. Same columns and prose as the markdown, made interactive.
def _slug(label):
    return "cov-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _status_lead(label):
    """The concise action a status opens with (`Fix: selectors.`) — looked up from
    crawl_audit's STATUS_LEADS, which is built from the SAME triples as LEGEND (no
    re-authoring), so the detail stays in sync with the markdown."""
    return STATUS_LEADS.get(label, "")


def _flag_guidance(flags):
    """One line per flag ACTUALLY on this row (token + its glossary meaning) — not the whole
    status's prose. A clean row yields nothing."""
    out = []
    for tok in (flags or "").split(" · "):
        t = tok.strip()
        if not t:
            continue
        meaning = _flag_title(t)
        out.append(
            f'<div class="flagline"><b>{_esc(t)}</b>'
            + (f" — {_esc(meaning)}" if meaning else "")
            + "</div>"
        )
    return "".join(out)


def _coverage_detail(project, r):
    td = r.get("true_dupes", 0) or 0
    bits = [
        f"scraped <b>{r.get('scraped', 0)}</b>",
        f"rows <b>{r.get('rows', 0)}</b>",
        (
            f"pdf <b>{r.get('pdf', 0)}</b> (own {r.get('pdf_own', 0)} · "
            f"external {r.get('pdf_ext', 0)})"
            if r.get("pdf")
            else ""
        ),
        f"versions <b>{r.get('versions', 0)}</b>",
        f"files <b>{r.get('files', 0)}</b>",
        f"median <b>{_esc(str(r.get('content_med', 0)))}</b> chars",
        f"eligible <b>{_esc(str(r.get('eligible', '-')))}</b>",
        f"sitemap total <b>{_esc(str(r.get('sitemap_total', '-')))}</b>",
    ]
    out = [f'<div class="kv">{" · ".join(b for b in bits if b)}</div>']
    # the ONE-line action for this status (the bold lead of its LEGEND meaning)
    meaning = next((d for (l, d) in LEGEND if l == r.get("status")), "")
    lead = _status_lead(r.get("status"))
    if lead:
        out.append(
            f'<div class="why"><b>{_esc(r.get("status", ""))}:</b> {_esc(lead)}</div>'
        )
    # guidance for ONLY the flags present on this row (not every flag for the status)
    out.append(_flag_guidance(r.get("flags", "")))
    if td:
        out.append(
            f'<div class="dupe">{td} duplicate rows ({r.get("dup_pct", 0)}%) · '
            f'{_copy_btn(dupe_command(project, r.get("spider", "")))}</div>'
        )
    # the exhaustive status meaning + fix-hint, tucked away so nothing is lost
    hint = fix_hints(project).get(r.get("status"))
    full = _md_strip(meaning) + (("  " + _md_strip(hint)) if hint else "")
    if full.strip():
        out.append(
            '<details class="fullguide"><summary>full guidance</summary>'
            f'<div class="fix">{_esc(full)}</div></details>'
        )
    return "".join(out)


def _num_cell(v):
    """A raw right-aligned number cell (the MD columns the user built). '-'/'' pass through;
    non-numeric sorts to the bottom."""
    s = "" if v is None else str(v)
    try:
        k = float(s)
    except (TypeError, ValueError):
        k = -1
    return f'<td class="r" data-key="{k}">{_esc(s if s != "" else "-")}</td>'


# per-status action: tick spiders → a ready-to-run command for that problem group
_SELECT_MODE = {
    "extraction broken": "repair",
    "incomplete": "repair",
    "too few pages": "crawl",
    "manual review": "review",
}
_SELECT_NOUN = {
    "repair": ("spiders to repair", "paste into the agent"),
    "review": ("spiders to review", "paste into the agent"),
    "crawl": ("spiders to crawl", "run in your terminal"),
}


def _cov_table(
    project, rows, tab_id, with_status=False, with_dupes=False, select_mode=None
):
    """One coverage table with the audit-MD columns (raw numbers; a slim inline meter behind the
    %s). Sortable; each row expands to `_coverage_detail`. Caller pre-sorts `rows`. When
    `select_mode` is set, rows get a checkbox and a select-bar builds the group's command.
    """
    if not rows:
        return '<p class="empty">— none —</p>'
    ncols = (
        10
        + (2 if with_dupes else 0)
        + (1 if with_status else 0)
        + (1 if select_mode else 0)
    )
    body = []
    for i, r in enumerate(rows):
        rid = f"{tab_id}{i}"
        spider = str(r.get("spider", ""))
        cov = r.get("coverage_pct", "")
        cells = []
        if select_mode:
            cells.append(
                f'<td class="sel"><input type="checkbox" class="fx-check" aria-label="select {_esc(spider)}"></td>'
            )
        cells += [
            f'<td class="mono" data-key="{_esc(spider.lower())}">{_esc(spider)} <span class="caret">▸</span></td>',
            f'<td data-key="{_esc(str(r.get("sitemap", "")))}">{_esc(str(r.get("sitemap", "")))}</td>',
            _num_cell(r.get("sitemap_total", "-")),
            _num_cell(r.get("eligible", "-")),
            _num_cell(r.get("scraped", 0)),
        ]
        pdf = r.get("pdf", 0) or 0
        pdf_disp = f'{pdf} ({r.get("pdf_ext", 0)} ext)' if pdf else "—"
        cells.append(f'<td class="r" data-key="{pdf}">{pdf_disp}</td>')
        if with_dupes:
            td = r.get("true_dupes", 0) or 0
            ver = r.get("versions", 0) or 0
            dup_disp = f"{td} ({r.get('dup_pct', 0)}%)" if td else "0"
            cells.append(f'<td class="r" data-key="{td}">{dup_disp}</td>')
            cells.append(f'<td class="r" data-key="{ver}">{ver}</td>')
        scr, elig = r.get("scraped", 0), r.get("eligible", "-")
        cont = r.get("content", scr)
        content_tip = f"{cont} of {scr} saved HTML pages have extracted text"
        cov_tip = (
            f"{scr} of {elig} expected pages saved"
            if str(elig) not in ("-", "", "None")
            else None
        )
        # a pdf-only spider has no HTML to judge — n/a, not a red 0%
        cells.append(
            f'<td data-key="{r.get("content_pct", 0) if scr else -1}">'
            f'{_meter(r.get("content_pct", 0) if scr else None, content_tip)}</td>'
        )
        cells.append(
            f'<td data-key="{cov if cov != "" else -1}">{_meter(cov, cov_tip)}</td>'
        )
        cells.append(
            f'<td data-key="{_esc(str(r.get("stale", "")))}">{_esc(str(r.get("stale", "")) or "—")}</td>'
        )
        cells.append(f'<td class="flags">{_flags_cell(r.get("flags", ""))}</td>')
        if with_status:
            st = r.get("status", "")
            cells.append(f'<td data-key="{_STATUS_ORDER.get(st, 99)}">{_chip(st)}</td>')
        body.append(
            f'<tr class="fx-row" data-id="{rid}" data-name="{_esc(spider)}">'
            + "".join(cells)
            + "</tr>"
            f'<tr class="fx-detail" data-id="{rid}" hidden><td colspan="{ncols}">'
            f"{_coverage_detail(project, r)}</td></tr>"
        )
    h = []
    if select_mode:
        h.append(
            '<th class="sel"><input type="checkbox" class="fx-all" aria-label="select all"></th>'
        )
    tip_total = _tip(
        "How many page URLs the site lists in its sitemap (its own map of all pages)."
    )
    tip_eligible = _tip(
        "How many pages this spider SHOULD have got — the sitemap URLs matching its "
        "rules, minus dead ones. This is the denominator for coverage."
    )
    tip_scraped = _tip(
        "How many unique HTML pages we actually saved "
        "(PDF harvest rows have their own column)."
    )
    tip_versions = _tip(
        "The same URL saved again with CHANGED content — real history from "
        "re-fetching updated pages; dedupe keeps these."
    )
    tip_stale = _tip(
        "Flagged (⚠ Nd) when the newest saved crawl is more than 30 days old — "
        "the data may be out of date."
    )
    h += [
        '<th data-key="spider" data-type="str">spider</th>',
        f'<th data-key="sitemap" data-type="str" {_tip(COLUMN_DEFS["sitemap"])}>sitemap</th>',
        f'<th class="r" data-key="total" data-type="num" {tip_total}>total</th>',
        f'<th class="r" data-key="eligible" data-type="num" {tip_eligible}>eligible</th>',
        f'<th class="r" data-key="scraped" data-type="num" {tip_scraped}>scraped</th>',
        f'<th class="r" data-key="pdf" data-type="num" {_tip(COLUMN_DEFS["pdf"])}>pdf</th>',
    ]
    if with_dupes:
        h.append(
            f'<th class="r" data-key="tdupes" data-type="num" {_tip(COLUMN_DEFS["dupes"])}>true dupes</th>'
        )
        h.append(
            f'<th class="r" data-key="versions" data-type="num" {tip_versions}>versions</th>'
        )
    h.append(
        f'<th data-key="content" data-type="num" {_tip(COLUMN_DEFS["content"])}>content%</th>'
    )
    h.append(
        f'<th data-key="coverage" data-type="num" {_tip(COLUMN_DEFS["coverage"])}>coverage</th>'
    )
    h.append(f'<th data-key="stale" data-type="str" {tip_stale}>stale</th>')
    h.append(
        f'<th data-key="flags" data-type="str" {_tip(COLUMN_DEFS["flags"])}>flags</th>'
    )
    if with_status:
        h.append(
            f'<th data-key="status" data-type="num" {_tip(COLUMN_DEFS["status"])}>status</th>'
        )
    head = "<tr>" + "".join(h) + "</tr>"
    selbar = ""
    if select_mode:
        noun, where = _SELECT_NOUN.get(select_mode, ("selected", ""))
        selbar = (
            f'<div class="selbar" id="selbar-{tab_id}" data-project="{_esc(project)}" '
            f'data-mode="{select_mode}"><b><span class="n">0</span> {noun}</b> → '
            f'<code class="cmd"></code> <button class="copy" type="button">copy</button>'
            f'<span class="sub">&nbsp; {where}</span></div>'
        )
    return (
        f'<table class="fx-table" data-tab="{tab_id}"><thead>{head}</thead>'
        f'<tbody>{"".join(body)}</tbody></table>' + selbar
    )


def _health_strip(rows):
    """An at-a-glance stacked bar of the status counts (segments coloured + proportional, each a
    link to its section) — the health read before the detailed summary/tables."""
    counts = {}
    for r in rows:
        counts[r.get("status", "")] = counts.get(r.get("status", ""), 0) + 1
    total = len(rows) or 1
    segs = []
    for label, meaning in LEGEND:
        n = counts.get(label, 0)
        if not n:
            continue
        cls = _STATUS_CLASS.get(label, "s-other")
        lead = _status_lead(label)
        segs.append(
            f'<a class="seg {cls}" href="#{_slug(label)}" '
            f'style="width:{round(100 * n / total, 2)}%" '
            f'{_tip(f"{label}: {n} — {lead}")}>{n}</a>'
        )
    return (
        f'<div class="healthstrip"><div class="hsbar">{"".join(segs)}</div>'
        f'<span class="hslabel">{len(rows)} spiders</span></div>'
    )


def _status_summary(rows):
    """The MD's 'Status labels' table: label · count · meaning. Counts link to their section."""
    counts = {}
    for r in rows:
        counts[r.get("status", "")] = counts.get(r.get("status", ""), 0) + 1
    body = []
    for label, meaning in LEGEND:
        n = counts.get(label, 0)
        cnt = f'<a href="#{_slug(label)}">{n}</a>' if n else "0"
        # chip carries the FULL meaning on hover; the cell shows only the short action lead
        body.append(
            f"<tr><td>{_chip(label)}</td>"
            f'<td class="r">{cnt}</td><td class="def">{_esc(_status_lead(label))}</td></tr>'
        )
    return (
        '<h3>Status labels <span class="sub">— hover a label for the full meaning</span></h3>'
        '<table class="summary"><thead><tr><th>label</th>'
        '<th class="r">count</th><th>in short</th></tr></thead><tbody>'
        + "".join(body)
        + "</tbody></table>"
    )


def _dupes_section(project, rows):
    """The MD's Duplicate-rows section: the table + the dedupe copy-commands (per spider and a
    select→combined bar). Kept separate from status (duplication is an orthogonal axis).
    """
    dups = sorted(
        (r for r in rows if (r.get("true_dupes", 0) or 0) > 0),
        key=lambda r: r.get("true_dupes", 0),
        reverse=True,
    )
    out = [
        f'<div class="covsec"><h3 id="cov-duplicate-rows">Duplicate rows ({len(dups)})</h3>'
    ]
    if not dups:
        out.append(
            '<p class="hint">None — no spider has identical rows repeated '
            "(same URL <b>and</b> content).</p></div>"
        )
        return "".join(out)
    out.append(
        '<p class="hint"><b>true dupes</b> = same URL <b>and</b> identical content (re-run '
        "artifacts the default dedupe removes). <b>versions</b> = same URL, changed content "
        "(genuine history; dedupe keeps these). Neither affects scraped/coverage.</p>"
    )
    tb = []
    for r in dups:
        sp = str(r.get("spider", ""))
        tb.append(
            f'<tr class="fx-row" data-name="{_esc(sp)}">'
            f'<td class="sel"><input type="checkbox" class="fx-check" aria-label="select {_esc(sp)}"></td>'
            f'<td class="mono" data-key="{_esc(sp.lower())}">{_esc(sp)}</td>'
            f'<td class="r" data-key="{r.get("files", 0)}">{r.get("files", 0)}</td>'
            f'<td class="r" data-key="{r.get("rows", 0)}">{r.get("rows", 0)}</td>'
            f'<td class="r" data-key="{r.get("scraped", 0)}">{r.get("scraped", 0)}</td>'
            f'<td class="r" data-key="{r.get("true_dupes", 0)}">{r.get("true_dupes", 0)}</td>'
            f'<td class="r" data-key="{r.get("dup_pct", 0)}">{r.get("dup_pct", 0)}%</td>'
            f'<td class="r" data-key="{r.get("versions", 0)}">{r.get("versions", 0)}</td></tr>'
        )
    head = (
        '<tr><th class="sel"><input type="checkbox" class="fx-all" aria-label="select all"></th>'
        '<th data-key="spider" data-type="str">spider</th>'
        '<th class="r" data-key="files" data-type="num">files</th>'
        '<th class="r" data-key="rows" data-type="num">rows</th>'
        '<th class="r" data-key="unique" data-type="num">unique</th>'
        '<th class="r" data-key="tdupes" data-type="num">true dupes</th>'
        '<th class="r" data-key="dpct" data-type="num">dup%</th>'
        '<th class="r" data-key="versions" data-type="num">versions</th></tr>'
    )
    out.append(
        f'<table class="fx-table" data-tab="cov-dupes"><thead>{head}</thead>'
        f'<tbody>{"".join(tb)}</tbody></table>'
    )
    out.append(
        '<p class="hint"><b>Fix</b> — <code>./scrapai dedupe</code> consolidates each '
        "spider's <code>crawls/*.jsonl</code> (originals kept as <code>*.superseded</code>, "
        "reversible). Tick the spiders to dedupe and copy the combined command.</p>"
    )
    out.append(
        f'<div class="selbar" id="selbar-cov-dupes" data-project="{_esc(project)}">'
        '<b><span class="n">0</span> selected</b> → <code class="cmd"></code> '
        '<button class="copy" type="button">copy</button></div>'
    )
    out.append("</div>")
    return "".join(out)


def _render_hint(hint):
    """Render a fix-hint (a lead line, then `- ` bullets) as STRUCTURED html — a lead paragraph
    plus a bullet list — instead of one overwhelming blob."""
    out, bullets = [], []

    def flush():
        if bullets:
            out.append(
                "<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in bullets) + "</ul>"
            )
            bullets.clear()

    for raw in _md_strip(hint).split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        else:
            flush()
            out.append(f'<p class="fixhint">{_esc(line)}</p>')
    flush()
    return "".join(out)


def _status_section(project, label, rows):
    """One '## <status> (N)' section: heading + the `fix_hints` intro + the per-status table."""
    cat = sorted(
        [r for r in rows if r.get("status") == label],
        key=lambda r: str(r.get("spider", "")).lower(),
    )
    if not cat:
        return ""
    lead = _status_lead(label)
    out = [
        f'<div class="covsec"><h3 id="{_slug(label)}">{_esc(label)} ({len(cat)})'
        + (f' <span class="lead">— {_esc(lead)}</span>' if lead else "")
        + "</h3>"
    ]
    hint = fix_hints(project).get(label)
    if hint:
        out.append(
            '<details class="howto"><summary>how to fix</summary>'
            + _render_hint(hint)
            + "</details>"
        )
    out.append(
        _cov_table(project, cat, _slug(label), select_mode=_SELECT_MODE.get(label))
    )
    out.append("</div>")
    return "".join(out)


def _all_spiders_table(project, rows):
    """The full sortable grid over EVERY spider (all columns incl. true dupes / versions / status)
    — COLLAPSED by default. The per-status tables above are the primary, grouped view; this is the
    occasional 'sort / scan everything in one place' reference, one click away."""
    srt = sorted(rows, key=lambda r: str(r.get("spider", "")).lower())
    return (
        '<details class="drawer allgrid"><summary>All spiders — full sortable grid '
        f"({len(srt)})</summary>"
        + _cov_table(project, srt, "cov-all", with_status=True, with_dupes=True)
        + "</details>"
    )


def _notes_definitions():
    """The MD's Notes & definitions, generated from the SAME COLUMN_DEFS / GLOSSARY used for the
    header + flag tooltips (no re-authoring), in a collapsible drawer."""
    cols = "".join(
        f"<li><b>{_esc(k)}</b> — {_esc(v)}</li>"
        for k, v in COLUMN_DEFS.items()
        if k in ("sitemap", "coverage", "content", "dupes", "flags")
    )
    flags = "".join(f"<li><b>{_esc(k)}</b> — {_esc(v)}</li>" for k, v in GLOSSARY)
    return (
        '<details class="drawer"><summary>Notes &amp; definitions</summary>'
        "<p><b>Method.</b> <i>scraped</i> = unique URLs across <code>crawls/*.jsonl</code>. "
        "<i>content%</i> = share with non-empty content. <i>eligible</i> = sitemap URLs matching "
        "the allow-rules, reduced to the live fraction when crawl-stats exist. <i>coverage</i> = "
        "scraped ÷ eligible. <i>total</i>/<i>eligible</i> come from the crawl when it recorded "
        "them, else a fetched sitemap (nested indexes capped). <code>-</code> = no sitemap.</p>"
        "<p><b>Two independent axes:</b> <i>coverage</i> (did we get enough of the right pages?) "
        "and <i>content%</i> (did extraction work on what we got?).</p>"
        f'<p><b>Columns</b></p><ul class="defs">{cols}</ul>'
        f'<p><b>Flag tokens</b></p><ul class="defs">{flags}</ul></details>'
    )
