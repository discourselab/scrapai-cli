# Quality Tools: audit · overview · dedupe

**One read-only view of everything a project has collected — coverage, extraction,
compliance, content profile — plus one explicit, reversible cleanup command.**

Spiders accumulate: some under-collect, some scrape challenge pages, some pile up
duplicate rows, some sites forbid reuse. The quality tools answer, per project:

| Command | Question it answers | Writes |
|---|---|---|
| `./scrapai audit` | Did we get the whole site? Did extraction work? May we crawl/reuse it? | reports + CSVs + HTML dashboard (read-only for crawl data) |
| `./scrapai overview` | What did each spider *actually* collect — sections, date span, field coverage, thin items? | report + CSV + HTML dashboard (read-only) |
| `./scrapai dedupe` | — (the ONE mutating command) | consolidates `crawls/*.jsonl`, originals kept as `*.superseded` |

The split is deliberate: a "show me quality" command must never silently rewrite
your data. The audit only *surfaces* dupey spiders and the copy-paste `dedupe`
command; running it is always a separate, explicit call.

---

## Audit

```bash
./scrapai audit --project news                       # full run (first run fetches; then incremental)
./scrapai audit --project news --no-fetch --no-compliance --no-html   # fast, cache-only, no dashboard
./scrapai audit --project news --refresh             # re-capture compliance (keeps history)
```

Outputs under `data/<project>/_audit/`:

- `audit_<project>.md` — the coverage/extraction report (+ `crawl_audit.csv`, `coverage.csv`)
- `compliance_<project>.md` — robots / licence / AI-signals rollup
- `dashboard_<project>.html` — self-contained interactive view (tabs: Coverage ·
  Compliance; sort, facet, search, row-expand, row-select → copy-paste commands)

### Flags

| Flag | Effect |
|---|---|
| `--no-compliance` | skip the compliance stage entirely (read existing snapshots only; fast, zero network) |
| `--refresh` | re-capture compliance for already-snapshotted domains (appends a dated snapshot, keeping history) and retry failed ones |
| `--reset` | re-capture compliance, OVERWRITING prior dated snapshots (no history) |
| `--no-fetch` | never fetch sitemaps; use only cached files + crawl-recorded counts |
| `--fetch-all` | re-fetch every spider's sitemap (refreshes the cache; prunes the previous generation) and each site's declared root sitemaps, retrying any that failed |
| `--only <spider>` | recompute only these spiders (repeatable); every other spider's row carries over from the previous report, so the output stays project-wide |
| `--no-cache` | ignore the per-file crawl-scan cache; re-read every `crawls/*.jsonl` |
| `--per-cap N` / `--global-cap N` | max sitemap fetches per spider (80) / overall (2000) |
| `--no-browser-retry` | don't retry failed sitemap fetches with `--browser` |
| `--no-html` | skip building the HTML dashboard |
| `--verbose` / `-v` | full detail: per-spider lines and per-organisation compliance output. Default output is minimal — stage markers, progress bar and the completion summary |

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
unverifiable) · `scraped more than expected (N%)` (coverage over 115% with more than 20 pages scraped: the sitemap
is likely a partial yardstick) · `blocked n (p%)` / `failed n (p%)` (over 5% of the
crawl's requests walled off or unanswered) · `sitemap rejected (N)` (the crawl
fetched N sitemaps it could not parse and dropped their URLs) ·
`deltafetch-stale` (cache ≫ output → `--reset-deltafetch`). The report's *Notes & definitions* section and the dashboard
glossary tooltips define every flag precisely.

Coverage is `scraped ÷ eligible`, where `eligible` is the full rule-matched sitemap
count. For a sitemap spider that is the sitemaps it was given only, whether counted by
the crawl or fetched by the audit: the site's other sitemaps show in the sitemap
listing, never in coverage. URLs the crawl found dead (404) or blocked (403) are not subtracted: they are
pages the spider should have got, so they show as a shortfall.

**dead / blocked / failed** say how the crawl's requests finally ended, read from its
`_audit/crawl_stats/<spider>.json`: dead = 404/410, blocked = 403/429/401, failed = no
response at all after every retry (offsite/robots drops excluded), each as `n (p%)` of
all final outcomes. They are columns in the markdown tables and sit in the row detail
of the dashboard. Blocked or failed over 5% (and at least 5 requests) flags the row
for manual review; dead never flags. `–` means not recorded: the crawl ran before the
stats writer recorded final outcomes (dead/blocked then show per-attempt counts that
include retried attempts, marked `†` in the markdown, for information only, and failed
is unknown), or the spider
is status-blind — Cloudflare/browser mode hands every page back as HTTP 200, so dead
and blocked can't be seen (failed still can). A crawl resumed from a checkpoint has
its legs summed by the writer (the file is stamped `resumed` and `summed`) and reads
like any other crawl. One stamped `resumed` without `summed` covers only its last
leg (an earlier leg died before handing its counters on): its figures end `last
leg`, and a blocked or failed share over the threshold still flags, with the same
`last leg` caveat in the flag. The dashboard's row detail labels per-attempt and
last-leg figures as such.

