# Quality Dashboards — Context & Improvement Reference

> **Historical plan — the tool is built and shipped.** Current docs: [docs/quality.md](../quality.md); handover checklist: [docs/requests/quality-tool.md](../requests/quality-tool.md).

> Handoff doc for continuing work on the **HTML dashboards**. Everything you need to pick up
> cold and improve them. The three markdown reports are the untouched **ground truth**; the
> HTML is a *projection* of the same structured data and must never change the MD/CSV.

## What exists now (two dashboards, one shared engine)

| Command | Output file | Renderer | Tabs / shape |
|---|---|---|---|
| `./scrapai audit --project <p>` | `data/<p>/_audit/dashboard_<p>.html` | `core/quality/dashboard.py` | 3 tabs: **Coverage · Compliance · PDFs** |
| `./scrapai overview --project <p>` | `data/<p>/_audit/overview_<p>.html` | `core/quality/overview_dashboard.py` | 1 table: per-spider **content profile** |

Both are **self-contained single HTML files** (inline CSS/JS, no server, no dependency).
`overview_dashboard.py` **imports `_CSS`, `_JS`, `_meter` from `dashboard.py`** — so the generic
interactive-table engine (`setupTable`: sort · facet · search · select · expand) is the single
source of styling/behaviour for both. **Improve the interaction model in one place: `dashboard.py`'s
`_JS`/`_CSS`.**

## The design idea (keep it)
A quality report is a **faceted view over one corpus of sources, each carrying lenses of signals.**
So the UI is *one generic interactive table*, instantiated per lens (`<table class="fx-table"
data-tab="…">`). The markdown's repetition (six per-status tables, legend, per-group fix-hints,
definitions wall) is re-expressed as **facets + progressive disclosure** (counts → facet chips →
row → expand → drawer). Nothing is lost; it's just interactive instead of repeated.

**Visual grammar (5 primitives, reused everywhere):** `chip` (colour+glyph+label, never colour
alone) · `meter` (a ratio as a bar) · `token` (muted flag/note, hover = meaning) · `mono id`
(spider/host/domain) · `expand caret`.

**Single source of truth per fact:** status meanings from `crawl_audit.LEGEND`, fix guidance from
`crawl_audit.fix_hints()`, compliance verdicts from `compliance_capture.assess_crawl` /
`assess_reuse`. The dashboard never re-authors these → it can't drift from the MD.

## File map
- `core/quality/dashboard.py` — **audit dashboard + the shared `_CSS`/`_JS` engine.** Key fns:
  - `render_dashboard(project, coverage_rows, compliance_rows, pdf_spiders, config_warnings=())`
    — **pure** (no fs/net), returns the full HTML string. Unit-tested.
  - `write_dashboard(project, audit_result, pdf_result)` — orchestrates + writes the file.
  - `build_compliance_rows(project)` — impure; flattens `cc.build_report_data()` via the
    `assess_*` / cell helpers into plain escapable dicts.
  - tab renderers `_coverage_table` / `_compliance_table` / `_pdf_table`, detail renderers
    `_coverage_detail` / `_compliance_detail`, cell helpers `_chip` `_meter` `_flags_cell`
    `_copy_btn` `_link`, and constants `GLOSSARY` (flag→meaning), `COLUMN_DEFS`, `_STATUS_CLASS`.
  - `dupe_command` / `bulk_dedupe_command` — command builders (pure, tested).
  - `_CSS` (styles), `_JS` (`setupTable` generic engine + tab switch + copy).
- `core/quality/overview_dashboard.py` — imports `_CSS/_JS/_meter`; `render_overview`,
  `write_overview_dashboard`, `_table`, `_detail`, `_bars` (year histogram), `_facets`, `_EXTRA_CSS`.
- `cli/audit.py`, `cli/dedupe.py`, `cli/overview.py` — thin Click wrappers (all registered in
  `cli/__init__.py`). `tests/unit/test_audit.py` — pure-render + command-builder tests.
- Design plan: `docs/plans/quality-dashboard.md`. Upstream handover: `docs/requests/quality-tool.md`.

## Data contracts (what each row dict carries)
- **coverage_rows** = `crawl_audit.run()["rows"]`: `spider, status, sitemap, sitemap_total,
  eligible, scraped, rows, true_dupes, versions, dup_pct, files, content, content_pct,
  content_med, coverage_pct, stale, flags`.
