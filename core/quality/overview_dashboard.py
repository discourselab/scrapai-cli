"""Content-profile dashboard — the interactive view of `overview.run()`'s structured data.

A sibling of the audit `dashboard` package, deliberately kept separate so the audit dashboard
is untouched. It reuses that package's `CSS` / `JS` (the generic `setupTable` sort·search·expand
engine) as the single source of styling, and renders ONE `.fx-table` of spider content profiles.
Every dynamic value is `html.escape`d. Self-contained: no server, no external asset.
"""

import os

from core.quality._env import DATA_DIR
from core.quality.dashboard.assets import CSS, JS
from core.quality.dashboard.widgets import esc as _esc
from core.quality.dashboard.widgets import flags_cell as _flags_cell
from core.quality.dashboard.widgets import meter


def _bars(year_hist):
    """A small inline bar chart over the per-year publication histogram."""
    if not year_hist:
        return '<span class="na">no dates</span>'
    mx = max(year_hist.values()) or 1
    cells = []
    for y, n in year_hist.items():
        h = max(3, round(28 * n / mx))
        cells.append(
            f'<span class="ybar" title="{_esc(str(y))}: {n}">'
            f'<span class="yfill" style="height:{h}px"></span>'
            f'<span class="ynum">{_esc(str(y))[2:]}</span></span>'
        )
    return '<span class="ybars">' + "".join(cells) + "</span>"


def _detail(r):
    out = []
    # sections
    secs = " · ".join(f"{_esc(s)} <b>{n}</b>" for s, n in r["sections"][:16])
    out.append(
        f'<div class="kv"><b>Sections ({r["n_sections"]}):</b> {secs or "—"}</div>'
    )
    if r["zero_yield_rules"]:
        out.append(
            '<div class="why"><b>⚠ allow-rules matching 0 scraped URLs:</b> '
            + " ".join(f"<code>{_esc(z)}</code>" for z in r["zero_yield_rules"])
            + "</div>"
        )
    if r.get("pdf_rows"):
        out.append(
            f'<div class="kv"><b>PDFs harvested:</b> {r["pdf_unique"]} unique '
            f'({r["pdf_ext"]} external-host) · {r["pdf_rows"]} link occurrences</div>'
        )
    # dates
    if r["date_min"]:
        out.append(
            f'<div class="kv"><b>Publication dates:</b> {_esc(r["date_min"])} → '
            f'{_esc(r["date_max"])} · {r["n_dated"]} dated · {r["null_date_pct"]}% null</div>'
        )
        out.append('<div class="kv">' + _bars(r["year_hist"]) + "</div>")
        if r["suspicious_dates"]:
            out.append(
                f'<div class="why">⚠ {r["suspicious_dates"]} out-of-range date(s) '
                "(&lt;1995 or future) — likely a wrong date selector.</div>"
            )
    else:
        out.append(
            f'<div class="kv"><b>Publication dates:</b> none parsed '
            f'({r["null_date_pct"]}% null)</div>'
        )
    # field coverage
    frag = "".join(
        f'<tr><td class="mono">{_esc(f["field"])}</td><td>{meter(f["pct"])}</td>'
        f'<td class="sub">{f["populated"]}/{r["rows"]}</td></tr>'
        for f in r["fields"]
    )
    if frag:
        out.append(
            '<div class="kv"><b>Field coverage</b> (share of items non-empty):'
            f'<table class="mini">{frag}</table></div>'
        )
    # content / degenerate / off-domain
    out.append(
        f'<div class="kv"><b>Content:</b> median {r["content_med"]} chars · '
        f'{r["thin"]} thin items ({r["thin_pct"]}%)</div>'
    )
    if r["degenerate"]:
        out.append(
            '<div class="why"><b>⚠ Constant fields</b> (same value every item): '
            + " ".join(
                f'<code>{_esc(d["field"])}</code>=“{_esc(d["value"])}”'
                for d in r["degenerate"]
            )
            + "</div>"
        )
    if r["offdomain"]:
        hosts = " · ".join(f"{_esc(h)} <b>{n}</b>" for h, n in r["offdomain_hosts"])
        out.append(
            f'<div class="why"><b>⚠ Off-domain URLs:</b> {r["offdomain"]} → {hosts}</div>'
        )
    # samples
    if r["samples"]:
        rows = "".join(
            f'<li>{_esc(s["title"] or "(no title)")} — '
            f'<a href="{_esc(s["url"], quote=True)}" target="_blank" rel="noopener">'
            f'{_esc(s["url"])}</a></li>'
            for s in r["samples"]
        )
        out.append(f'<div class="kv"><b>Samples:</b><ul class="samp">{rows}</ul></div>')
    if not r["config_found"]:
        out.append(
            '<div class="why">⚠ No final_spider.json found — profiled crawl output only.</div>'
        )
    return "".join(out)


