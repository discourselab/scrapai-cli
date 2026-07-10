# Quality-tool suite — integration handover

**Requested by:** Ranu (project owner). **Status:** built, bug-fixed, restructured and
documented locally (`./scrapai audit` / `overview` / `dedupe` + dashboards + the
`spider-*` maintenance skills). This note is the checklist for folding it upstream.
User-facing reference: [docs/quality.md](../quality.md); skills:
[docs/skills-overview.md](../skills-overview.md).

## What ships (and where)

- `core/quality/` — the engines, restructured into focused modules/packages:
  - `crawl_audit/` — coverage + extraction + inline compliance (orchestrator)
  - `compliance_capture/` — robots / licence / AI signals + snapshot store
  - `corpus.py` — the ONE shared home for the JSONL scan + content fingerprint
    (crawl_audit's *true dupes* and dedupe's collapse set can no longer drift)
  - `dedupe.py` — corpus hygiene (the ONLY mutating command; reversible)
  - `external_pdf.py` — external-PDF host frequency
  - `overview.py` + `overview_dashboard.py` — per-spider content profile + dashboard
  - `dashboard/` — the self-contained interactive audit dashboard (Coverage ·
    Compliance · PDFs), vanilla JS/CSS, every value escaped, `render_dashboard()`
    pure and unit-tested; incl. the per-project PDFs-tab host-exclusion layer
    (`data/<project>/_audit/pdf_exclude.json`, dashboard-only, scaffolded inert)
  - `_env.py` — repo-anchored environment (CLI launcher, settings.py, .scrapy,
    loud `db_query`); every engine works from ANY cwd
- `cli/audit.py`, `cli/dedupe.py`, `cli/overview.py` — thin click wrappers,
  registered in `cli/__init__.py`
- **The `spider-*` skills are part of the product**: `.claude/commands/spider-{repair,
  review,align,slow}.md` + `docs/skills-overview.md`. The audit report and dashboard
  emit `/spider-repair` / `/spider-review` copy-paste commands, so the skills must
  ship wherever the audit does.
- Tests: `tests/unit/test_audit.py` (dashboard render + fixes),
  `test_quality_env.py`, `test_quality_corpus.py` (pinned fingerprint digests),
  `test_crawl_audit_cache.py`, `test_compliance_fixes.py`,
  `test_compliance_robots.py` + `test_compliance_signals.py` (regression pins for
  the robots matcher and legal-text regex batteries).

**History:** the engines began as ports of standalone root scripts; those are kept
at the repo root as frozen `*.superseded` reference copies (never edit/delete).
The ports are canonical and have deliberately diverged since (see below), so the
original "byte-identical to the roots" acceptance test no longer applies — the
current acceptance test is the **golden-master gate**: deterministic cache-only
runs (`audit --no-fetch --no-compliance` + `overview`) on five real projects,
byte-compared across the restructure. The restructure itself changed zero output
bytes.

## Deliberate divergences from the `*.superseded` roots

- **Compliance report-time recomputes** — legal-page prohibitions and the AI-reuse
  aggregate are re-derived from stored snapshots at report time (regex fixes apply
  without re-capture); legacy-format snapshots fall back to their stored concrete
  evidence (tdmrep/tdm_meta/robots_meta/headers) so a genuine reservation is never
  recomputed away.
- **Snapshot write-order** — a dated `compliance.json` is written only for
  REACHABLE domains; unreachable ones get `_capture_failed.json` (older good
  snapshots survive a failed `--refresh`).
- **Sitemap-cache lifecycle** — temp+swap fetches (failure leaves nothing; stale
  content is never served as fresh) + generation-pruning on re-fetch.
- **`db_query` fails loudly** (`ScrapaiCliError`) instead of returning `[]` on a
  broken DB — a failed query can no longer overwrite a good report with an empty one.
- `crawl_audit.run()` accepts `reset` for compliance snapshots; report text points
  at the `./scrapai audit` flags.

## Known, deliberate inconsistencies (documented, not bugs)