- **compliance_rows** = `build_compliance_rows(project)` (one dict/domain): `domain, checked,
  failed, source, archived_ts, crawl_emoji/crawl_sev/crawl_reasons, reuse_emoji/reuse_sev/
  reuse_reasons, facet, robots_cell, pdf_cell, blocked_paths, pdf_evidence, comments, notes,
  llms{present,verdict}, license, license_scope, license_url, license_quote, license_low,
  license_review, all_rights_reserved, bespoke, copyright, copyright_holder, copyright_year,
  copyright_discrepancy, ai_bits[], clauses[(kind,url,snippet)], cross_check`.
- **pdf_spiders** = `external_pdf.run()["spiders"]`: `[{spider,total,unique,hosts:[{host,count,sample}]}]`.
- **overview rows** = `overview.run()` output (see `core/quality/overview.py`) — sections, date
  span + null %, per-field coverage, thin/constant/off-domain checks.

## The interaction engine (`_JS` → `setupTable`)
Runs on every `.fx-table`. Row pairs: `<tr class="fx-row" data-id data-name data-facet
data-attention>` + a hidden `<tr class="fx-detail" data-id>`. Provides: **sort** (click `th[data-key]`,
numeric via `data-type="num"`), **facet** (chips in `.fx-facets[data-for=<tab>]`, multi-select),
**search** (`.fx-search`, matches `data-name`), **needs-attention** toggle (`.fx-att`), **expand**
(click row → toggles its detail), **select** (coverage only: `.fx-check` → sticky `#selbar-<tab>`
builds a combined `./scrapai dedupe … --only …` copy command), **copy** buttons.

## Hard constraints (do not break)
1. **No MD/CSV drift.** Byte-identical to the untouched root scripts is the acceptance test:
   `./scrapai audit --project gscc --no-fetch --no-compliance`, then diff `crawl_audit.csv`,
   `audit_gscc.md`, `compliance_gscc.md`, `external_pdf_report.md`. (Verified passing.)
2. **No new dependency** — vanilla JS/CSS, one self-contained file.
3. **XSS-safe** — every dynamic value `html.escape`d (site-derived clause/URL/licence text is
   untrusted). Data is embedded as escaped DOM text, never injected into JS strings.
4. Accessible — semantic tables, `aria-expanded`, keyboard-focusable, glyph **+** text, `title=` tips.

## Gotchas
- **Python 3.12 f-string tokenizer quirk:** a nested-quote f-string inside a genexp spread across
  continuation lines (`(… + ", ".join(f"…{x['k']}…" for x in xs) + …)`) raises a bogus
  "unterminated string literal". Fix: precompute the join with plain `+` concatenation. (Bit us in
  the fail-banner; watch for it when adding rendered sections.)
- Large PDF/coverage tables → big files (`dashboard_kb_policy_CARDS.html` ≈ 2.6 MB). Fine to open,
  but a candidate for virtualization if it grows.
- `_CSS` has two `.meter` blocks that merge — works, but tidy if you touch meters.
- Stale artifacts to ignore/delete: old unprefixed `data/*/_audit/dashboard.html` (pre-rename).

## Verify after any change
`.venv/bin/pytest tests/unit/` (currently green); rebuild `dashboard_gscc.html`; re-run the
no-drift diff above; spot-check an injected `<script>` value renders escaped.

## Improvement backlog (ideas, not committed)
- **Unify the two dashboards** — cross-link audit ↔ overview, or fold `overview` in as a 4th tab
  so a project has ONE `<p>.html` console. The shared `_CSS/_JS` already makes this cheap.
- Persist filter/sort state in the URL hash (shareable views; survives reload).
- Column show/hide picker; sticky first column on wide tables; multi-key sort.
- Export the current (filtered/selected) view to CSV client-side.
- Virtualize very large tables (PDFs) so multi-MB projects stay snappy.
- Keyboard navigation (j/k rows, / to search, enter to expand) + a full a11y pass.
- Light/dark toggle (currently dark only).
- A small top-of-page "health strip" (counts per status as a stacked bar) as an at-a-glance summary.