**Sitemaps given.** For a `USE_SITEMAP` spider the `sitemap` cell reads `given/total`
(e.g. `4/13`) instead of `yes`: how many of the site's sitemaps its `start_urls`
name, of all the site lists — the children of every sitemap index its robots.txt
declares, plus declared leaf sitemaps. The robots `Sitemap:` lines come from disk
(compliance snapshot, crawl witness) where possible, and each declared sitemap is
read from disk first — its host manifest, or the copy the spider's own sitemap fetch
cached. Only what isn't on disk is fetched, once, on the listing's own small budget
(it never counts toward `--global-cap` or raises `sitemap-cap-hit`). A `start_url`
that is robots.txt, or is itself a declared index, counts as giving all of it, and so
does one whose cached copy is a sitemap index (e.g. `/sitemap.xml` serving the
declared `/sitemap_index.xml`); a cache-busted copy (`?v=2`) of a given sitemap counts
once. A declared URL whose content isn't a sitemap (an RSS feed on a `Sitemap:`
line) is skipped with a note, never counted. A given sitemap the site doesn't list
is added to the total and marked *not listed in root index*. `?` = the total is unknown (not fetched under `--no-fetch`, or
a fetch or the sitemap discovery failed — retried only by `--fetch-all`). The cell
links to the spider's list in *Sitemaps given to spiders*, at the end of the report
and under the coverage tables in the dashboard.

**Rejected sitemaps.** A sitemap served as HTTP 200 with a body that is not a
`urlset` or `sitemapindex` (an HTML view of the sitemap, a block page) is dropped
by the crawl's Scrapy along with every URL in it, and the crawl-recorded `total` /
`eligible` leave those URLs out. The sitemap spider records such sitemaps in its
crawl-stats file as `sitemap_rejected`, and the audit flags the row `sitemap
rejected (N)` (N = rejected sitemaps), which sends an otherwise clean spider to
manual review. Where the coverage denominator is the crawl's own sitemap count it
is short, so coverage reads high; a resumed crawl records no count, and the audit
fetches the sitemap itself. A resumed leg also reports the rejections an earlier
leg kept, even when that leg died before handing its counters on. The
spider's block in *Sitemaps given to spiders* lists the rejected URLs, marked
*rejected*, and points to the bodies the crawl kept in
`_audit/sitemap_rejects/<spider>/` (at most 20 per crawl, each cut at 256 KB, with
an `index.json` of URL, status, size and content type; a fresh production crawl
clears the folder, `--limit` runs keep nothing). Read those bodies before fetching
anything. A crawl-stats file from before the key existed can't say, so it never
flags.

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
- `sitemap_cache/_host/<host>/` — the sitemaps a site's robots.txt declares, for
  the `given/total` listing: `sm_<hash>/manifest.json` holds the sitemap's own
  `<loc>`s (children are never fetched), `sm_<hash>.failed.json` marks a failed
  fetch, `declared.json` records a discovery answer when robots.txt lists none
  (`declared.failed.json` a blocked or failed discovery — never stored as "no
  sitemap"). Each is fetched at most once per host, ever; failures are retried only
  by `--fetch-all`. robots.txt already on disk and a cached `/sitemap.xml` probe are
  never fetched again.
- `compliance/<org>/<date>/` — dated compliance snapshots (robots.txt, legal
  pages, `compliance.json`). Written only for REACHABLE domains; an unreachable
  domain gets `_capture_failed.json` instead (retried only with `--refresh`).
  First run with no cache fetches robots/legal pages via `inspect` (minutes);
  cached after.

### How read-only is it?

Crawl data (`crawls/*.jsonl`, spider configs, the DB) is **never** touched. The
audit does maintain its own `_audit/` state: the caches above, pruning
crawl_stats/scan_cache for spiders whose data folder was deleted, and refreshing
the `_instructions` line in the review-record files (entries untouched, atomic
writes). `dedupe` is the only command that rewrites crawl output.

---

## Overview

```bash
./scrapai overview --project proj
./scrapai overview --project news --only acme_org --thin-chars 300 --no-html
```

Per spider: sections (from URL paths + per-allow-rule yield), publication-date
span + null % + per-year histogram, per-field coverage %, thin-item %, degenerate
(constant) fields, off-domain URLs, and sample titles. Writes
`overview_<project>.md` + `.csv` + `overview_<project>.html`. Complementary to the
audit — it never recomputes coverage-vs-sitemap or dupes.

Flags: `--only <spider>` (repeatable; recomputes just those — other rows carry over from `_audit/overview_rows.json`, so the report stays project-wide) · `--thin-chars N` (default 200) · `--no-html`.
In the dashboard, the null-date and thin meters are lower-is-better (green = low).
A `date-null N%` flag alone is informational and does not mark a spider for attention.

---

## Dedupe

```bash
./scrapai dedupe --project news                    # url+content: collapse identical re-scrapes
./scrapai dedupe --project news --only acme_org     # one spider
./scrapai dedupe --project myproject --latest-only    # newest row per URL (drops old versions)
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
`overview.py`, `dedupe.py`, `corpus.py` (shared JSONL scan +
fingerprint), `dashboard/` + `overview_dashboard.py` (self-contained HTML),
`_env.py` (repo-anchored CLI/DB access). Each engine exposes `run(project, opts)`
returning its structured result. The former standalone root scripts are frozen as
`*.superseded` reference copies. Integration/handover notes:
[docs/requests/quality-tool.md](requests/quality-tool.md).
