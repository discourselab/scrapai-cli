# 19 — `USE_SITEMAP` silently replaces link-following (no hybrid)

**Requested by:** Ranu (2026-07-16)
**Type:** bug (framework defect + misleading docs)
**Status:** implemented locally (loud warning + docs fix); the hybrid crawl is
a documented follow-up.
*(Split 2026-07-19 from the short-lived merged "sitemap-spider-correctness"
doc: this half is pure crawling behaviour; the measurement half — the
crawl-recorded denominator — is request 23, patched onto the per-crawl-stats
PR where that code lives.)*

## Problem

Any spider configured with `USE_SITEMAP: true` crawls **only** the URLs its
sitemap lists. The setting does not *add* sitemap enumeration on top of
link-following — it **replaces** the spider class entirely with a sitemap-only
crawler that has no link discovery at all:

- Class swap: `cli/crawl.py` — `use_sitemap` → `spider_class =
  "sitemap_database_spider"`, else `"database_spider"`.
- `spiders/database_spider.py` is a `CrawlSpider` and builds
  `Rule(LinkExtractor(...), ...)` — full link-following.
- `spiders/sitemap_spider.py` is a `SitemapSpider`. It has **no `LinkExtractor`,
  no `Rule`, no `CrawlSpider`** — deny patterns are re-implemented by hand in
  `sitemap_filter()` precisely because `SitemapSpider` has none. There is no
  fallback to rule-based link discovery.

Real sitemaps are routinely incomplete (a CMS's sitemap plugin typically covers
its post types and nothing else), so any spider built with this setting
**silently orphans** every content section the sitemap doesn't list — no error,
a healthy-looking crawl, missing sections. `CLAUDE.md` §7.1 actively misled
here: *"the sitemap enumerates URLs; your sections/rules still do extraction"*
reads as "sitemap + link-following compose." They don't. (Example of the
incompleteness in the wild: a site whose sitemap lists 1,410 article URLs but
none of its 647 research/project pages, which are reachable only by links.)

## Change

1. **Loud warning at crawl start** (`cli/crawl.py`): when `USE_SITEMAP` routes
   to the sitemap spider and the spider also has follow rules, print that
   link-following is disabled and only sitemap-listed URLs will be crawled.
   The footgun stays (see Follow-up) but stops being silent.
2. **Docs** (`CLAUDE.md` §7.1 + §5): state that `USE_SITEMAP` *replaces* link
   discovery — sections still match and extract, follow rules are ignored —
   so a spider must not enable it when the sitemap is known-incomplete.

## Impact

- Anyone "fixing" a coverage gap by enabling `USE_SITEMAP` now sees exactly
  what they are trading away, at launch time, instead of silently losing
  sections from a healthy-looking crawl.
- Relevant to the audit's `found → try sitemap` hint: it must not be acted on
  blindly while sitemap mode replaces link-following.

## Follow-up (not in this change)

**Hybrid crawl** — make the sitemap path *seed* the frontier AND keep the
`CrawlSpider`/`Rule` link-following engine, so a section missing from the
sitemap is still reached by following links. That is the real fix (and what
§7.1 used to claim); it is a structural spider change affecting every
`USE_SITEMAP` spider and needs a supervised live crawl to verify, so it ships
separately. The warning above becomes obsolete when it lands.
