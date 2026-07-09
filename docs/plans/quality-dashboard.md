# Quality Dashboard — Plan

> **Historical plan — the tool is built and shipped.** Current docs: [docs/quality.md](../quality.md); handover checklist: [docs/requests/quality-tool.md](../requests/quality-tool.md).

> Make `./scrapai audit`'s HTML the **primary, detailed, elegant** view of a project's crawl
> quality — clickable, filterable, sortable, selectable, with detail on hover/expand — while
> the three markdown reports stay **byte-for-byte untouched** as the ground truth.

## Context
`./scrapai audit` writes three ground-truth reports (`audit_<p>.md`, `compliance_<p>.md`,
`external_pdf_report.md` + `crawl_audit.csv`) and, today, a thin HTML summary that shows far
less than the MD. The MD is exhaustive but repeats itself — six per-status tables, a legend,
a fix-hint per group, a definitions wall, a separate duplicates section — because paper can't
filter. We want the opposite medium to play to its strengths: **one live view where filtering,
sorting and disclosure do what repetition does on paper.** Same information, a fraction of the
scrolling. The engines and their MD/CSV output do not change by a byte (the MD is the backup;
the HTML is a *projection* of the same data).

## The one idea that keeps it elegant
A quality report is a **faceted view over one corpus of sources, each carrying three lenses of
signals** (coverage/extraction · compliance · external PDFs). So the whole UI is *one generic
interactive table, instantiated three times* — not three bespoke renderers.

- **One component, three specs.** A single declarative table (sort · facet · search · select ·
  expand · tooltip) is written **once** in ~40 lines of vanilla JS that operate on `data-*`
  attributes. Each tab is just *data + a column spec + a detail renderer*. Add a lens later =
  add a spec, not more JS.
- **One visual grammar, learned once.** Five primitives reused on every tab: a **chip**
  (colour + glyph + label — never colour alone), a **meter** (a ratio as a bar), a muted
  **token** (flags/notes), a **mono id** (spider/host/domain), and an **expand caret**.
- **One progressive-disclosure ladder.** `counts → facet chips → row → expand → drawer`. Each
  rung reveals more; nothing is a wall of text. The MD's six status tables become six *facet
  states* of one table; the per-group fix-hint becomes a contextual banner shown only when
  that facet is active.
- **One source of truth per fact.** Status meanings come from `LEGEND`, fix guidance from
  `fix_hints()`, compliance verdicts from `assess_crawl`/`assess_reuse` — all **reused**, never
  re-authored, so the HTML can never drift from the MD.
- **A pure projection.** Engines return structured data → `render_dashboard(data) → HTML` is a
  pure function (unit-testable); the only impure step (reading compliance snapshots) is one
  isolated call. The MD is never re-parsed.

```
┌ gscc — quality audit ································ 15 sources ┐
│  ● broken 1   ◐ incomplete 2   ◔ review 3   ● ok 9     🔍 ____ │
│  [ Coverage ] Compliance   PDFs        ☐ needs-attention only  │
├───────────────────────────────────────────────────────────────┤
│ ☐  spider ▲    status   coverage        content        flags   │
│ ▸ ☐ rmi_org    ● ok     ▐████████▌100%  ▐███████▍99%   —       │
│ ▾ ☑ epa_gov    ● broken ▐█▏      12%    ▐█▏     12%    thin?ⓘ  │
│      240 scraped · 1998 rows · 3 files · median 0.4k · Fix:… │
│ ▸ ☐ iea_org    ◔ review ▐███████▏88%    ▐███████▉99%   found→ⓘ│
├───────────────────────────────────────────────────────────────┤
│ 2 selected → ./scrapai dedupe --project gscc --only … [copy]  │
└───────────────────────────────────────────────────────────────┘
 click header = sort · click chip = facet · click row = expand · hover ⓘ = why
```

## Information architecture (three specs, one grammar)
- **Coverage** (row = spider). Cells: select · status chip (hover = `LEGEND` meaning) ·
  sitemap · **coverage% meter** · **content% meter** · flag tokens (hover = glossary) · dupes
  badge. Facet chips = the statuses (live counts) + a *needs-attention* toggle + text search.
  Selecting a status shows its `fix_hints()` text as a slim contextual banner. Expand = every
  raw number (total, eligible, scraped, rows, versions, files, median chars) + flags in words
  + a dedupe copy-command if dupey. Row checkboxes → a sticky bar with a **combined**
  `./scrapai dedupe … --only a b c` copy button. Config-warnings banner; a *How this is
  calculated* drawer; column definitions on header-hover.
