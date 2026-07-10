---
description: Sweep ALL spiders in a project — bring each into line with current instructions and repair `extraction broken` / `incomplete` (final_spider.json only; proposes changes, applies on approval)
argument-hint: <project> [spider ...]
---

You are running `/spider-align`. Arguments given: `$ARGUMENTS`

> **HARD CONSTRAINT — the ONLY file you may change is each spider's own `final_spider.json`** (`data/<project>/<spider>/analysis/final_spider.json`), applied via `./scrapai spiders import`. You must NOT edit `.env`, `settings.py` or any Scrapy/framework setting, framework code, spider Python, or any other project file. If a change seems to need any of those, it does not happen here — see the push-back rule below.

**What good looks like:** every spider in the project ends with a clear verdict — *already-conformant* (no change), a *proposed-and-approved* change re-tested in its `final_spider.json` with required fields still populating, or *deferred* with a concrete reason. **This sweep touches working, already-assessed spiders, so a human gates every change — propose each one and wait for explicit go-ahead; never auto-modify a spider that is currently fine.** The only thing changed on disk is spider `final_spider.json` files (and only after approval). No guesses, no unverified edits, and no conformance change that silently regresses a working spider.

## Argument handling (do this FIRST)

- The **first** token is the project name. It MUST exactly match an existing project (verify with `./scrapai projects list` / the presence of `data/<project>/project.json`). If no project is given, or the name does not exactly match a real project, **STOP and ask the user which project** — never assume, never fall back to `default`, never risk running on a different project. Proceed only once you have an exact, valid project name.
- Any **remaining** tokens are specific spider names to act on. If none are given, act on **every spider in the project** (`./scrapai spiders list --project <project>`, cross-checked against the audit) — this is a whole-project sweep, healthy spiders included. If a named spider doesn't exist in the project, flag it and confirm before proceeding.

## Ensure a current audit (before starting)

Always refresh the audit first so each spider's status (`extraction broken` / `incomplete` / `too few pages` / `manual review` / `ok` / `discarded`) reflects current state — it is incremental by default (only fetches what's missing):

```bash
./scrapai audit --project <project>
```

The report lands at `data/<project>/_audit/audit_<project>.md` (+ `crawl_audit.csv`, `coverage.csv`, and the interactive `dashboard_<project>.html`). Read it for each spider's status. (A `discarded` spider is a deliberately-dropped source — skip it.)

## Task

Sweep every spider in the project (or the named selection) and bring each into line with the **current** instructions, while also repairing the genuinely broken ones. **Two triggers, one pipeline:** (a) a **conformance gap** — the spider's config diverges from the current `project.json` contract or the project's conventions; (b) **`extraction broken` / `incomplete`** status in the audit. Both are actionable and flow through the same gated, **propose-then-approve**, spider-level pipeline. **Focus: HTML content + PDF-row discovery (not PDF content extraction).**

**Goal:** Evidence → diagnosis → proposal, kept separate. Propose a change only where directly evidenced (a real divergence or a verified defect) and verified by a bounded re-test; apply only on the user's approval; otherwise defer. Bringing a spider into line must not break it.

**Execution:** process the spiders in BATCHES of ≤5, each spider through a **two-stage per-spider pipeline**:
- **Stage 1 — probe (cheap model; spawn the Task agent with `model: sonnet`):** one Sonnet agent per spider runs the bounded test crawl and computes ALL measurement — config-vs-contract deltas plus corpus, coverage, temporal, and PDF-URL aggregates — and returns the structured **evidence bundle** (schema in *Stage split* below). It does **not** classify, diagnose, decide, propose, or edit anything.
- **Stage 2 — diagnose (default/Opus):** one Opus agent per spider consumes that spider's evidence bundle and does conformance/failure-mode triage → gap + flag validation (4 outcomes) → proposed changes → self-critique, assesses ITS spider only and returns one report of proposed changes (it does not apply them). All gating/approval stays here.

Run Stage 1 for the whole batch (≤5 concurrent, never `run_in_background`), then Stage 2 for the batch; finish a batch before the next (12 → 5+5+2). **When you spawn each agent, embed this command's Rules and the Procedure steps that stage owns — especially the HARD CONSTRAINT (final_spider.json only) and the push-back rule — so every subagent operates under the same constraints.** *(Future option: the same probe→diagnose split can be run as a Workflow `pipeline(probe, diagnose)`; the minimal form here keeps Task batches.)*

## Rules (strict)

