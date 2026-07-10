"""Per-spider scoring: the status classifier, the DeltaFetch-cache estimate, and
score_spider() — the audit row builder run() calls once per spider."""

import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from core.quality import _env
from core.quality.corpus import host_in_domains
from core.quality.corpus import scraped_urlset as _scraped_urlset

from .sitemaps import (
    collect_pages,
    compile_deny,
    discover_sitemap,
    eligible_urls,
    fetch_spider_sitemaps,
    spider_cache_dirs,
)
from .spiders_db import crawl_ran, crawl_stats_liveness, crawl_stats_sitemap

STALE_DAYS = 30  # newest crawl older than this -> a ⚠ mark in the `stale` column
THIN_CHARS = 1000  # median content below this -> a `thin?` flag (over-broad rules?)
LIVENESS_FLAG_BELOW = (
    90  # live% under this -> a flag (many dead sitemap URLs); above = silent
)


def norm_url(u):
    """Canonicalize a URL for set-comparison between scraped output and sitemaps:
    drop scheme + leading www, lowercase host, strip trailing slash and fragment,
    keep query. So http/https, www, and trailing-slash variants all match."""
    try:
        p = urlparse(u.strip())
    except Exception:
        return u.strip().lower()
    if not p.netloc:  # placeholders like __noURL__N
        return u.strip().lower()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/") or "/"
    return host + path + (("?" + p.query) if p.query else "")


def _human_k(v):
    """Compact char count: 838 -> '0.8k', 5500 -> '5.5k', 12053 -> '12k'."""
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    return f"{v / 1000:.1f}k"


# --------------------------------------------------------------------- deltafetch
# DeltaFetch stores one Berkeley-DB file per spider. We can't read its keys here
# (no BDB reader available), but file size is a reliable proxy for URL count:
# empirically ~8 URLs/KB above a ~16 KB empty-db baseline.
DELTAFETCH_BASELINE_KB = 16
DELTAFETCH_URLS_PER_KB = 8


def deltafetch_estimate(project, spider):
    """Rough count of URLs in the spider's DeltaFetch cache (0 if absent/empty)."""
    path = os.path.join(_env.SCRAPY_DIR, "deltafetch", project, spider + ".db")
    if not os.path.exists(path):
        return 0
    kb = os.path.getsize(path) / 1024
    usable = max(0, kb - DELTAFETCH_BASELINE_KB)
    return int(usable * DELTAFETCH_URLS_PER_KB)


def deltafetch_lost(est_cached, scraped):
    """DeltaFetch cache holds far more than the output → output lost; a plain
    re-crawl skips everything (needs --reset-deltafetch)."""
    return est_cached > 2 * scraped + 50


# -------------------------------------------------------------------------- status
def classify(eligible, scraped, content, est_cached=0):
    """Base status: one of extraction broken / too few pages / incomplete / ok.
    Precedence matters: 'did a real crawl run' and 'does extraction work' are decided
    BEFORE coverage, so an empty/odd sitemap can never mask broken selectors. main()
    then refines an `ok` base into `manual review` when a concern flag is present,
    and audit_notes.json can promote to `ok` (`✓ reviewed`) or move to `discarded`."""
    cpct = (100.0 * content / scraped) if scraped else 0.0
    cov = (100.0 * scraped / eligible) if eligible else None
    # DeltaFetch cache holds far more than the output → output lost; a plain
    # re-crawl skips everything (needs --reset-deltafetch). Counts as incomplete.
    if deltafetch_lost(est_cached, scraped):
        return "incomplete", cpct, cov
    if scraped == 0:
        # no JSONL output — never-ran OR ran-empty (the flag distinguishes them
        # by whether crawl_stats exist; both land in this group)
        return "too few pages", cpct, cov
    # extraction broken: pages reached but came back empty → selectors wrong.
    # Large sample: <70% have content. Small sample (>=3 pages): flag only on
    # near-total failure (<30%), so a 1-2 page test or a couple of thin pages
    # isn't mislabeled — but a small all-empty crawl no longer hides here.
    if (scraped > 20 and cpct < 70) or (scraped >= 3 and cpct < 30):
        return "extraction broken", cpct, cov
    if cov is not None and cov < 90:
        return "incomplete", cpct, cov  # verified shortfall
    if cov is None and scraped < 50:
        return "too few pages", cpct, cov  # too little to verify completeness
    return "ok", cpct, cov


@dataclass
class ScoreContext:
    """Everything score_spider() needs from run() beyond the spider itself: the
    project, the CLI opts, the sitemap cache dir + fetch-budget state, the review
    configs (skip/notes), and run()'s cache-policy closures."""

    project: str
    opts: object  # argparse.Namespace-like (no_browser_retry, ...)
    cache_dir: str
    state: dict  # {"global", "global_cap", "per_cap"} fetch budget
    skip: dict  # audit_sitemap_skip.json entries
    notes: dict  # audit_notes.json entries
    has_cache: object  # closure: prior run resolved this spider's sitemap?
    mark_no_sitemap: object
    should_fetch: object


