# Quality Audit Tool — Plan

> **Historical plan — the tool is built and shipped.** Current docs: [docs/quality.md](../quality.md); handover checklist: [docs/requests/quality-tool.md](../requests/quality-tool.md).

> **▶ RESUME / HOW TO BUILD (read first).** This plan is approved and ready to build.
> To execute: turn OFF plan mode, then build in this order —
> 1. **`core/quality/`** — faithful COPIES of the four root scripts
>    (`crawl_audit.py`, `compliance_capture.py`, `external_pdf_report.py`,
>    `dedupe_crawls.py`), each given a `run(project, opts)` that returns its structured
>    result and still writes its MD/CSV. Computations copied verbatim (no logic changes);
>    resolve paths via `from core.config import DATA_DIR`; import each other by package path.
> 2. **`cli/audit.py`** (`./scrapai audit`) + **`cli/dedupe.py`** (`./scrapai dedupe`) —
>    thin Click commands calling `core.quality.*`; register both in `cli/__init__.py`.
> 3. **Dashboard** — self-contained tabbed HTML rendered from the engines' returned
>    objects (built by default; `--no-html` to skip; copy-paste dedupe command, no execute button).
> 4. **`tests/unit/test_audit.py`** + short `CLAUDE.md`/`README` notes.
> 5. **`docs/requests/quality-tool.md`** — the handover note (buckets A & B below).
>
> **Hard constraints:** the four ROOT scripts stay UNTOUCHED as backup (never edit/delete).
> **No-drift check is the acceptance test:** the copies must produce byte-identical
> `crawl_audit.csv` / PDF output to the untouched originals. Framework edits
> (`cli/__init__.py`, `CLAUDE.md`, `README`) are user-authorized. Match the `crawl-status`
> house style (commit `1a97b83`). Full detail below.

## Context
You've written four scripts that assess scrape quality (`crawl_audit.py`,
`compliance_capture.py`, `external_pdf_report.py`, `dedupe_crawls.py`). They work, but
they're scattered, run one at a time, and each emits its own separate file. Goal: fold
them into **one tool you can run locally** to inspect a project's quality, and give your
collaborator a **note** on the framework changes needed to integrate it upstream.

## The idea that keeps it elegant
The four scripts are four **lenses on one thing — a project's crawl corpus**:
- `crawl_audit` → coverage (did we get the whole site?) + extraction quality
- `compliance_capture` → may-we-crawl / may-we-reuse
- `external_pdf_report` → where external PDFs come from
- `dedupe_crawls` → corpus hygiene — **the only one that changes files**

Three are read-only reports; one mutates. So the split is natural:
- **One read-only `audit`** runs the three report lenses and gives a single combined view.
- **`dedupe` stays separate and deliberate** — a "show me quality" command must never
  silently rewrite your data. The audit can *say* "spider X has N dupes, run dedupe",
  but the destructive step is always an explicit, separate call.

And one principle handles "MD **and** HTML" without double work:
**the lenses remain the source of truth; HTML is just a second view of the files they
already write.** Never render the same report twice.

## Design — a `./scrapai` command in the repo's house style (refined after review)
Match how the collaborator shipped `crawl-status` (commit `1a97b83`): a thin **Click
command** in `cli/`, registered in `cli/__init__.py`, with a unit test and a short
`CLAUDE.md`/`README` note — so the upstream handoff is near drag-and-drop.

**User directive:** COPY the engine code into the proper `core/` location and wire the
`cli/` commands to it exactly as the real repo would — self-contained, house-style. The
**root scripts are kept untouched as backup** (never deleted/edited). Framework edits are
explicitly authorized by the user.

**Key facts that keep this safe:**
- `crawl_audit.py` is **already the orchestrator**: it runs coverage + extraction quality
  **and** compliance inline (`--no-compliance` / `--refresh-compliance`, imports
  `compliance_capture`). So "audit does everything" is ~80% already built.
- Net-new work: copy the engines into `core/quality/`, add `external_pdf`, render HTML,
  add CLI wrappers + wiring.
- The copies must produce **identical numbers** to the root backups — we verify by
  comparing outputs (the untouched originals are the reference).

1. **`core/quality/` — the engine (COPIES of the root scripts, house-style).** Faithful
   copies of `crawl_audit.py`, `compliance_capture.py`, `external_pdf_report.py`,
   `dedupe_crawls.py` refactored to: expose a `run(project, opts)` that **returns its
   structured result** (and still writes its MD/CSV), resolve paths via `from core.config
   import DATA_DIR` (locally = `./data`, so output is identical), and import each other by
   package path. Computations copied verbatim — no logic changes.