- **SPIDER-LEVEL ONLY, with push-back before deferring.** Every change lands in the spider's own `final_spider.json` and is re-imported (`./scrapai spiders import <that file> --project <project>`) — never `.env`, settings, framework, or spider Python. Before concluding a change *can't* be done at the spider level, do not accept that on the first judgement: genuinely re-attempt it from a different angle, and then once more. Pushing back repeatedly often surfaces a spider-level way to do it. Only after those genuine retries may you defer it — and then state what you tried each time and why it failed.
- **PROPOSE, then apply on approval — never auto-modify.** Because this sweeps working/assessed spiders, it changes nothing on its own: for each spider, diagnose and PROPOSE the change(s) with evidence, and apply to `final_spider.json` (+ re-import) ONLY after the user's explicit go-ahead. Bounded verification test crawls (`crawl --limit 5`) are always allowed — they don't change the spider. Every change you propose must be backed by a bounded re-test showing required fields still populate (no regression); a conformance change that would drop/empty a required field is a regression — don't propose it, defer. When in genuine doubt whether a divergence is even wrong, treat it as a hypothesis and verify before proposing.
- Never full-site crawl — the production re-crawl/backfill is the user's to run.
- One spider per agent: each owns a single spider and emits one report; never mix spiders. Pause after each batch.
- Don't touch audit tables/status or mark spiders approved. Implement only directly-observed + verified changes; otherwise record as deferred.
- **Review records are suggest-only.** If you find a spider's auto-discovered sitemap is the wrong coverage yardstick (nav-only / malformed / excludes the real content), you may SUGGEST an `audit_sitemap_skip.json` entry — read the `_instructions` in `data/<project>/_audit/audit_sitemap_skip.json` and follow them, but never auto-write it; propose it and write only on the user's explicit approval. Likewise never write `audit_notes.json` entries yourself. (Changing the spider's own `final_spider.json` is fine; recording a review verdict is the human's call.)

## Stage split (probe vs diagnose)

