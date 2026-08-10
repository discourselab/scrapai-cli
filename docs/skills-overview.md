# scrapai Skills Overview

The repo ships **three slash-command skills** in `.claude/commands/` — agent
workflows for keeping a project's spiders healthy. They pair with the quality
tools (`./scrapai audit` / `overview` / `dedupe` — see [quality.md](quality.md)):
the audit classifies every spider into status groups; the skills act on them.

Two guarantees hold across all three:

- **Spider-config only** — they edit a spider's own `final_spider.json` and
  re-import it; never `.env`, `settings.py`, framework code, or spider Python.
- **No bulk auto-apply** — every change is *proposed* and applied only on your
  explicit go-ahead.

The two batch skills run a **two-stage per-spider pipeline**: a cheap **probe**
stage does all deterministic measurement and returns a structured evidence
bundle; a stronger **diagnose** stage consumes it and does the triage / verdict /
proposal. The bundle schema lives ONCE, in `spider-review.md` — `spider-align`
references it rather than carrying a drifting copy.

---

## `/spider-review` — the problem-spider skill

Default scope: all four audit problem groups, with the posture following the
group — **repair posture** for `extraction broken` / `incomplete` (a defect is
established; root-cause it and propose a verified fix) and **triage posture**
for `manual review` / `too few pages` (first decide whether there IS a problem:
actually-fine → OK note, fix proposed, `needs full crawl`, or defer). Named
spiders can be reviewed regardless of status. Temporal-coverage analysis is
tool-backed (`./scrapai overview --only <spider>`: date span, per-year
histogram, null %) and judged against the site's own claimed history. PDF checks
follow the row model: visible PDF links must appear as `content_type="pdf"`
rows. Review records (`audit_notes.json` / `audit_sitemap_skip.json`) are
suggest-only, written on explicit approval.

## `/spider-align` — the conformance sweep

Brings every spider in line with the current `project.json` contract and
conventions, and repairs broken ones in the same gated pipeline. Includes
config-modernisation deltas (`FIELD_EXTRACT`→`FIELDS` rename, retired pdf-field
directives to remove, `PDF_MODE` override sanity). Use it whenever project
conventions change and the fleet should follow.

## `/spider-slow` — live-crawl ops

Symptom-driven (not audit-driven). Measures with `./scrapai crawl-status`
(the `last-item` column is the stall signal) and `pueue follow <id>`; classifies
slow / stalled / blocked; kills junk-URL explosions; picks the recovery path —
resume from checkpoint (`pueue kill <id>` → fix → re-enqueue) vs clean restart
(`--reset-deltafetch`). Never touches the running process itself.

---

## How they fit together

```
   [ ./scrapai audit ]     classifies every spider into status groups
        │
   ├─ /spider-review       ALL problem groups → repair or triage per bucket
   ├─ /spider-align        conventions changed → sweep all
   └─ /spider-slow         live crawl misbehaving → ops diagnosis
```

Teams can add their own project-scoped skills alongside these (this repo's
`.gitignore` shows the pattern: track the generic skills, ignore the local ones).