2. **`cli/audit.py` — the one command.** `@click.command("audit")` with `--project`,
   `--no-compliance`, `--refresh`, `--reset`, `--no-html`. Thin: parses options, calls
   `core.quality.crawl_audit.run()` (coverage+extraction+compliance) →
   `core.quality.external_pdf.run()`, prints a compact per-spider summary, writes a
   combined `index.md`, **and builds the HTML dashboard by default**.
   → `./scrapai audit --project gscc`
   - Compliance is **cache-first**; `--refresh` re-fetches (dated snapshot), `--reset`
     overwrites, `--no-compliance` skips.
   - **First-run cost:** with no compliance cache, first run fetches all domains via
     `./scrapai inspect` (minutes); log clearly; cached after.

3. **`cli/dedupe.py` — separate command** (mutating; explicit). Calls
   `core.quality.dedupe.run()`. → `./scrapai dedupe --project gscc`.

4. **Dashboard (built automatically; `--no-html` to skip).** Renders from the engines'
   **returned structured objects** (NOT by re-parsing markdown) into **one self-contained
   HTML file** with tabs (Coverage · Compliance · PDFs) — inline CSS/JS, `html.escape` on
   all values, no server, no new dependency.
   - **Dedupe surfaced safely, NOT executed:** flags dupey spiders and shows a copy-button
     command (`./scrapai dedupe --project X --only <spider>`). No live delete button.

5. **Wiring:** `cli/__init__.py` gets two `add_command` lines; **`tests/unit/test_audit.py`**
   tests pure functions (dashboard render from a fake result, dupe-command generation);
   short `CLAUDE.md` + `README` note — all per house style.

**Root scripts = backup:** the originals in the repo root are **left exactly as they
are**. `core/quality/` is the wired, canonical copy; nothing is deleted or duplicated
away.

**Framework touch (user-authorized):** edits `cli/__init__.py`, `CLAUDE.md`, `README`,
adds `core/quality/` + `cli/audit.py` + `cli/dedupe.py`. Explicitly authorized; handover
note attributes it to the user.

**Edge cases:** project with no crawls → report gracefully; `GENERATED_URLS` spider (no
static start_urls/sitemap) → mark coverage N/A, not 0%.

**Why this beats the "big refactor" version:** smallest new code; zero change to the
numbers you're assessing; HTML is a pure add-on that can't break the core reports; fully
reversible. (The duplicated helpers between `crawl_audit` and `dedupe` are noted as a
*future* cleanup in the handover, not done now — deduping them risks changing dedup
behaviour.)

## Explicitly out of scope
- No rewrite of the big scripts' internals.
- The 8 "thinktanks" helper scripts (not yours; a project-specific inference pipeline).
- `crawl-status` (collaborator's live run-monitor) — separate concern, possible future
  integration only.

## Works locally today (verified)
- Data exists across projects (`gscc`, `policy`, `policy_CARDS`, …); several already
  have `_audit/` outputs.
- The liveness note-files `audit` reads **exist locally**
  (e.g. `data/policy_CARDS/_audit/crawl_stats/who_int.json`), so nothing is missing.

## Handover note → `docs/requests/quality-tool.md` (a required deliverable)
Plain checklist for the collaborator. Two questions it must answer:

**(A) What framework requests still need integrating for this tool to work upstream:**
- per-crawl stats writer (#5), coverage accounting (#6), `_is_block_page`,
  `ComplianceFileCapture` extension, extractors date/author merge, `crawl-stats.sh`
  rewrite, spider name/domain warning.
- (For reference — already upstream, so SKIP: relative-loc resolution, sitemap deny,
  core-field prune.)

**(B) What must change so the tool works with the repo that's now AHEAD of this copy:**
- **liveness** — upstream moved to **Pueue + last-item**; audit reads `_stats.json` →
  reconcile (either ship the stats writer, or read Pueue like `crawl-status` does).
- **PDFs** — upstream now records PDFs as **`PDF_MODE` URL-only items**; `external_pdf`
  reads an `external_pdf_urls` field → reconcile to the new PDF model.
- **`FIELD_EXTRACT` → `FIELDS`** rename (back-compat alias exists) — audit reads `FIELDS`.
- Also flag the future cleanup: extract the shared URL/JSONL/fingerprint helpers.

## Verification
1. **No-drift check (most important):** run the untouched root `python3 crawl_audit.py
   --project gscc` and the new `./scrapai audit --project gscc --no-compliance --no-html`
   and diff the resulting `crawl_audit.csv` — must be identical (proves the copy didn't
   change the numbers). Repeat spot-check for `external_pdf`.
2. `./scrapai audit --project gscc` (and `policy_CARDS`) → runs, prints the summary,
   writes the per-lens MD/CSV + `index.md`, and builds the HTML dashboard.
3. Open the dashboard → tabs (Coverage · Compliance · PDFs) render; numbers match the
   MD/CSV; dupey spiders show a copy-paste dedupe command.
4. `./scrapai dedupe --project <p>` on a copy of a crawl dir → `.superseded` renames +
   counts match the root `dedupe_crawls.py`.
5. `./scrapai audit --help` / `./scrapai dedupe --help` → commands are registered and
   discoverable.