The two-stage pipeline, the **evidence-bundle schema**, and the **bundle-completeness
rule** are IDENTICAL to `/spider-review`'s — read `.claude/commands/spider-review.md`
§ *Stage split (probe vs diagnose)* and use that schema verbatim. One align-only
addition: `config_facts` also carries `contract_deltas` — factual
config-vs-`project.json`/conventions differences, listed neutrally, NOT judged
actionable (judging is Stage 2's job, step 8). Keeping the schema in ONE file is
deliberate: it drifted when each skill carried its own copy.
## Procedure

Apply only the steps that bear on this spider's divergences and flags — a step that doesn't apply gets a one-line "N/A (why)", not a manufactured finding. This is a checklist for thoroughness, not a script to perform: lead with reasoning, not box-ticking.

0. `[probe→diagnose]` **Conformance check (every spider, even healthy ones)** — the probe records the raw config-vs-contract deltas (`contract_deltas`); deciding which are actionable vs benign is diagnose (folds into step 8). Read the current `data/<project>/project.json` (the contract) and the project's conventions (CLAUDE.md / docs: extractor order, throughput settings, scope/exclusion policy, naming, sitemap/pagination, PDF-URL capture). Compare the spider's config against them and list each divergence as an actionable gap, e.g.:
   - **Schema coverage** — every `required: true` field has a source (generic extractor, `FIELDS` directive, or callback).
   - **Framework-migration deltas** (aligning a project migrated from the old field-based KB, or any config predating the current framework): `FIELD_EXTRACT` key still present → propose the rename to `FIELDS` (the alias works, but configs should use the current key); leftover `pdf_urls`/`external_pdf_urls` extraction directives → propose their REMOVAL (the framework harvests PDF rows; the directives produce redundant fields and confuse the schema); a `PDF_MODE` override → verify it's intentional; a dedicated pdf-index helper spider (created because the old system needed one to walk a PDF listing) → flag as possibly REDUNDANT under the row model — verify the parent spider's PDF rows cover it before proposing retirement (retirement itself is the user's call, not a config edit).
   - **Extractor strategy** — matches the project's rule for its schema (core-only → `["trafilatura","newspaper"]`; non-core fields → directives/pure-CSS as the project dictates).
   - **Throughput** — `DOWNLOAD_DELAY` / `CONCURRENT_REQUESTS` / autothrottle match the project default unless the site is fragile (note why if it deviates).
   - **Scope/exclusion** — rules follow the current exclusion policy; no retired pdf-field directives present (the framework harvests PDF rows).
   - **Naming** — spider name == domain-based folder.
   Treat every gap AND every audit flag as a hypothesis, not a fact.

1. `[probe]` **Context + status** — note the audit status and content model + sitemap (verify the sitemap flag independently). A `too few pages` / `manual review` spider is for `/spider-review` to triage — here, only act on a clear conformance gap or `extraction broken` / `incomplete`; otherwise note it and move on.

2. `[probe→diagnose]` **Corpus + failure-mode triage (primary evidence)** — the probe computes the corpus aggregates + got-vs-expected; the failure-mode *classification* below is diagnose. For a broken/incomplete spider, from existing `crawls/*.jsonl` + `*_audit/crawl_stats/*.json` compare got-vs-expected and CLASSIFY before touching anything:
   - *Extraction-broken* (pages reached, content empty/short) → selector wrong OR artifact: CF/bot-challenge (HTTP 202/403 — re-check `inspect --browser`), decode error (UnicodeDecodeError on lightweight fetch → retry `--browser`), or stale-null row + DeltaFetch.
   - *Incomplete* (ran but short) → rate-limit/proxy (403s + TunnelError), too-narrow scope, a deny rule dropping valid URLs (e.g. Drupal `?page=` sitemap children), DeltaFetch-stale (cache ≫ output), or an un-followed archive/index.
   - Do not blindly re-run a ran-empty spider — diagnose first.

3. `[probe]` **Bounded probe (mandatory when changing anything)** — caps: ≤5 HTML, ≤5 PDF-link-bearing pages, ≤3 year points, ≤10 links. Confirm the gap/failure live before acting: a divergence actually produces wrong/worse output; PDF URLs present in source but missing from output; visible-vs-extracted consistency. Inspect suspect URLs before judging — never condemn on pattern/low-length alone (may be a challenge/decode artifact).

4. `[probe]` **Coverage matrix** — HTML content / PDF-row discovery / supplementary pages → present / discovered / extracted (Y/N each).

5. `[probe→diagnose]` **Temporal (ONLY when diagnosing an `incomplete` spider — skip otherwise, it's a locator for coverage shortfalls, not a health check)** — probe: lift span/per-year histogram/null% from `./scrapai overview --only <spider>` (URL-path years as fallback when null% is high) and record `site_earliest` + access paths. Diagnose the SHAPE: a truncation cliff or interior gap vs the site's own history = a discovery gap (missing archive path / pagination depth / denied old URL scheme) — name the path and the fix, or defer with what you tried. High null% alone is not a defect (say temporal coverage is unverifiable from dates).

6. `[probe]` **PDF-row rule** — evaluate discovery only. The framework harvests every visible `.pdf` link as a URL-only row (`content_type="pdf"`; same-org/external derived at audit time). Check: visible PDF links appear as PDF rows; missing = the page wasn't crawled or `PDF_MODE` is overridden. Never propose pdf-field extraction directives (retired mechanism). Do not evaluate PDF content.

7. `[probe]` **Extended probing (conditional — only on direct gap evidence)** — expand locally around the detected branch; follow nearby navigation/archives; test alternate PDF-link discovery paths. Never full-site.

8. `[diagnose]` **Gap + flag validation (4 outcomes)** — justified-actionable / justified-benign (correct but upstream/cosmetic — e.g. an intentional, documented deviation) / unjustified / inconclusive. Apply to both conformance gaps and audit flags. Do NOT "fix" a documented intentional deviation (check `NOTES.md`).

9. `[diagnose]` **Changes (proposed; gated; spider-level)** — per gap/issue: observed · current vs required · proposed change · confidence · decision. PROPOSE the change; implement it ONLY after the user's explicit approval — and only if it's directly observed + reproducible AND verified by a bounded re-test (`crawl --limit 5` / regex-vs-corpus) showing required fields still populate (no regression). On approval, apply to `final_spider.json`, re-import, then re-test. Scope changes: inspect a sample before proposing any deny. Apply the push-back rule before deferring. If the bar isn't met: record as a deferred suggestion, propose nothing. *(Verification stays cheap where it can: candidate-selector / regex-vs-corpus checks against the already-saved HTML (`analyze --test`, `try`) are measurement — commission them as a follow-up `model: sonnet` probe rather than burning Opus tool-churn; only a fix whose effect needs a live re-crawl is verified here directly.)*

10. `[diagnose]` **Report (BLUF)** — lead with a 3-line verdict: conformance status (already-aligned / changes proposed / deferred) · failure status (none / fix proposed / deferred) · confidence. Then: (A) conformance gaps found + outcome each, (B) coverage matrix, (C) probe + extended findings, (D) PDF-row + temporal, (E) gap + flag validation, (F) changes **proposed** (with the verifying re-test result; mark any applied after approval), (G) deferred suggestions, (H) residual risks. Wait for the user's go-ahead before applying.

11. `[diagnose]` **Self-critique** — did I change anything that wasn't actually a divergence or a verified defect? did a conformance change regress a working spider (required field now empty)? was any "fix" masking a CF/decode/DeltaFetch artifact? did I respect documented intentional deviations? did I exhaust spider-level options (with genuine retries) before deferring? Revise only on concrete evidence.

12. `[orchestrator, post-batch]` **Clean-run handover (PRINT — do NOT execute; deletion is the user's job)** — after all batches, print ONE block covering every spider you actually changed. For each, it deletes stale JSON + caches (NOT `.scrapy`, NOT `analysis/*.json` — that holds the change you just made) and re-crawls with `--reset-deltafetch` (which itself clears deltafetch + checkpoint). Tell the user to run it:

    ```bash
    # Clean re-run for changed spiders in <project> — run this yourself.
    # --reset-deltafetch clears .scrapy/deltafetch + checkpoint, so do NOT delete those manually.
    # Repeat per changed spider <spider>:
    rm -f  data/<project>/<spider>/crawls/*.jsonl            # stale crawl output
    rm -f  data/<project>/_audit/crawl_stats/<spider>.json   # stale audit stats
    rm -f  data/<project>/_audit/scan_cache/<spider>.json    # stale crawl-scan cache
    rm -rf data/<project>/_audit/sitemap_cache/<spider>_*    # stale sitemap cache
    ./scrapai crawl <spider> --project <project> --reset-deltafetch
    ```
