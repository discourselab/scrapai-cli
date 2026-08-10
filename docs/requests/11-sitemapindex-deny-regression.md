# Possible regression: deny patterns applied to `<sitemapindex>` entries

**Status:** flag for verification — found 2026-07-09 while grafting the sitemap audit
counters onto the rewritten `sitemap_filter`. Not fixed here (out of scope for the
quality-tool handover); needs an owner.

## The problem

Upstream's `sitemap_filter` now runs **every** sitemap entry through the deny
patterns — including entries of a `<sitemapindex>` (i.e. URLs of *child sitemaps*,
not content pages).

The original implementation of deny-enforcement (in the frozen instance,
2026-06-26) deliberately **skipped `<sitemapindex>` entries** when applying
denies, because of a real failure mode: Drupal's `simple_sitemap` module paginates
its index as `sitemap.xml?page=1`, `?page=2`, … — and a project-conventional deny
like `\?page=` (used to drop paginated listing URLs) then swallows the child
sitemaps themselves. The spider silently discovers nothing and the crawl runs
empty. This was observed in production ("ran-empty" spiders) and fixed by letting
index recursion bypass the deny filters — denies only ever apply to content locs.

## What to verify

On current `main`: a sitemap spider with `deny: ["\\?page="]` pointed at a Drupal
simple_sitemap index (`sitemap.xml` → `<sitemapindex>` of `sitemap.xml?page=N`).
If the children get denied, the regression is real.

## Suggested fix

In `sitemap_filter`, detect `<sitemapindex>` responses (the quality-tool graft
already computes `is_index` there for its counters) and skip deny-filtering for
their entries; keep denies for `<urlset>` locs.

## Cross-reference

- The frozen instance's `spiders/sitemap_spider.py` working-tree diff carries the
  original guard (reference implementation).
- The audit surfaces the symptom as `too few pages` / `ran-empty` with a
  discovered-but-empty sitemap.
