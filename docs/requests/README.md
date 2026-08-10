# Framework change requests

> ⚠️ **Framework changes are the exception, not the norm.** The standing rule is
> **spider-config only** — work happens in each spider's `final_spider.json`, never
> in framework code. Editing `core/`, `spiders/`, `settings.py`, middlewares,
> pipelines, etc. changes behaviour for **every project and everyone working in this
> repo**, so it must be avoided. Prefer a spider-config workaround in all cases. A
> framework change is only acceptable when there is genuinely no config-only
> equivalent AND it has been explicitly requested — and then it must be captured as
> a request here and **attributed in the code to the person who requested it**
> (not assumed — multiple people work here). The entries below exist because each was
> explicitly requested; do not treat them as licence to add more.

These docs capture **framework changes** as discrete, reviewable requests — one request per change. They describe the problem, the implemented change (with code where useful), trade-offs, and any config-only alternative.

**This repo instance IS the integration** (a clean clone of upstream main + the
quality tool + these framework changes). Each request doc carries the problem,
the implemented change, and its verification. Numbering ≤14 follows the old
repo's ledger (gaps = requests that were superseded upstream or deliberately
left behind — see the frozen repo for those); 15+ are new to this instance and
are numbered by **logical grouping** (crawl framework → spiders → CLI tooling →
quality tool), not by order of discovery.

**One request doc = one PR.** The map:

| PR | Request doc | Change | Files |
|---|---|---|---|
| 1 | [12-sitemap-pdf-collection.md](12-sitemap-pdf-collection.md) | bugfix: PDF link collection for sitemap spiders (parity with rule-based) | `spiders/sitemap_spider.py` |
| 2 | [05-spider-name-domain-warn.md](05-spider-name-domain-warn.md) | behaviour: name-vs-domain mismatch warns instead of blocking import | `cli/spiders.py` |
| 3 | [06-per-crawl-stats.md](06-per-crawl-stats.md) | per-crawl stats file: `closed()` writer + sitemap counters (merged 06+07) | `spiders/base.py`, `spiders/sitemap_spider.py` |
| 4 | [04-compliance-file-capture.md](04-compliance-file-capture.md) | crawl-time robots/llms witnesses (extension + settings wiring) | `extensions/compliance_files.py`, `settings.py` |
| 5 | [quality-tool.md](quality-tool.md) | the quality tool: audit · overview · dedupe + dashboards + skills (incl. the `.gitignore` skills change, merged 13) | `core/quality/`, `cli/`, `tests/`, `docs/`, `.claude/commands/`, `.gitignore`, `CLAUDE.md`, `README.md` |
| 6 | [14-crawl-all-pueue.md](14-crawl-all-pueue.md) | `crawl-all` enqueues via Pueue (parallel, disconnect-safe) instead of running inline | `cli/crawl.py` |
| — | [11-sitemapindex-deny-regression.md](11-sitemapindex-deny-regression.md) | ⚠ file as an ISSUE, not a PR: possible regression — denies applied to `<sitemapindex>` entries | `spiders/sitemap_spider.py` (verify) |

PRs 1–2 and 6 are small and independent (review-first); 3–4 are the tool's
framework producers (their consumer arrives in PR 5); PR 5 degrades gracefully
if 3–4 are still pending, so the order is a courtesy, not a hard dependency.

The second wave (requests 16–23, 2026-07-10 → 2026-07-19). From this wave on
there is no separate PR counter: **the request number is the PR** (branch
`pr/<nn>-<slug>`), continuing the ledger; 15 was withdrawn, so the wave starts
at 16.

| PR | Request doc | Change | Files |
|---|---|---|---|
| 16 | [16-dead-proxy-fail-open.md](16-dead-proxy-fail-open.md) | bugfix: dead-proxy detection + fail-open to direct; compliance probes can't poison a domain | `middlewares.py`, `tests/` |
| 17 | [17-browser-crawl-reliability.md](17-browser-crawl-reliability.md) | bugfix+feature: all-exception browser crawls exit failed; browser crawls get their own Pueue group | `extensions/browser_wedge.py`, `cli/crawl.py`, `settings.py`, `tests/` |
| 18 | [18-crawl-output-hygiene.md](18-crawl-output-hygiene.md) | bugfix ×2: `--limit` test crawls no longer poison DeltaFetch; same-day reset re-runs supersede today's file only (no append dupes; version history preserved) | `cli/crawl.py`, `tests/` |
| 19 | [19-use-sitemap-replaces-link-following.md](19-use-sitemap-replaces-link-following.md) | bugfix: loud warning that `USE_SITEMAP` disables link-following + docs correction (hybrid crawl = follow-up) | `cli/crawl.py`, `CLAUDE.md` |
| 20 | [20-show-production-output.md](20-show-production-output.md) | bugfix: `show` reads production `crawls/*.jsonl` (DB fallback + `--source`) | `cli/show.py`, `tests/` |
| 21 | [21-jsonapi-repository-harvest.md](21-jsonapi-repository-harvest.md) | feature port: JSON:API / paginated-JSON repository harvest spider | `spiders/repository_spider.py`, `cli/crawl.py`, `tests/` |
| → PR 5 | [22-audit-measurement-and-quiet.md](22-audit-measurement-and-quiet.md) | bugfix bundle: audit measurement accuracy (liveness, PDF-provenance "versions", media locs, CF robots) + quiet default output | `core/quality/`, `cli/audit.py` |
| → PR 3 | [23-sitemap-crawl-denominator.md](23-sitemap-crawl-denominator.md) | bugfix: crawl-recorded sitemap denominator counts unique, non-media pages | `spiders/sitemap_spider.py`, `tests/` |

"→ PR 3 / → PR 5" = fixes to code still in review, appended to those open PRs
rather than opened as new ones. PRs 16–21 are independent of the quality-tool
stack and of each other. (15 was considered — default `ROBOTSTXT_OBEY` to
True — and withdrawn as a framework change: it's a per-project preference,
handled by setting `"ROBOTSTXT_OBEY": true` in that project's spider configs.)

Requests that existed in the old (frozen) repo but do NOT travel to this
instance — superseded by upstream or orthogonal local work — are documented in
the frozen repo's `docs/requests/` and in
[quality-tool-handover.md](quality-tool-handover.md); they are deliberately not
carried here.
