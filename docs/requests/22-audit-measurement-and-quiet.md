# 22 — Audit: measurement-accuracy fixes + minimal default output

**Requested by:** MirjamOdile (2026-07-16)
**Type:** bugfix bundle (audit scoring accuracy) + UX (quiet by default)
**Status:** Fixes A, C, D, E applied and verified on a production project
(C/D syntax/logic-checked but not yet exercised live — they only fire on the
sitemap FETCH path and verification ran `--no-fetch`; run a normal fetching
audit, e.g. re-check that the CF-guarded site in Fix D is discovered rather
than mislabelled `no-sitemap`). Fix B implemented **presentationally** after the counting
approach was tried, shown to break the audit↔dedupe invariant, and reverted —
see the Fix B section.
*(Numbered 23 before the 2026-07-16 renumbering. The spider-side
"Fix C-companion" moved to request 19, where the sitemap-spider work lives.)*

These are the audit-side "measurement bugs" found during a project review:
the audit scores against a corrupted denominator / fingerprint, so it
flags healthy spiders as broken and stays silent on genuinely broken ones. All
fixes are audit-only (they change reported numbers, never crawl behaviour or
data).

---

## Fix A — liveness treats transient 5xx as dead URLs

`crawl_stats_liveness()` bucketed 5xx with 4xx, so a crawl that threw transient
503s had its `eligible` denominator shrunk and its coverage under-reported.
Observed: one spider read "liveness 56%" from 810×503 (transient); real
coverage ~97%.

**File:** `core/quality/crawl_audit/spiders_db.py` — only 4xx count as dead
(the URL doesn't exist); 5xx are transient server errors, excluded from the
denominator entirely.

**Verified:** that spider moved `manual review` (liveness 56%, coverage
172%) → `ok` (eligible 599→1064, coverage 97%, flags cleared).

**Test note:** the audit-integration expectation in
`tests/unit/test_crawl_stats_writer.py` is updated alongside request 19 (that
file belongs to the per-crawl stats PR).

## Fix B — "versions" inflated by PDF `found_on` provenance — presentational split

**Symptom:** the content fingerprint hashes `metadata_json`, which for PDF rows
carries `found_on`. The same PDF linked from N pages yields N rows with N
fingerprints. Observed: one document-heavy spider reported **10,932 "versions"**
(exact: 12,350 PDF link-occurrences − 1,391 unique ≈ 10,959).

**Why the counting fix is wrong.** Keying PDF rows in `scan_file()`'s `uc` set
by URL alone DID collapse `versions` — but it moved those rows into
`true_dupes`, which the audit defines as **"what default dedupe removes."**
dedupe uses `fingerprint()` (which includes `found_on`), sees each PDF row as
distinct, and **keeps** them; the change made the audit claim dedupe removes
~10,961 rows it actually keeps, breaking the module's core invariant
(crawl_audit and dedupe must agree byte-for-byte on "the same record",
`corpus.py` docstring). That change was applied, verified to break the
invariant, and reverted.

**Implemented fix — presentational, invariant-preserving.** The `uc`/dedupe
counting is untouched. The scan additionally counts the PDF rows' own
`(url, fingerprint)` pairs (`pdf_uc`), so scoring can split the displayed
figure: `pdf_multi = pdf_uc − pdf` (multi-referrer provenance rows — dedupe
keeps them) is reported as its own column, and `versions` now shows only
**HTML** re-fetch churn, which is what its "genuine history from re-fetching
updated pages" description always meant. The duplicate-rows table wording
states that PDF provenance rows are expected and kept.

If collapsing multi-referrer PDF rows in the DATA is ever wanted (dedupe would
then keep one row per PDF, losing which pages cited it), that is a deliberate
`fingerprint()` change with dedupe consequences — out of scope here.

## Fix C — image/media `<loc>`s counted in the coverage denominator (fetched path)

Attachment/media URLs that appear as plain `<loc>`s (WP image/attachment
sitemaps) were counted as content pages, inflating `total`/`eligible`.

**File:** `core/quality/crawl_audit/sitemaps.py` — `is_media_loc()` filters
media extensions out of `collect_pages()`. (`<image:loc>` tags were never
matched by `LOC_RE`; this catches media appearing as a plain `<loc>`.) The
spider-side counter for `USE_SITEMAP` spiders gets the equivalent fix in
request 19.

## Fix D — `no-sitemap` false negative: a Cloudflare robots.txt page reads as valid

`discover_sitemap()`'s robots probe treated any non-empty body as a valid
robots.txt. A Cloudflare "Just a moment" challenge is non-empty HTML with no
`Sitemap:` directive, so discovery concluded "no sitemap" even when robots.txt
really declares one. Observed: a CF-guarded site whose robots.txt declares
`sitemap_index.xml`, but the audit reported `no-sitemap` (hiding a ~50% loss).

**File:** `core/quality/crawl_audit/sitemaps.py` — a robots body that looks
like HTML (`_looks_like_html`) is treated as blocked and retried through the
browser before being trusted. Note: a cached `_nositemap` marker means the
improvement only takes effect on a `--fetch-all` (or after the marker is
cleared).

## Fix E — minimal default output + `--verbose`

The audit used to stream a line per spider, dump the entire external-PDF report
to stdout, and print per-organisation compliance detail. The DEFAULT is now
minimal — stage markers, a transient rich progress bar over the scoring loop, a
compliance summary line, and the completion summary — with the full detail
behind `--verbose` (`cli/audit.py`, `core/quality/crawl_audit/engine.py`,
`core/quality/external_pdf.py`; the flag is mirrored into the `python -m`
path).

**Verified:** default `./scrapai audit` prints stage markers + progress bar +
summary; `--verbose` restores per-spider lines, the full external-PDF report,
and per-org compliance output.

## Impact

- Coverage numbers stop lying: transient-5xx false "liveness" flags disappear,
  the 10,932 phantom versions are shown as PDF provenance instead of content
  churn, and CF-guarded sites are correctly discovered instead of mislabelled
  `no-sitemap`.
- Default `./scrapai audit` output becomes a few progress lines + a summary;
  `--verbose` restores the previous detail.
- All changes are read-only measurement/report fixes — no crawl, spider, or
  data behaviour changes (the one spider-side item lives in request 19).