def _table(rows):
    if not rows:
        return '<p class="empty">No spiders / no crawl output for this project.</p>'
    body = []
    for i, r in enumerate(sorted(rows, key=lambda x: str(x.get("spider", "")).lower())):
        rid = f"o{i}"
        spider = str(r.get("spider", ""))
        att = r.get("attention", 0)
        facet = "attention" if att else "clean"
        wf = f'{_esc(r["worst_field"])} ' if r["worst_field"] else ""
        date_cell = (
            f'{_esc(r["date_min"])}→{_esc(r["date_max"])}' if r["date_min"] else "—"
        )
        body.append(
            f'<tr class="fx-row" data-id="{rid}" data-name="{_esc(spider)}" '
            f'data-facet="{facet}" data-attention="{att}">'
            f'<td class="mono" data-key="{_esc(spider.lower())}">{_esc(spider)} '
            f'<span class="caret">▸</span></td>'
            f'<td class="r" data-key="{r["rows"]}">{r["rows"]}</td>'
            f'<td class="r" data-key="{r.get("pdf_unique", 0)}">'
            + (
                f'{r["pdf_unique"]} ({r["pdf_ext"]} ext)'
                if r.get("pdf_unique")
                else "—"
            )
            + "</td>"
            f'<td class="r" data-key="{r["n_sections"]}">{r["n_sections"]}</td>'
            f'<td data-key="{_esc(r["date_min"] or "")}">{date_cell}</td>'
            f'<td data-key="{r["null_date_pct"]}">{meter(r["null_date_pct"], invert=True)}</td>'
            f'<td data-key="{r["worst_field_pct"]}">{wf}{meter(r["worst_field_pct"])}</td>'
            f'<td data-key="{r["thin_pct"]}">{meter(r["thin_pct"], invert=True)}</td>'
            f'<td class="flags">{_flags_cell(r.get("flags", ""))}</td>'
            f"</tr>"
            f'<tr class="fx-detail" data-id="{rid}" hidden><td colspan="9">{_detail(r)}</td></tr>'
        )
    head = (
        "<tr>"
        '<th data-key="spider" data-type="str">spider</th>'
        '<th class="r" data-key="items" data-type="num" title="HTML article rows of crawl output">items</th>'
        '<th class="r" data-key="pdf" data-type="num" title="unique PDF documents harvested as URL-only rows; (N ext) '
        '= external hosts">pdf</th>'
        '<th class="r" data-key="sections" data-type="num" title="distinct first-path-segment sections">sections</th>'
        '<th data-key="dates" data-type="str" title="publication date range (min→max)">dates</th>'
        '<th data-key="null" data-type="num" title="share of items with no parseable published_date">null date</th>'
        '<th data-key="worst" data-type="num" title="the configured field with the lowest non-empty %">worst field</th>'
        '<th data-key="thin" data-type="num" title="share of items shorter than the thin threshold">thin</th>'
        '<th data-key="flags" data-type="str" title="attention tokens; a clean row is empty">flags</th>'
        "</tr>"
    )
    return (
        f'<table class="fx-table" data-tab="overview"><thead>{head}</thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def _facets(rows):
    n_att = sum(1 for r in rows if r.get("attention"))
    n_clean = len(rows) - n_att
    chips = (
        f'<button class="facet" type="button" data-facet="attention">needs attention <b>{n_att}</b></button>'
        f'<button class="facet" type="button" data-facet="clean">clean <b>{n_clean}</b></button>'
    )
    return (
        f'<div class="fx-facets" data-for="overview">{chips}'
        '<input class="fx-search" placeholder="filter spider…" aria-label="filter">'
        '<button class="clear" type="button">clear</button></div>'
    )


_EXTRA_CSS = """
.ybars{display:inline-flex;align-items:flex-end;gap:2px;height:34px}
.ybar{display:inline-flex;flex-direction:column;align-items:center;justify-content:flex-end;width:20px}
.yfill{width:12px;background:var(--acc);border-radius:2px 2px 0 0;display:block}
.ynum{font-size:9px;color:var(--mut);margin-top:2px}
table.mini{width:auto;margin:4px 0}
table.mini td{border:none;padding:1px 10px 1px 0}
ul.samp{margin:4px 0;padding-left:18px}ul.samp li{margin:2px 0}
"""


def render_overview(project, rows):
    """Pure render → self-contained HTML string for the content-profile dashboard."""
    rows = rows or []
    n_att = sum(1 for r in rows if r.get("attention"))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(project)} — content profile</title>
<style>{CSS}{_EXTRA_CSS}</style></head>
<body>
<header>
 <h1>{_esc(project)} — spider content profile</h1>
 <div class="meta">{len(rows)} spiders · {n_att} need attention · what each spider actually
 collected (sections · publication dates · field coverage · thin/constant/off-domain checks).
 Complementary to <code>./scrapai audit</code> (coverage vs sitemap + dupes). Click a row to
 expand · a header to sort · a chip to filter. Ground truth: <code>overview_{_esc(project)}.md</code>.</div>
</header>
<main>
 <section id="overview" class="active">
  {_facets(rows)}{_table(rows)}
 </section>
</main>
<script>{JS}</script>
</body></html>
"""


def write_overview_dashboard(project, overview_result):
    """Render and write `_audit/overview_<project>.html`; return its path."""
    rows = (overview_result or {}).get("spiders", []) or []
    out_dir = os.path.join(DATA_DIR, project, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"overview_{project}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_overview(project, rows))
    return path
