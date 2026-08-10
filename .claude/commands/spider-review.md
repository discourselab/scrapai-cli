---
description: Diagnose and triage ALL of the audit's problem spiders — repair `extraction broken`/`incomplete`, review `manual review`/`too few pages` (final_spider.json only; proposes, applies on approval — absorbs the former /spider-repair)
argument-hint: <project> [spider ...]
---

You are running `/spider-review`. Arguments given: `$ARGUMENTS`

> **HARD CONSTRAINT — if (and only if) the user approves a fix, the ONLY file you may change is that spider's own `final_spider.json`** (`data/<project>/<spider>/analysis/final_spider.json`), applied via `./scrapai spiders import`. You must NOT edit `.env`, `settings.py` or any Scrapy/framework setting, framework code, spider Python, or any other project file. The `audit_notes.json` / `audit_sitemap_skip.json` review records are also suggest-only — written only on explicit approval (see below).

**What good looks like:** every spider in scope gets a *defensible, evidence-backed verdict* — actually-fine → OK, spider-side fix proposed (verified by a bounded re-test), `needs full crawl`, or not-spider-side → defer. You change NOTHING until the user approves, then only its `final_spider.json`. When the evidence is thin, gather more or ask — never "fix" or condemn a spider that was actually fine.

## Argument handling (do this FIRST)