- `compliance_summary` (the audit MD's inline compliance cells) assesses the
  UNREFINED latest snapshot, while `build_report_data` (compliance MD + dashboard)
  refines it. Unifying them would change audit-MD cells — left as-is on purpose;
  worth aligning upstream in a change that owns that diff.
- The `_PAGE_PATH` paginated-sitemap probe walks trailing-`/N` URLs; on a
  non-paginated year-archive URL it costs exactly one bounded empty fetch
  (per-cap'd). Assessed and kept.
- "Added by Mirjam"-style attribution comments were cleaned from `core/quality/`;
  the same markers still exist in `core/schemas.py` / `core/extractors.py`
  (outside this tool's scope).
- `.claude/settings.local.json` still allowlists the retired
  `python3 crawl_audit.py` invocation (harmless; user-local file).

## (A) Framework requests still needed for this tool to work fully upstream

The audit reads signals the spiders must *produce*. Outstanding framework changes
(kept out of this copy, which only edits config-level surfaces):

- **Per-crawl stats writer** — the spider's `closed()` handler must write
  `data/<project>/_audit/crawl_stats/<spider>.json` with the HTTP-status histogram.
  The audit uses it for exact **liveness** and to tell `never-ran` from `ran-empty`.
- **Coverage accounting** — the sitemap spider should record `sitemap_total` /
  `eligible` in that stats file while parsing (point-in-time denominator, no
  sitemap-drift re-fetch).
- **`_is_block_page`** — a shared helper so extraction can distinguish a
  Cloudflare/challenge page from real-but-empty content.
- **`ComplianceFileCapture` extension** — crawl-time capture of `/robots.txt` +
  `/llms.txt` + legal pages; the audit's cross-check treats these as the
  authoritative witness.
- **Extractors date/author merge** — so core-field extraction populates the fields
  the audit checks for `required: true` coverage.
- **`crawl-stats.sh` rewrite** — align the shell run-monitor with the stats-file format.
- **Spider name / domain warning** on `spiders import` (mismatches send crawls to
  the wrong folder and confuse the audit).

**Already upstream — SKIP:** relative-`<loc>` resolution, sitemap `deny`
application, core-field prune.

## (B) Reconcile with the repo that is now AHEAD of this copy

- **Liveness** — upstream moved to Pueue + last-item run tracking; this audit reads
  `_audit/crawl_stats/<spider>.json`. Ship the stats writer (A) so both coexist, or
  point the audit at the Pueue/`_stats.json` source.
- **PDFs** — upstream records PDFs as `PDF_MODE` URL-only items; `external_pdf`
  reads an `external_pdf_urls` field on content rows. Reconcile to the new PDF item
  model (the PDFs-tab host-exclusion layer is orthogonal and rides on top).
- **`FIELD_EXTRACT` → `FIELDS` rename** — point the audit's/overview's schema
  reading at `FIELDS` with a `FIELD_EXTRACT` fallback.

## Open follow-ups (moved here from code comments)

- **Language-aware legal pages** — `legal_links()` matches English-ish LEGAL_WORDS
  against URL paths, missing non-English legal pages (aviso-legal, impressum,
  mentions-legales, 개인정보처리방침…). Plan: spiders record their site's legal URLs at
  build time; compliance treats those as authoritative (not subject to the heuristic).
- **Spider-vs-mini-crawl safety net** — spiders now capture legal pages + PDFs as
  content rows; compliance's own mini-crawl is a second, independent pass. Add a
  compare step that diffs the two sets per domain and flags discrepancies.

## Deferred / out of scope

- The "thinktanks" helper scripts (a project-specific inference pipeline).
- `crawl-status` (the live run-monitor) — separate concern.
- `DATA_DIR` defaults to the RELATIVE `./data` in `core/config.py` — the quality
  tools are cwd-proof via `_env.py`, but the framework-level relativity remains.

---

# Bundled change (merged from request 13): ship the slash-command skills

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-07-09)
- **File:** `.gitignore`
- **Type:** repo configuration

## Problem

`.gitignore` excluded the whole `.claude/` directory. But the quality tool
SHIPS three generic slash-command skills in `.claude/commands/` (`spider-review` —
which absorbed the former `spider-repair` — `spider-align`, `spider-slow`; the
team's project-scoped creation skills stay local via explicit ignore entries) — and the audit report + dashboard actively emit
`/spider-repair <project> <spiders>` copy-paste commands, so the skills are
part of the product, not local state. With `.claude/` ignored they would
silently vanish from any commit/PR: the dashboard would generate commands that
run nothing for the next user.

## Change

```gitignore
# .claude is local agent state, EXCEPT the shipped slash-command skills
.claude/*
!.claude/commands/
```

(The parent pattern must be `.claude/*`, not `.claude/` — git cannot re-include
a path under an excluded *directory*.) Local agent state (`settings.local.json`
etc.) stays ignored.

## Verification

`git status` shows `.claude/` (the commands) as trackable while
`git check-ignore .claude/settings.local.json` still ignores local settings.
