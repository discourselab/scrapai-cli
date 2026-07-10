# Quality Tools: audit · overview · dedupe

**One read-only view of everything a project has collected — coverage, extraction,
compliance, content profile — plus one explicit, reversible cleanup command.**

Spiders accumulate: some under-collect, some scrape challenge pages, some pile up
duplicate rows, some sites forbid reuse. The quality tools answer, per project:

| Command | Question it answers | Writes |
|---|---|---|
| `./scrapai audit` | Did we get the whole site? Did extraction work? May we crawl/reuse it? Where do the external PDFs come from? | reports + CSVs + HTML dashboard (read-only for crawl data) |
| `./scrapai overview` | What did each spider *actually* collect — sections, date span, field coverage, thin items? | report + CSV + HTML dashboard (read-only) |
| `./scrapai dedupe` | — (the ONE mutating command) | consolidates `crawls/*.jsonl`, originals kept as `*.superseded` |

The split is deliberate: a "show me quality" command must never silently rewrite
your data. The audit only *surfaces* dupey spiders and the copy-paste `dedupe`
command; running it is always a separate, explicit call.

---

## Audit

```bash
./scrapai audit --project gscc                       # full run (first run fetches; then incremental)
./scrapai audit --project gscc --no-fetch --no-compliance --no-html   # fast, cache-only, no dashboard
./scrapai audit --project gscc --refresh             # re-capture compliance (keeps history)
```

Outputs under `data/<project>/_audit/`:

- `audit_<project>.md` — the coverage/extraction report (+ `crawl_audit.csv`, `coverage.csv`)
- `compliance_<project>.md` — robots / licence / AI-signals rollup
- `external_pdf_report.md` — the PDF harvest per spider: external hosts ranked by frequency + same-org counts (built from the crawl's URL-only PDF rows, `metadata_json.content_type = "pdf"`; nothing is ever downloaded under the default `PDF_MODE=links_only`)
- `dashboard_<project>.html` — self-contained interactive view (tabs: Coverage ·
  Compliance · PDFs; sort, facet, search, row-expand, row-select → copy-paste commands)

### Flags

| Flag | Effect |
|---|---|
| `--no-compliance` | skip the compliance stage entirely (read existing snapshots only; fast, zero network) |
| `--refresh` | re-capture compliance for already-snapshotted domains (appends a dated snapshot, keeping history) and retry failed ones |
| `--reset` | re-capture compliance, OVERWRITING prior dated snapshots (no history) |
| `--no-fetch` | never fetch sitemaps; use only cached files + crawl-recorded counts |
| `--fetch-all` | re-fetch every spider's sitemap (refreshes the cache; prunes the previous generation) |
| `--only <spider>` | restrict to specific spiders (repeatable) |
| `--no-cache` | ignore the per-file crawl-scan cache; re-read every `crawls/*.jsonl` |
| `--per-cap N` / `--global-cap N` | max sitemap fetches per spider (80) / overall (2000) |
| `--no-browser-retry` | don't retry failed sitemap fetches with `--browser` |
| `--no-html` | skip building the HTML dashboard |

### Status taxonomy

Every spider lands in exactly one group (precedence: "did a real crawl run" and
"does extraction work" are decided BEFORE coverage, so an odd sitemap can never
mask broken selectors):

| Status | Meaning | Next step |
|---|---|---|
| `extraction broken` | pages reached but content came back empty — selectors wrong, or a Cloudflare/decode/DeltaFetch artifact | `/spider-repair` |
| `incomplete` | ran but fell short — verified coverage < 90%, or the DeltaFetch cache holds far more than the output (`deltafetch-stale`) | `/spider-repair`, then re-crawl |
| `too few pages` | little/no output — `never-ran` (no production crawl yet) vs `ran-empty` (ran, produced 0) vs `small/partial` | full crawl, or `/spider-review` triage |
| `manual review` | extraction works and it ran, but a concern flag means coverage/quality isn't auto-verified | `/spider-review`, then record the verdict |
| `ok` | passed everything (`✓ reviewed` when promoted by a human note) | — |
| `discarded` | deliberately dropped source (recorded in `audit_notes.json`) | — |

The audit assesses **HTML vs PDF harvest separately**: `scraped`/`content%` cover HTML article rows only, the `pdf` column counts harvested PDF documents (`(N ext)` = external hosts), and a spider that harvested only PDFs gets the `pdf-only` flag instead of a false `ran-empty`.

Common flags: `thin? <median>` (over-broad rules?) · `no-sitemap` / `sitemap-empty` /
`sitemap-drift (m/e)` / `sitemap-cap-hit` / `found sitemap empty` (why coverage is
unverifiable) · `liveness N%` (dead sitemap URLs) · `deltafetch-stale` (cache ≫
output → `--reset-deltafetch`). The report's *Notes & definitions* section and the
dashboard glossary tooltips define every flag precisely.

### Review records (human-owned)

Two per-project JSON files under `_audit/` carry HUMAN verdicts — agents may
*suggest* entries but must never write them without explicit approval (their
`_instructions` keys, refreshed every run, say the same):

- `audit_notes.json` — review notes keyed by spider. `{"status": "ok", "flag": "…",
  "note": "…", "updated": "…"}` promotes a reviewed spider to `ok` (`✓ reviewed`);
  `"status": "discarded"` drops it. A note without a `status` is inert. A spider
  with genuinely broken extraction is never promoted by a note (shows `⚠ reviewed-stale`).
- `audit_sitemap_skip.json` — "this spider's auto-discovered sitemap is the wrong
  coverage yardstick" entries (`reason` + `updated`).

### Caches (all under `data/<project>/_audit/`)

- `scan_cache/<spider>.json` — per-file crawl-scan counts keyed by (size, mtime);
  unchanged JSONL reloads instantly. `--no-cache` bypasses (still rewrites).
- `sitemap_cache/<spider>_<n>/` — fetched sitemap XML. Fetches are temp+swap: a
  failed fetch leaves nothing (so the default mode retries next run), and a
  re-fetch replaces the spider's whole previous generation. `_smprobe` /
  `_robots` / `_nositemap` record discovery results so the default (`missing`)
  mode never re-probes a resolved site.
- `compliance/<org>/<date>/` — dated compliance snapshots (robots.txt, legal
  pages, `compliance.json`). Written only for REACHABLE domains; an unreachable
  domain gets `_capture_failed.json` instead (retried only with `--refresh`).
  First run with no cache fetches robots/legal pages via `inspect` (minutes);
  cached after.

### How read-only is it?

Crawl data (`crawls/*.jsonl`, spider configs, the DB) is **never** touched. The
audit does maintain its own `_audit/` state: the caches above, pruning
crawl_stats/scan_cache for spiders whose data folder was deleted, refreshing the
`_instructions` line in the review-record files (entries untouched, atomic
writes), and scaffolding an inert `pdf_exclude.json` template on first dashboard
build. `dedupe` is the only command that rewrites crawl output.

---

## Overview

```bash
./scrapai overview --project thinktanks
./scrapai overview --project gscc --only rmi_org --thin-chars 300 --no-html
```

Per spider: sections (from URL paths + per-allow-rule yield), publication-date
span + null % + per-year histogram, per-field coverage %, thin-item %, degenerate
(constant) fields, off-domain URLs, and sample titles. Writes
`overview_<project>.md` + `.csv` + `overview_<project>.html`. Complementary to the
audit — it never recomputes coverage-vs-sitemap or dupes.

Flags: `--only <spider>` (repeatable) · `--thin-chars N` (default 200) · `--no-html`.
In the dashboard, the null-date and thin meters are lower-is-better (green = low).
A `date-null N%` flag alone is informational and does not mark a spider for attention.

---

## Dedupe

```bash
./scrapai dedupe --project gscc                    # url+content: collapse identical re-scrapes
./scrapai dedupe --project gscc --only rmi_org     # one spider
./scrapai dedupe --project policy --latest-only    # newest row per URL (drops old versions)
```

Duplicate rows pile up when a crawl is re-run with `--reset-deltafetch` (the
date-named JSONL appends another full copy). Dedupe consolidates each spider's
`crawls/*.jsonl` into ONE file:

- default key = URL + content fingerprint — collapses identical re-scrapes but
  KEEPS genuinely-changed versions of a page (lossless for changed content);
- `--latest-only` key = URL — keeps only the newest row per URL;
- every source file is first renamed aside as `*.superseded` (reversible; re-runs
  overwrite the same shadow, so backups never accumulate); malformed / no-URL rows
  are always kept.

The fingerprint (and the volatile-field set it ignores) is shared with the audit
via `core/quality/corpus.py`, so the report's `true dupes` count always equals
exactly what dedupe collapses.

---

## Workflow with the maintenance skills

The audit classifies; the `spider-*` skills act (propose-then-approve, spider
config only — see [skills-overview.md](skills-overview.md)):

```
./scrapai audit --project <p>
   ├─ ANY problem group              → /spider-review <p>    (repair or triage per bucket)
   ├─ conventions changed            → /spider-align <p>     (whole-project sweep)
   └─ dupey spiders                  → ./scrapai dedupe <copy-paste from dashboard>
```

The dashboard's row-select bars build these commands for you (select rows → copy).

## Engine layout (for maintainers)

`cli/{audit,dedupe,overview}.py` are thin click wrappers over `core/quality/`:
`crawl_audit/` (coverage engine), `compliance_capture/` (robots/licence/AI),
`external_pdf.py`, `overview.py`, `dedupe.py`, `corpus.py` (shared JSONL scan +
fingerprint), `dashboard/` + `overview_dashboard.py` (self-contained HTML),
`_env.py` (repo-anchored CLI/DB access). Each engine exposes `run(project, opts)`
returning its structured result. The former standalone root scripts are frozen as
`*.superseded` reference copies. Integration/handover notes:
[docs/requests/quality-tool.md](requests/quality-tool.md).