- The **first** token is the project name. It MUST exactly match an existing project (verify with `./scrapai projects list` / the presence of `data/<project>/project.json`). If no project is given, or the name does not exactly match a real project, **STOP and ask the user which project** — never assume, never fall back to `default`, never risk running on a different project. Proceed only once you have an exact, valid project name.
- Any **remaining** tokens are specific spider names.
  - **If spider names are given:** review exactly those spiders **regardless of their audit status** — *any* spider in the project can be reviewed by name (it doesn't have to be in a particular audit group). Just confirm each named spider exists in the project (`./scrapai spiders list --project <project>`); if one doesn't, flag it.
  - **If NO spider is named:** default to ALL FOUR of the audit's problem groups — **`extraction broken`**, **`incomplete`**, **`manual review`**, **`too few pages`** (exact status-group labels). The per-spider POSTURE follows the group:
    - **Repair posture** (`extraction broken` / `incomplete` — the confirmed-broken buckets): the audit has already established a defect; your job is root cause → verified fix proposal. Lead with the failure-mode triage, not with "is it fine?".
    - **Triage posture** (`manual review` / `too few pages` — the ambiguous buckets): first decide whether there IS a problem. `manual review` = extraction works and it ran, but a concern flag means coverage/quality isn't auto-verified. `too few pages` = barely any output — never fully crawled, genuinely small, or discovery too narrow (triage decides — see Task).
    Both postures run the SAME probe→diagnose pipeline below; only the burden of proof differs (repair assumes a defect until shown benign; triage assumes nothing).

## Ensure a current audit (before selecting targets)

Always refresh the audit first so the `manual review` / `too few pages` lists reflect current state — it is incremental by default (only fetches what's missing):

```bash
./scrapai audit --project <project>
```

The report lands at `data/<project>/_audit/audit_<project>.md` (+ `crawl_audit.csv`, `coverage.csv`, and the interactive `dashboard_<project>.html`); read it to get the `manual review` and `too few pages` lists. Only use `--no-fetch` (fast, cache-only) or `--fetch-all` (force a full sitemap refresh) if the user asks; `--no-compliance` skips the compliance stage when you only need the coverage lists.

## Task

Batch review spiders for the project. **Default (no names given): the audit's `manual review` and `too few pages` groups** — the ambiguous buckets. **When spider names are given: review exactly those spiders, regardless of audit status** — any spider can be reviewed by name. For the default groups: `manual review` = extraction works and the crawl ran, but a concern flag (`no-sitemap` / `sitemap-empty` / `sitemap-drift` / `sitemap-cap-hit` / `thin?` / low `liveness`) means coverage/quality isn't auto-verified. For a `too few pages` spider (barely any output), triage it into one of: **(1) never fully crawled** (only a test run) → hand the user the full production crawl command and mark it `needs full crawl`; **(2) genuinely small / complete site** → confirm via the ground-truth count check (Step 5b) and draft an OK note; **(3) discovery too narrow / extraction failing** (a full crawl DID run but under-collected) → investigate and propose a config fix. **Decide (1) vs (3) from EVIDENCE, never by assumption: check `_audit/crawl_stats/<spider>.json` (a completed full crawl recorded many requests / HTTP responses there even if it yielded few items) and the DeltaFetch cache `.scrapy/deltafetch/<project>/<spider>.db` (≫ output ⇒ it crawled a lot but stored little). If crawl_stats show a substantial crawl, the spider DID run — treat the shortfall as a defect (sub-case 3), do NOT call it "never run" or "interrupted." Only if the evidence is genuinely inconclusive, ASK the user whether a full crawl ran to completion and take their answer as authoritative — never tell the user they didn't run it, and don't ask them to re-run merely to disambiguate.** Your job is to **decide per spider whether there is a genuine problem or the spider is actually correct**. **Focus for PDFs: row discovery, not PDF content.**

**Goal:** Bounded, reproducible assessment of coverage completeness + extraction correctness, including PDF-URL discovery. Corpus-first, then targeted probing. Keep evidence, interpretation, and repairs separate. Reach a verdict and **propose** fixes — do not implement anything until the user gives explicit go-ahead.

**Execution:** process the group in BATCHES of ≤5, each spider through a **two-stage per-spider pipeline**:
- **Stage 1 — probe (cheap model; spawn the Task agent with `model: sonnet`):** one Sonnet agent per spider runs the bounded test crawl and computes ALL measurement — corpus, coverage, temporal, ground-truth, and PDF-URL aggregates — and returns the structured **evidence bundle** (schema in *Stage split* below). It does **not** classify, diagnose, decide, propose, or edit anything.
- **Stage 2 — diagnose (default/Opus):** one Opus agent per spider consumes that spider's evidence bundle and does failure-mode triage → flag validation (4 outcomes) → verdict → proposed repairs → suggested audit records (drafts only) → self-critique, reviews ITS spider only and returns one report. All gating/approval stays here; it decides-then-proposes and the review records stay suggest-only.

Run Stage 1 for the whole batch (≤5 concurrent, never `run_in_background`), then Stage 2 for the batch; finish a batch before the next (12 → 5+5+2). **When you spawn each agent, embed this command's Rules and the Procedure steps that stage owns — especially the HARD CONSTRAINT and the decide-then-propose / suggest-only rules — so every subagent operates under the same constraints.** *(Future option: the same probe→diagnose split can be run as a Workflow `pipeline(probe, diagnose)`; the minimal form here keeps Task batches.)*

## Rules (strict)

- **DECIDE, THEN PROPOSE — do not auto-fix.** Reach a verdict per spider:
  - **(a) actually correct** → recommend it move to the **OK** table;
  - **(b) genuine defect, spider-side and config-fixable** → PROPOSE the fix (verified), and implement it ONLY after the user's explicit go-ahead;
  - **(c) genuine problem that is NOT spider-side** (upstream/site/proxy/framework) → defer with evidence.
  - **(d) never properly crawled** → assign this ONLY when evidence shows no full crawl ran (no/empty `_audit/crawl_stats/<spider>.json`, output consistent with a `--limit` test, no large DeltaFetch cache) OR the user confirms it. NEVER infer it from a low page count alone, and NEVER tell the user "it was interrupted" / "you didn't run it" — if `crawl_stats` shows a substantial crawl, it DID run (→ treat as a defect, sub-case 3). When unsure, ask the user; don't ask them to re-run just to disambiguate. If confirmed never-run → hand the user the **full production crawl** command (`./scrapai crawl <spider> --project <project>`) and mark it `needs full crawl`; do NOT draft an OK note and do NOT treat it as a defect.
  - Bounded verification test crawls are always allowed (read-only — they don't change the spider). Rationale: this table is ambiguous, so a human gates every change to avoid "fixing" a spider that was actually fine.
- **SPIDER-LEVEL ONLY, with push-back before deferring** (applies when a fix is approved). On approval YOU apply it — it lands in the spider's own `final_spider.json` (`data/<project>/<spider>/analysis/final_spider.json`) and is re-imported (`./scrapai spiders import <that file> --project <project>`); never `.env`, settings, framework, or spider Python. Before concluding a fix *can't* be done at the spider level, do not accept that on the first judgement: re-attempt from a different angle, then once more — pushing back repeatedly often surfaces a spider-level fix that wasn't obvious. Only after those genuine retries may you defer it, stating what you tried each time.
- Never full-site re-crawl — the production re-crawl is the user's to run.
- One spider per agent: each owns a single spider and emits one report; never mix spiders. Pause after each batch.
- Don't touch audit tables/status or mark spiders approved — you **recommend** the OK move; the user applies it. Conclusions must be evidence-based.
- **Review records are suggest-only.** The OK recommendation and any sitemap-skip are recorded via the audit's own review files (`audit_notes.json`, `audit_sitemap_skip.json`) — but these are HUMAN records: SUGGEST, never auto-write. Read the `_instructions` in each file (they're auto-refreshed every audit run — follow the live version) and propose entries in your report; write them ONLY after explicit user approval, and NEVER during bulk/batch analysis.

## Stage split (probe vs diagnose)

This command runs as a **two-stage per-spider pipeline** (see Execution above). Each Procedure step below is tagged with the stage that owns it — `[probe]` (cheap measurement), `[diagnose]` (Opus judgment), or `[probe→diagnose]` (the measurement half runs in the probe, the interpretation in diagnose).

- **Stage 1 (probe, cheap) is read-only measurement.** It MUST NOT: classify failure modes, decide the 4-outcome flag/gap validation, choose a verdict, propose or apply a fix, edit `final_spider.json`, run `spiders import`, or draft/write `audit_notes.json` / `audit_sitemap_skip.json`. It measures the CURRENT config and returns the evidence bundle — nothing else. (This is what keeps "a human gates every change" and the "review records are suggest-only" rules intact: the cheap model never touches a gated surface.)
- **Hand-off is the structured evidence bundle** (schema below), so the diagnose stage reasons over clean evidence, not raw dumps.
- **Rationale:** mechanical measurement doesn't need a frontier model; reserving Opus for judgment yields large token savings at equal verdict quality.

**Evidence bundle (Stage 1 returns this per spider):**
- `spider`, `project`, `audit_status` (from `audit_<project>.md`)
- `config_facts` — extractor order, throughput settings, schema fields + declared source per field, rule allow/deny patterns, sitemap flag (verified), name-vs-folder. *(align only: also `contract_deltas` — factual config-vs-`project.json`/conventions differences, listed neutrally, NOT judged actionable.)*
- `corpus` — rows; unique URLs; unique (url,content) pairs; true_dupes; versions; content-present / title-present counts; median content length; empty/thin count; per-field fill rates; PDF-row stats (rows with `metadata_json.content_type="pdf"`: count, unique URLs, same-org vs external by host vs `allowed_domains`); per-year histogram; URL buckets by host + path-shape.
- `crawl_stats` — ran? (file present), requests, items, status/liveness dict, `sitemap_total`, `eligible`, deltafetch-cache size.
- `probe` — per sampled URL (caps: ≤5 HTML, ≤5 PDF-bearing, ≤10 links): fetched-ok?, HTTP status, content length, browser-needed?, visible-vs-extracted notes (facts only).
- `coverage_matrix` — per content type: present / discovered / extracted (Y/N).
- `temporal` — from `./scrapai overview --project <project> --only <spider> --no-html` (the tool computes this; do NOT re-derive by hand): `span` (date_min→date_max), `per_year` (the year histogram), `null_pct` (share with no parseable date; when high, add `url_year_hist` from URL-path dates as fallback), `odd_dates` (out-of-range count); PLUS the probe's own `site_earliest` (the oldest content the SITE claims — from its archive page, earliest sitemap entry, or a first-page-of-last-pagination probe; state the source) and `access_paths` ({archive: Y/N+url, year_filter: Y/N, pagination: Y/N+depth}). Every gap year between site_earliest and now with 0 items goes in `gaps`.
- `pdf_rows` — PDF links visible in the sampled pages' source vs PDF ROWS in the output (`content_type="pdf"`, `found_on` = the page) + missing list. The framework harvests these automatically (`PDF_MODE=links_only` default) — a spider needs NO pdf directives; also record whether the config overrides `PDF_MODE`.
- `ground_truth` *(review only)* — declared total per section (+ source: results counter / last-page×page-size / `$count` / sitemap count), unique rows, captured÷declared %.
- `existing_review_records` — current `audit_notes` / `audit_sitemap_skip` entries for this spider (read-only).
- `signals` — neutral anomaly markers (e.g. "content median < 50 chars", "deltafetch ≫ output", "HTTP 403 seen") — descriptive, **not** a diagnosis.
- `artifacts` — paths to the saved probe outputs (inspect HTML, `analyze`/`try` results) + the exact sample URLs used, so the diagnose stage can drill into a specific page **without re-fetching**.

**Bundle completeness rule (anti-starvation):** every field above is **mandatory**. If the probe genuinely can't measure one (site down, no declared total exposed, browser needed but unavailable), it returns `null` + a one-line `reason` — never omits it. A silently-missing field forces the diagnose stage to re-probe on Opus, throwing away the savings; an explicit `null + reason` lets diagnose either reason around it or commission a targeted follow-up probe (still cheap).

## Procedure

Apply only the steps that bear on this spider's status and flags — a step that doesn't apply gets a one-line "N/A (why)", not a manufactured finding. This is a checklist for thoroughness, not a script to perform: lead with reasoning toward the verdict, not box-ticking.

1. `[probe]` **Context** — read config + `NOTES.md`. Note the content model (HTML articles / structured records / PDF repository — decides Step 6). Verify the sitemap flag independently. Treat every audit flag as a hypothesis, not a fact.

2. `[probe→diagnose]` **Corpus analysis + failure-mode classification (primary evidence)** — the probe computes the corpus aggregates; the failure-mode *classification* below is diagnose. From existing `crawls/*.jsonl` across the FULL corpus: row / unique / duplicate counts; per-year histogram (published_date vs URL-encoded date); content-length distribution + empty/thin count; per-field fill rates (every required field); PDF-row counts (same-org/external); URL buckets by host + path-shape (`/profile/`, `/tag/`, landing pages, indexes). Cross-check `_audit/crawl_stats/*.json`. If anomalies suggest a failure, classify it: *extraction-broken* (pages reached, content empty/short → wrong selector OR CF/decode/DeltaFetch artifact) vs *incomplete* (ran but short → rate-limit/proxy, narrow scope, deny rule, DeltaFetch-stale, un-followed archive). Anomalies here drive Step 3.

3. `[probe]` **Live probe (bounded; mandatory)** — caps: ≤5 HTML, ≤5 PDF-link-bearing pages, ≤10 links. Targeted by Step 2. Confirm: extracted fields match visible content across the age range; low-fill fields are genuinely absent vs missed extraction; PDF URLs visible in the source appear as PDF rows in the output (`content_type="pdf"` with `found_on` = the page). Inspect suspect URLs before judging — never condemn on length/pattern alone: it may be a CF/bot challenge (HTTP 202/403 → re-check `inspect --browser`), a decode error (UnicodeDecodeError on lightweight fetch → retry `--browser`), or a stale-null row + DeltaFetch artifact.

4. `[probe]` **Coverage matrix** — per content type: present / discovered / extracted (Y/N each). Include HTML content and PDF-row discovery.

5. `[probe→diagnose]` **Temporal completeness** — the single strongest coverage signal after ground-truth counts; measure it with the tool, judge it against the SITE's own history.
   - `[probe]` Run `./scrapai overview --project <project> --only <spider> --no-html` and lift the date span, per-year histogram, null-date %, and odd-date count into the bundle — never eyeball-parse dates yourself. If `null_pct` > ~40%, ALSO bucket scraped URLs by the year embedded in their paths (`/2021/05/...`) as `url_year_hist` and say which signal you're using.
   - `[probe]` Establish `site_earliest`: what is the OLDEST content the site itself claims? Check (in order) an archive/annual-report page, the earliest sitemap `<lastmod>`/entry, or the last page of the deepest pagination. Record the value AND its source; if none found, record null + reason.
   - `[probe]` Record `access_paths`: does the site expose an archive section, year filters, or deep pagination (how deep)? Y/N + URL each.
   - `[diagnose]` Judge the SHAPE, not just presence: (a) **truncation cliff** — items stop N years before site_earliest → discovery misses the archive path (typical: RSS-capped feeds, JS 'load-more' never followed, pagination depth limit); (b) **interior gap years** — often a site re-platforming (verify: probe one known-old URL) OR a rules/deny mismatch on the old URL scheme; (c) **single-year/recent-only spike** on a site with a deep archive → the spider only sees the front listing; (d) smooth histogram covering site_earliest→now → temporal evidence FOR completeness (still not proof — pair with ground-truth counts, Step 5b). A high null_pct is NOT itself a defect (many sites don't date pages) — but say explicitly that temporal coverage is then unverifiable from dates and lean on url_year_hist / ground truth instead.
   - `[diagnose]` Any confirmed taper/gap MUST appear in the verdict: it is a coverage gap hypothesis → name the missing access path and the proposed rule change (or defer with what you tried).

5b. `[probe→diagnose]` **Ground-truth count check (decisive)** — the probe captures the declared totals + computes captured÷declared %; the "<95% ⇒ coverage gap ⇒ diagnose discovery" call is diagnose. Internal evidence (no-gap histogram, no cap truncation) shows the *absence of gaps* but NOT completeness — a crawl can uniformly under-collect and still look smooth. Wherever the site declares its own total per content type, capture it and compare to unique rows: a results counter ("of N results"), pagination last-page × page-size, API/OData `$count`, sitemap section count, or load-more totals. Per section: captured ÷ declared = coverage %. <95% → coverage gap → diagnose discovery (pagination stopped early, 2nd URL pattern, cap hit). If no declared total is exposed anywhere, say so explicitly and downgrade coverage confidence to "no ground truth available" — don't claim completeness from internal consistency alone.

6. `[probe]` **PDF-row rule** — evaluate DISCOVERY only — capture, not content. The FRAMEWORK harvests every `.pdf` href on every crawled page as a URL-only row (`content_type="pdf"`, `found_on` provenance; same-org vs external is derived at audit time — both wanted, nothing configured per spider). So the check is: PDF links visible on sampled pages MUST appear as PDF rows in the output. A visible PDF link with no row = the page wasn't crawled (discovery gap) or `PDF_MODE` was overridden — check the config. A dead/unreachable PDF URL is NOT a defect — URLs only; retrieval is the downstream pipeline's job. NEVER propose adding pdf_urls/external_pdf_urls extraction directives — that is the retired field-based mechanism.

7. `[probe]` **Extended probing (only on direct gap evidence)** — expand locally around the detected gap: adjacent navigation, archive sections, alternative access/PDF-link paths. Never full-site.

8. `[diagnose]` **Flag validation (4 outcomes)** — justified-actionable / justified-benign (correct but upstream/cosmetic) / unjustified / inconclusive.

9. `[diagnose]` **Verdict + proposed repairs** — state the verdict per spider (OK-eligible / spider-side fix proposed / needs-full-crawl / deferred — not spider-side). Per issue: observed · root cause · proposed fix · confidence. Verify empirically (bounded test crawl `--limit 5` / corpus check) before claiming high confidence. Implement ONLY after explicit approval; on approval apply to `final_spider.json` and re-import. Apply the push-back rule before deferring anything. *(Verification stays cheap where it can: candidate-selector / corpus checks against the already-saved HTML (`analyze --test`, `try`) are measurement — commission them as a follow-up `model: sonnet` probe rather than burning Opus tool-churn; only a fix whose effect needs a live re-crawl is verified here directly.)*

9b. `[diagnose]` **Suggested audit records (suggest — do NOT auto-write)** — read the live `_instructions` in `data/<project>/_audit/audit_notes.json` and `audit_sitemap_skip.json` and follow them exactly. Then, per spider:
   - **Actually correct → draft an `audit_notes.json` entry**: `status:"ok"` + a SHORT `flag` (the 1–2 most central verified points — state WHAT you verified and the OUTCOME, no volatile per-crawl counts/percentages; include a stable year-span like "all years covered (2017–2026)" when meaningful) + a brief `note` mapping each auto-flag to why it's fine (overflow → `note_long`) + `updated`. Note the promotion rules: an `incomplete` (coverage-shortfall) flag CAN be promoted by a reviewed note vouching it's a false positive, but a spider with genuinely **broken extraction** is NOT promoted by a note (it shows `⚠ reviewed-stale`) — don't claim empty content is fine.
   - **Sitemap is the wrong yardstick** (nav-only / malformed / excludes the real content) → draft an `audit_sitemap_skip.json` entry (`reason` + `updated`); don't restate the reason in the note.
   - Present both drafts in the report. Write them ONLY after explicit user approval.

10. `[diagnose]` **Report (BLUF)** — 3-line summary: verdict (OK-eligible / fix-proposed / needs-full-crawl / deferred) · top finding · confidence. Then: coverage matrix; evidence (corpus + probe + extended); PDF-row + temporal + ground-truth; flag validation; proposed repairs (confidence + verified?); the drafted `audit_notes` / `audit_sitemap_skip` entries (for approval); data hygiene (junk rows) + residual risks; the recommended status move (e.g. "→ OK") for the user to apply; and, for any `needs full crawl` spider, the full production crawl command for the user to run (`./scrapai crawl <spider> --project <project>`).

11. `[diagnose]` **Self-critique** — assume conclusions may be wrong: check missing evidence (unsearched access path, unverified PDF-link path, unread source), misapplied rules, alternative explanations (was a "gap" actually a CF/decode/DeltaFetch artifact?), whether ground-truth was genuinely sought, and whether any proposed fix could break a spider that is actually fine. Revise only on concrete error.

12. `[orchestrator, post-batch]` **Clean-run handover (PRINT — do NOT execute; deletion is the user's job)** — for any spider where the user approved and you applied a fix, print ONE block covering those spiders. For each, delete stale JSON + caches (NOT `.scrapy`, NOT `analysis/*.json`) and re-crawl with `--reset-deltafetch` (which itself clears deltafetch + checkpoint). Tell the user to run it:

    ```bash
    # Clean re-run for fixed spiders in <project> — run this yourself.
    # --reset-deltafetch clears .scrapy/deltafetch + checkpoint, so do NOT delete those manually.
    # Repeat per fixed spider <spider>:
    rm -f  data/<project>/<spider>/crawls/*.jsonl            # stale crawl output
    rm -f  data/<project>/_audit/crawl_stats/<spider>.json   # stale audit stats
    rm -f  data/<project>/_audit/scan_cache/<spider>.json    # stale crawl-scan cache
    rm -rf data/<project>/_audit/sitemap_cache/<spider>_*    # stale sitemap cache
    ./scrapai crawl <spider> --project <project> --reset-deltafetch
    ```
