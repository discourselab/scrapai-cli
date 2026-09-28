# Change request: PDF harvest reads non-anchor URL sources

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-09-28)
- **File:** `spiders/base.py` — `_pdf_links()`, new `_PDF_URL_SOURCES`
- **Type:** framework change (coverage bugfix)
- **Requested by:** @MirjamOdile

## Problem

Under the default `PDF_MODE=links_only` the framework records every PDF link on
a crawled page as its own URL-only row (`metadata_json.content_type="pdf"`,
`found_on` provenance). `CLAUDE.md` §7.1 and `docs/settings.md` both describe
this as covering *every* PDF link on the page. It did not: `_pdf_links()`
scanned `a::attr(href)` and nothing else.

Some CMS themes never emit an anchor for a report download. The pattern is a
share/download modal — the page renders a `<select>` of download options and a
submit button wired in JavaScript:

```html
<div class="modal modal--share">
  <p class="title">Please select a download option from the dropdown list …</p>
  <form>
    <select class="download-options">
      <option value="https://…/full-report.pdf">Full report (67 MB)</option>
      <option value="https://…/executive-summary-fr.pdf">Résumé (FR)</option>
    </select>
    <button data-download download>Download</button>
  </form>
```

The URL exists only as an `<option value>`. There is no anchor anywhere on the
page, so the harvest saw nothing and the site's entire report library was
invisible to the crawl — on the one affected site in a production batch, ~320
report PDFs across ~200 distinct documents, none of them reachable any other
way.

This is not a config-fixable gap. `_pdf_links()` is a module-level function
taking only a response; it reads no setting, so no spider config can change
where it looks. A `FIELDS` directive *can* capture the URLs into a schema
field, but that is a different artefact: the downstream pipeline that fetches
documents consumes PDF **rows**, so URLs parked in a field are recorded and
then never collected. Doing it at all also costs a project-schema field, since
`_apply_field_extract()` prunes any item key absent from the project schema.

## Change

One selector constant, used by `_pdf_links()`:

```python
_PDF_URL_SOURCES = "a::attr(href), option::attr(value)"
```

Everything downstream is unchanged: the same `.pdf` suffix test, the same
`response.urljoin()`, the same per-page `seen` dedupe, the same
`_url_only_pdf_item()` row shape. A PDF offered as both an anchor and an option
on one page yields one row.

## Why this does not widen the net

The `.pdf` suffix test is what makes it safe, and the safety is structural
rather than incidental: the change alters *where* the crawler looks for a URL,
never *what counts as a PDF*. Anything newly admitted is by construction a URL
ending in `.pdf`.

Measured against every saved page fixture in this working copy — 303 parsable
files spanning six projects and 263 spiders:

| | |
|---|---|
| `<option value>` attributes present | 1738 (1715 non-empty) |
| …ending in `.pdf` → admitted | **1** |
| …rejected by the suffix test | 1714 |
| shape of every rejected value | no file extension at all |

The rejected values are selection keys — language codes (`en`, `es`), `All`,
years (`1919`, `1827`) — which cannot pass a file-suffix test. Across the whole
fixture set the change admits exactly one URL, on the one site that needs it.

Because fixtures skew toward home pages, where a download modal would not
appear, this was also checked live against report pages at three large PDF
publishers in the fleet: none carried a single `<option>` element.

## Verification

- `tests/unit/test_pdf_collection.py`
  - `test_pdf_links_reads_option_value_download_dropdowns` — absolute and
    relative option values captured, relative resolved against the page.
  - `test_pdf_links_ignores_ordinary_option_values` — language, year and sort
    dropdowns yield nothing.
  - `test_pdf_links_dedupes_a_pdf_offered_as_both_anchor_and_option` — one row.
- Full unit suite green (473 passed).
- Live, end to end on the affected site, with **no PDF-specific spider config
  and the project's stock field schema** — so the harvest is the framework's
  alone:

  | | before | after |
  |---|---|---|
  | rows | 1299 | 1769 |
  | HTML rows | 588 | 588 |
  | PDF rows | 711 | 1181 |
  | **unique PDF URLs** | **104** | **425** |

  Every one of the 1181 PDF rows carries `content_type` + `found_on` with empty
  content — the same shape every other spider produces. HTML rows, titles
  (588/588) and content are unchanged, so nothing regressed on the article path.
  A report reachable only through the dropdown now arrives as an ordinary PDF row
  with `found_on` pointing at its landing page.

## Tracked docs this makes wrong

None. `CLAUDE.md` §7.1 and `docs/settings.md` already claim every PDF link on a
crawled page is recorded; the change makes that claim true where it previously
was not. `docs/settings.md` gains one sentence naming the elements scanned,
because "every PDF link" no longer implies "every anchor".

## Known limitation, unchanged by this request

PDF harvesting still runs only from `sitemap_spider.parse_article()` and
`database_spider.parse_article()`. A section compiled to a custom callback never
scans for PDF links at all, so pages handled by one contribute no PDF rows
regardless of how their PDFs are published. This is the same parity gap flagged
as a follow-up in [12-sitemap-pdf-collection.md](12-sitemap-pdf-collection.md),
and the fix it proposes — a single post-processing hook on yielded responses —
would close both. Left out of scope here: this request is one selector, that one
touches every parse path.
