# Quality-tool shipping pass — handover summary

**What:** full tidy-up of the quality-tool suite (`./scrapai audit` / `overview` /
`dedupe`, dashboards, `spider-*` skills) to make it bug-free, elegant, and ready to
hand to the upstream integrator. Targets THIS repo version; upstream reconciliation
items are listed in [quality-tool.md](quality-tool.md) §(A)/(B) and remain the
integrator's to-do. Nothing was committed; the working tree is the deliverable.

**Proof of no behaviour change for the restructure:** a golden-master gate —
deterministic cache-only runs (`audit --no-fetch --no-compliance` + `overview`) on
five real projects (gscc, thinktanks, policy, kb, mirjam), 42 output files
(MD + CSV + HTML dashboards) byte-compared after every step. The one masked value
is the `stale` column's `⚠ Nd` day counter (elapsed-seconds/86400 — it rolls
continuously with wall-clock time; proven to roll identically under the original
code). Test suite: 224→278 unit tests, all green; pyflakes clean.

## Bugs fixed (each with a unit test)

1. **Licence warn-span corrupted `data-key`** — every low-confidence licence row
   rendered broken `<td>` markup (the ⚠ tooltip's quotes terminated the attribute).
   *dashboard/compliance_tab.py* — plain sort key computed before decoration.
2. **Inverted meter colours** — 95% null-dates / thin-items rendered a GREEN bar.
   `_meter(..., invert=True)` for lower-is-better metrics. *dashboard/widgets.py +
   overview_dashboard.py*
3. **Dead "date-null is informational" logic** — a spider whose only flag was
   `date-null` still got attention=1. *overview.py*
4. **Sitemap-cache lifecycle** — (a) failed fetches left empty dirs that counted as
   "resolved", freezing a transient outage into permanent `total=0`; (b) a failed
   re-fetch could serve the previous run's HTML as fresh; (c) stale cache
   generations were unioned into coverage. Now: temp+swap fetches (failure leaves
   NOTHING), generation-prune on re-fetch, non-empty-file requirement, stale
   `_nositemap` markers cleaned. *crawl_audit/sitemaps.py, engine.py*
5. **Compliance snapshot write-order** — unreachable domains got a dated
   "checked today" snapshot asserting no-signals for a site never read. Now:
   snapshot only when reachable; failure marker otherwise; older snapshots survive
   a failed `--refresh`; `has_capture_failed()` docstring corrected.
   *compliance_capture/capture.py, store.py*
6. **Legacy-snapshot AI-reuse recompute** — 30 of 74 real snapshots are
   legacy-format; their stored concrete evidence (tdmrep/tdm_meta/robots_meta/
   headers) is now honoured when derived keys are absent, so a genuine reservation
   can't be recomputed away. *compliance_capture/report.py*
7. **Silent wrong-cwd behaviour** — relative `./scrapai`, `settings.py`, `.scrapy`,
   and `DATA_DIR` made every engine silently wrong from any other working
   directory (robots judged for the wrong UA; `db_query` returning [] for real
   projects; **reports written to `<cwd>/data/`**). New `core/quality/_env.py`
   anchors everything to the repo root and `db_query` raises `ScrapaiCliError`
   instead of masquerading failure as emptiness — a broken DB can no longer
   overwrite a good report with an empty one. Proven by a foreign-cwd smoke test
   producing byte-identical reports in the right place. (`core/config.py`'s own
   relative default is untouched — framework scope.)
8. **`overview.run()` on a typo'd project** scaffolded `data/<typo>/_audit/` with
   empty reports — now errors out, creating nothing.
9. **tz-aware vs naive date crash** — `overview` crashed on corpora mixing
   timestamp forms (hit live on thinktanks). *overview.py `_parse_date`*
10. **Non-atomic writes to human-edited files** — `audit_notes.json` /
    `audit_sitemap_skip.json` / failure markers now tmp+`os.replace`.
11. Smaller: `javascript:` hrefs rejected in Python `_link` (mirrors the JS guard);
    unchecked compliance rows render 9 keyed cells (sorting was comparing "null"
    against misaligned columns); llms.txt links honour the recorded
    `/.well-known/llms.txt` path; duplicate "unique" stat in the coverage detail;
    `_md_strip` no-op; stdout paths honour `DATA_DIR`; one stale test assertion.

## Restructure (pure code motion, gate-verified byte-identical)

- `corpus.py` (new) — the ONE home for the JSONL scan + content fingerprint;
  crawl_audit's *true dupes* and dedupe's collapse set can no longer drift
  (pinned digest tests + a dedupe smoke on a copied tree).
- `crawl_audit.py` (1,622 lines) → `crawl_audit/` package: engine · scoring
  (new `score_spider()` unit) · sitemaps · spiders_db · review · report ·
  text (ALL prose, LEGEND as triples + `STATUS_LEADS`) · facade.
- `compliance_capture.py` (2,413) → `compliance_capture/` package: signals
  (regex batteries, verbatim) · robots (matcher, verbatim; `ai_bots_blocked` ≡
  `ai_bot_signals()["full"]` proven over every stored robots.txt) · fetch · page ·
  store · assess · capture (staged) · report (per-section builders) · facade.
- `dashboard.py` (1,670) → `dashboard/` package: assets (CSS/JS byte-identical) ·
  widgets · coverage_tab · compliance_tab · pdfs_tab · render · facade. The
  fragile `split("**")` prose surgery became a `STATUS_LEADS` lookup
  (byte-equivalence proven per entry). `overview_dashboard` imports public names.
- Single-pass compliance data: the audit's `build_report_data()` result is shared
  with `write_report` and the dashboard (was recomputed per consumer);
  `lru_cache` on the per-domain JSONL witnesses. Snapshot paths embedded in the
  compliance MD stay repo-relative (never this machine's absolute layout).
- All facades re-export the previous public surface — `cli/*.py` and external
  imports unchanged.

## Skills + docs

- `spider-{align,repair,review}.md`: dead `python3 crawl_audit.py` → `./scrapai
  audit`; stale `ok? (manual review)` label → `manual review` (also in
  skills-overview.md).
- New `docs/quality.md` (full subsystem reference); CLAUDE.md + README quality
  sections updated (overview command + all flags); `quality-tool.md` rewritten as
  the honest integration checklist (divergences, known inconsistencies, upstream
  to-dos); `docs/plans/quality-*.md` marked historical; `core/quality/__init__.py`
  docstring made truthful.

## Deliberately NOT done (assessed, documented)

- `compliance_summary` vs `build_report_data` refinement inconsistency (would
  change audit-MD cells) — see quality-tool.md.
- The "dead" duplicated `.meter` CSS is actually layered base+skin (the first rule
  still supplies `display`/`align-items`; `min-width:2px` keeps the 0% sliver
  visible) — removal would regress rendering; left as-is.
- `_PAGE_PATH` probe kept (one bounded empty fetch, per-cap'd).
- `core/config.py`, `utils/inspector.py`, spider Python, `*.superseded` roots:
  untouched.

## For the reviewer

- Stale artefacts from the OLD code remain on disk for projects outside the gate
  set (e.g. `data/kb_policy_CARDS/_audit/dashboard_*.html` still shows the
  licence-cell corruption) — regenerate with `./scrapai audit --project <p>`.
- A stray `/tmp/data/gscc/` tree exists from the pre-fix foreign-cwd smoke test —
  safe to delete (deletion left to the owner).
- Step-by-step state snapshots (tarballs) + the gate script + goldens live in the
  session scratchpad `patches/` / `golden/` dirs; the original pre-split modules
  are preserved there as `*.moved-original`.

---

# Addendum: adaptation to the current framework (this repo instance)

This instance IS the integration: a clean clone of main + the quality tool,
adapted to the framework's PDF row model. `git diff` against main = the PR.

**Framework additions (3):**
1. `spiders/base.py` `closed()` — per-crawl stats writer (`_audit/crawl_stats/
   <spider>.json`: status histogram, items, requests) — feeds the audit's
   liveness / ran-vs-empty / coverage denominator.
2. `spiders/sitemap_spider.py` — `_sm_total`/`_sm_eligible` counters (crawl-time
   coverage denominator) AND the `links_only` PDF link-scan in `parse_article`
   (PDF collection previously worked only for rule-based spiders).
3. `extensions/compliance_files.py` + `settings.py` EXTENSIONS — crawl-time
   robots/llms witnesses for the compliance cross-check.
   (+ `.gitignore`: `.claude/` → `.claude/*` + `!.claude/commands/` so the
   shipped skills are trackable.)

**Quality-tool adaptation (row model, no field back-compat):**
- A row is productive if it has content OR is a PDF row
  (`metadata_json.content_type == "pdf"`). `scraped`/`content%`/coverage/drift
  judge HTML rows only; PDF rows can neither fake nor mask extraction health.
- HTML-vs-PDF assessment on every surface: audit MD/CSV `pdf (N ext)` column +
  detail split (own/external by URL host vs the spider's DB `allowed_domains`),
  dashboard coverage column + PDFs tab (host frequency from PDF rows, same-org
  counts, `found_on` provenance), overview per-spider PDF stats with article
  metrics (thin%, null-date%, off-domain) computed over articles only.
- New `pdf-only (N)` flag replaces a false `ran-empty` for document-repository
  sites; content% renders empty (not 0%) when a spider harvested no HTML.
- `external_pdf.py` rewritten to read PDF rows (the `external_pdf_urls`
  field-reader is gone); overview reads `FIELDS` (+ the framework's
  `FIELD_EXTRACT` alias) and desugars `sections` configs.
- Scan-cache format gained `pdf`/`pdf_hosts`; old cache entries re-scan once.
- Known limitations (documented in the report legend): a sitemap listing `.pdf`
  locs directly counts them as `pdf` not coverage; in `PDF_MODE=extract` the
  DeltaFetch-stale flag compares against total uniques.

**Verification:** suite 540 → 561 passed (21 new tests: sitemap wiring, corpus
pdf classification + cache migration, scoring split/flags, external_pdf lens,
dashboard/overview surfaces, an engine-level synthetic-project flow) — plus the
open flag `docs/requests/11-sitemapindex-deny-regression.md` (possible upstream
Drupal-deny regression, found during the graft; needs an owner).