def score_spider(name, sp, c, ctx):
    """Build ONE audit row for spider `name` (metadata `sp`, crawl-scan entry `c`):
    resolve the sitemap denominator (crawl-recorded, cached, fetched, or discovered),
    compute coverage/liveness/flags, classify, and apply the review note. Returns the
    row dict run() appends."""
    project, args = ctx.project, ctx.opts
    cache_dir, state = ctx.cache_dir, ctx.state
    skip, notes = ctx.skip, ctx.notes
    should_fetch, mark_no_sitemap = ctx.should_fetch, ctx.mark_no_sitemap
    unique_total, content = c.get("unique", 0), c.get("content", 0)
    pdf = c.get("pdf", 0)
    pdf_hosts = c.get("pdf_hosts", {}) or {}
    # HTML articles are the extraction/coverage universe; PDF harvest rows are
    # counted separately (the productive-row rule as set arithmetic — a PDF row
    # can neither fake nor mask extraction health).
    urls = unique_total - pdf
    recs, nfiles = c.get("rows", 0), c.get("files", 0)
    content_med = c.get("content_med", 0)
    uc = c.get("uc", unique_total)
    true_dupes = recs - uc  # identical re-scrapes (dupe math stays TOTAL)
    versions = uc - unique_total  # same URL, changed content (incl. same pdf,
    #                                        different found_on — documented, kept)
    dup_pct = round(100 * true_dupes / recs) if recs else 0
    own = sp.get("domains") or ([sp["host"]] if sp.get("host") else [])
    pdf_own = sum(n for h, n in pdf_hosts.items() if host_in_domains(h, own))
    pdf_ext = pdf - pdf_own
    eligible, total = "-", "-"
    label = "no"
    reason = (skip.get(name) or {}).get("reason")  # normalised entry: {reason, updated}
    pages = None  # collected at most ONCE per spider (pure disk read)
    # Prefer the sitemap counts the CRAWL recorded (sitemap_spider.py counts them
    # while parsing; closed() writes them). When present we skip the re-fetch
    # entirely — same point-in-time as the crawl, so no sitemap-drift mismatch.
    sm = crawl_stats_sitemap(project, name)
    if sp["use_sitemap"]:
        label = "yes"
        if sm:
            pass  # counts came from the crawl — never fetch
        elif should_fetch(name):
            # configured start_urls are often a single leaf (e.g. post-sitemap.xml);
            # also pull the site's root index so we catch sibling *content*
            # sub-sitemaps (page-sitemap etc.). Taxonomy ones are skipped during
            # recursion. The leaf start_urls are still fetched (deduped).
            entries = list(sp["start_urls"])
            for r in discover_sitemap(
                sp["host"],
                project,
                name,
                cache_dir,
                state,
                sp["browser"],
                not args.no_browser_retry,
            ):
                if r not in entries:
                    entries.append(r)
            fetch_spider_sitemaps(
                name,
                {**sp, "start_urls": entries},
                project,
                cache_dir,
                state,
                not args.no_browser_retry,
            )
    elif reason:
        label = "ignored"  # on the skip list — show 'ignored' + reason, don't probe
    else:
        # auto-discover a sitemap (robots.txt → /sitemap.xml) for coverage
        entry = []
        if should_fetch(name):
            entry = discover_sitemap(
                sp["host"],
                project,
                name,
                cache_dir,
                state,
                sp["browser"],
                not args.no_browser_retry,
            )
            if entry:
                fetch_spider_sitemaps(
                    name,
                    {**sp, "start_urls": entry},
                    project,
                    cache_dir,
                    state,
                    not args.no_browser_retry,
                )
                try:  # a sitemap exists after all — drop a stale 'none' marker
                    os.remove(os.path.join(cache_dir, name + "_nositemap"))
                except OSError:
                    pass
            else:
                mark_no_sitemap(name)  # confirmed none → don't re-probe next run
        else:
            pages = collect_pages(name, cache_dir)
            if pages:
                entry = ["(cached)"]  # found on a prior full run
        # A sitemap genuinely fetched here (sub-sitemap files on disk) counts as
        # `found` even if it parsed to 0 usable URLs (nested index / empty urlset) —
        # so that empty state surfaces for review instead of being hidden as `no`.
        if entry or spider_cache_dirs(name, cache_dir):
            label = "found"
    eligible_cell = "-"
    matched = ""
    if sm and label == "yes":
        # Crawl-recorded denominator: counts only (no URL list), and no drift to
        # check — eligible came from the same crawl as `scraped` — so `matched`
        # (the set-intersection integrity flag) is neither available nor needed.
        total, eligible, matched = sm["total"], sm["eligible"], ""
    elif label in ("yes", "found"):
        if pages is None:
            pages = collect_pages(name, cache_dir)
        total = len(pages)
        el_urls = eligible_urls(sp, pages)  # sitemap URLs matching rules
        # A callback/manual-sitemap spider (e.g. unep_org) matches the sitemap
        # *pages* in its allow-rules, not the article locs, so rule-matching yields
        # 0 even though the spider does crawl from the sitemap. For a DISCOVERED
        # ('found') sitemap that has content URLs, fall back to the whole sitemap
        # (minus the safe denies) as the coverage denominator — so the column shows
        # a real % and flags the shortfall, instead of going blank. (A `yes`
        # sitemap with 0 rule matches is a genuine misconfig → stays 0/'sitemap-empty'.)
        if not el_urls and label == "found" and total > 0:
            deny_c = compile_deny(sp)
            el_urls = [u for u in pages if not any(c.search(u) for c in deny_c)]
        eligible = len(el_urls)
        scraped_raw = _scraped_urlset(c)
        # matched = scraped pages that are ACTUALLY the eligible sitemap pages
        # (set intersection, normalized) — coverage uses this, not raw counts,
        # so 100 scraped / 100 eligible can't fake 100% if the sets differ.
        elig_norm = {norm_url(u) for u in el_urls}
        matched = len({norm_url(u) for u in scraped_raw} & elig_norm)

    # A discovered sitemap that parsed to 0 usable URLs (malformed XML, an index with
    # no content, or all-taxonomy) is NOT hidden as `no` — that would erase the fact a
    # sitemap exists. We keep it `found` and flag it `found sitemap empty (0 usable
    # URLs)` below, so it surfaces for `manual review` and a human can record the
    # reason in audit_sitemap_skip.json. (USE_SITEMAP spiders keep `yes` regardless —
    # 0 eligible there is a real misconfig.)
    found_no_content = label == "found" and isinstance(total, int) and total == 0

    # Liveness: ONLY from a real crawl's own HTTP-status stats (no sampling).
    rate = None
    if label in ("yes", "found"):
        cstats = crawl_stats_liveness(project, name)
        if cstats:
            rate = cstats["rate"]

    est_cached = deltafetch_estimate(project, name)
    # eligible denominator (tidy = just the number). When the crawl recorded
    # liveness it's reduced to the live fraction; the live% only shows (as a flag)
    # when it's LOW — a high live% isn't worth the reader's attention.
    denom = eligible if isinstance(eligible, int) else 0
    if isinstance(eligible, int):
        if rate is not None:
            denom = round(eligible * rate)
        eligible_cell = str(denom)
    status, cpct, cov = classify(denom, urls, content, est_cached)

    # drift = scraped URLs barely intersect the sitemap → denominator unreliable
    drift = (
        isinstance(eligible, int)
        and eligible > 0
        and urls > 20
        and isinstance(matched, int)
        and (
            urls > eligible * 1.15
            or (matched < 0.3 * eligible and urls >= 0.5 * eligible)
        )
    )
    # ---- flags: the ONE attention column. Built FIRST; the set of *concern*
    #      flags then decides whether an otherwise-`ok` spider is truly clean
    #      (`ok`, empty flags) or needs a human look (`manual review`).
    #      A clean, verified, recent spider leaves this EMPTY. ----
    flags = []
    concern = False  # any flag that should trigger manual review (see below)
    if reason:  # on the skip list (column = 'ignored')
        flags.append(reason)
    if label == "found":  # discoverable sitemap, USE_SITEMAP off
        if found_no_content:  # discovered but 0 usable URLs parsed
            flags.append("found sitemap empty (0 usable URLs)")
            concern = True  # surface for review → record a skip reason
        else:
            flags.append("found → try sitemap")
    if status == "too few pages":  # never-ran covers 'only tested'
        if urls == 0 and pdf > 0:
            # no HTML articles, but the crawl demonstrably ran and harvested
            # PDF links — a document-repository site, not a dead spider
            flags.append(f"pdf-only ({pdf})")
        elif urls == 0:
            # crawl_stats present → the crawl DID run, it just produced no
            # output (blocked, 0 rule-eligible URLs, or dropped items) — so
            # 'never-ran' would be a lie. liveness already trusts this file.
            flags.append("ran-empty" if crawl_ran(project, name) else "never-ran")
        else:
            flags.append("small/partial")
    if deltafetch_lost(est_cached, unique_total):  # output lost → --reset-deltafetch
        # compared against TOTAL uniques: in extract mode fetched PDFs sit in
        # the DeltaFetch cache, and HTML-only counts would false-flag
        flags.append("deltafetch-stale")
    if rate is not None and rate * 100 < LIVENESS_FLAG_BELOW:
        flags.append(f"liveness {round(rate * 100)}%")  # many dead sitemap URLs
        concern = True  # review trigger
    if content_med and content_med < THIN_CHARS and status != "extraction broken":
        flags.append(f"thin? {_human_k(content_med)}")  # over-broad rules / junk?
        concern = True  # review trigger
    # coverage unverifiable → say WHY (only meaningful for an `ok`-base spider)
    if status == "ok" and not (cov is not None and not drift):
        if drift:
            flags.append(f"sitemap-drift ({matched}/{eligible})")
        elif label == "yes":
            flags.append("sitemap-empty")  # configured sitemap matched 0
        elif label == "found":
            pass  # already flagged above (found → try sitemap / empty)
        elif not reason:
            flags.append("no-sitemap")
        concern = True  # review trigger (coverage)
    stale = ""  # OWN column (not a flag): data age
    newest = c.get("newest")
    if newest and nfiles:
        age_d = int((time.time() - newest) / 86400)
        if age_d > STALE_DAYS:
            stale = f"⚠ {age_d}d"  # newest crawl older than STALE_DAYS
    if state["global"] >= state["global_cap"] and label in ("yes", "found"):
        flags.append("sitemap-cap-hit")  # coverage data truncated
        concern = True  # review trigger (coverage)

    # ---- status refinement: an `ok`-base spider with any concern flag needs a
    #      human eyeball → `manual review`; otherwise it stays clean `ok`.
    if status == "ok" and concern:
        status = "manual review"

    # ---- manual review / discard (audit_notes.json) ----
    # A note ONLY affects the report when it carries an explicit `status` key
    # ("ok" | "discard"); legacy `discard: true` == status "discard". A note with
    # NO status is inert — pure documentation, it changes neither status nor flags.
    #   status "discard" → `discarded`, wins over everything (a dropped source).
    #   status "ok"      → promotes to `ok` with `✓ reviewed: <flag>`, which REPLACES
    #                      the auto-flags that prompted review (they're addressed in
    #                      the `note`). This applies whether the computed status was a
    #                      concern (`manual review`, `too few pages`) OR already
    #                      clean `ok` — an already-ok spider stays ok and just gains
    #                      the reviewed tag. EXCEPTIONS (both surface as
    #                      `⚠ reviewed-stale` instead): `extraction broken` — a note must
    #                      never claim empty content is fine — and an EMPTY CORPUS
    #                      (zero rows: never-ran/ran-empty) — a note vouches for data it
    #                      once reviewed, and there is none here (typical after a
    #                      migration carries notes into a project whose crawls haven't
    #                      run or came back empty). `incomplete` (a coverage shortfall)
    #                      CAN be promoted — the reviewer vouches it's a false positive
    #                      (e.g. a misleading denominator).
    # Only `deltafetch-stale` survives review (orthogonal — lost output, not the
    # reviewed concern); data-age staleness isn't a flag at all (own `stale` column).
    review = notes.get(name)
    if isinstance(review, dict):
        want = review.get("status") or ("discard" if review.get("discard") else None)
        tag = review.get("flag", "")
        if want == "discard":
            status = "discarded"
            flags = [f"🗑 discard: {tag}" if tag else "🗑 discard"] + [
                f for f in flags if f == "deltafetch-stale"
            ]
        elif want == "ok":
            if status == "extraction broken" or recs == 0:
                flags.insert(
                    0, f"⚠ reviewed-stale: {tag}" if tag else "⚠ reviewed-stale"
                )
            else:
                status = "ok"
                flags = [f"✓ reviewed: {tag}" if tag else "✓ reviewed"] + [
                    f for f in flags if f == "deltafetch-stale"
                ]
        # want is None (or an invalid status) → inert note: status/flags untouched

    return {
        "spider": name,
        "sitemap": label,
        "sitemap_total": total,
        "eligible": eligible_cell,
        "scraped": urls,  # unique HTML article URLs
        "unique": unique_total,  # ALL unique URLs incl. pdf rows (dupe math)
        "pdf": pdf,
        "pdf_own": pdf_own,
        "pdf_ext": pdf_ext,
        "rows": recs,
        "true_dupes": true_dupes,
        "versions": versions,
        "dup_pct": dup_pct,
        "files": nfiles,
        "content": content,
        "content_pct": round(cpct),
        "content_med": content_med,
        "coverage_pct": "" if cov is None else round(cov),
        "stale": stale,
        "flags": " · ".join(flags),
        "status": status,
    }