- **Compliance** (row = domain). Cells: worst-of verdict lead · domain (→ live robots.txt) ·
  checked · access · reuse · licence (→ the page it was read from) · AI · notes. Facet by
  crawl/reuse verdict. Expand = the evidence: assess reasons, which of *our* paths robots
  blocks (sample), AI signals, the **quoted** anti-scraping / no-AI-training / bespoke-grant
  clauses (blockquotes), licence wording, copyright, cross-check. Capture-failure banner.
- **PDFs** (row = spider×host, flat). Cells: spider · host · links · sample. Sort by links to
  float an org's own repository above one-off citations.

## Implementation (small, and it leaves the MD alone)
**`core/quality/crawl_audit.py`** — hoist `legend`→`LEGEND` (const) and `fix_hint`→
`fix_hints(project)` (fn) out of `write_outputs()`; it references them so the MD stays
identical and the dashboard shares the exact text. `run()` also returns `config_warnings`.

**`core/quality/compliance_capture.py`** — extract `build_report_data(project)` from
`write_report()` (returns `(captured, unchecked, failures)` — the fully-refined snapshots);
`write_report()` calls it, then formats the identical MD.

**`core/quality/dashboard.py`** — rewrite around the abstraction:
- Grammar + copy: `GLOSSARY` (flag → meaning), `COLUMN_DEFS`, `_chip`, `_meter`, `_token`.
- `_table(spec, rows)` — the one generic renderer emitting `data-sort`/`data-facet`/detail
  markup; a matching generic `<script>` handles sort/facet/search/select/expand/tooltip.
- Three column/detail **specs** (coverage, compliance, pdf) fed to `_table`.
- `dupe_command` / `bulk_dedupe_command` — command builders (pure, tested).
- `build_compliance_rows(project)` — flattens `cc.build_report_data()` via the existing
  `assess_*` / `crawl_robots_cell` / `crawl_pdf_cell` / `crawl_notes` / `license_*` helpers
  into plain escapable dicts (impure: reads snapshots).
- `render_dashboard(project, coverage_rows, compliance_rows, pdf_spiders, config_warnings=())`
  — **pure**, returns the whole self-contained HTML.
- `write_dashboard(project, audit_result, pdf_result)` — orchestrates + writes
  `dashboard_<project>.html`. (`cli/audit.py` unchanged — signature stays.)

Constraints: vanilla JS/CSS, one self-contained file, **no new dependency**; every dynamic
value `html.escape`d (site-derived clause/URL text is untrusted); accessible (semantic tables,
`aria-expanded`, keyboard-focusable, glyph **+** text, `title=` tooltips).

## Reused (no reinvention)
`assess_crawl` · `assess_reuse` · `crawl_robots_cell` · `crawl_pdf_cell` · `crawl_notes` ·
`license_class` · `license_scope` · `license_review_needed` (compliance_capture.py); hoisted
`LEGEND` / `fix_hints()` (crawl_audit.py); `run()` returns from `crawl_audit` / `external_pdf`
and `build_report_data()`.

## Verification
1. **No-drift (must pass):** save `audit_<p>.md`, `compliance_<p>.md`,
   `external_pdf_report.md`, `crawl_audit.csv` for `gscc`; run
   `./scrapai audit --project gscc --no-fetch --no-compliance`; `diff` → all four
   byte-identical. Repeat the compliance-MD diff on a project that has snapshots.
2. `.venv/bin/pytest tests/unit/` — green (incl. new tests: `bulk_dedupe_command`, facet/meter
   markup, select→command bar, compliance-row render + clause-snippet escaping, empty project).
3. Build `dashboard_gscc.html`; confirm three tabs; status facets filter the one table; header
   sort; row expand; meters; checkbox→combined dedupe command; compliance expand shows quoted
   clauses; PDF sort-by-links; an injected `<script>`/`onerror` value renders escaped.
4. `./scrapai audit --help` valid; commands still registered.
```
