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
    discovered_sitemaps,
    eligible_urls,
    fetch_spider_sitemaps,
    index_manifest,
    parse_sitemap,
    read_page,
    spider_cache_dirs,
    spider_cached_urls,
)
from .spiders_db import (
    crawl_ran,
    crawl_stats_outcomes,
    crawl_stats_sitemap,
    robots_sitemaps_on_disk,
)

STALE_DAYS = 30  # newest crawl older than this -> a ⚠ mark in the `stale` column
THIN_CHARS = 1000  # median content below this -> a `thin?` flag (over-broad rules?)
OVER_EXPECTED_PCT = 115  # coverage above this -> `scraped more than expected`
# ...but only once MORE than this many pages were scraped (drift's floor): 3
# scraped against a 2-URL sitemap is 150% and says nothing about the yardstick,
# while 60 against a 10-URL one does
OVER_EXPECTED_MIN = 20
# blocked / failed above this share of final outcomes (and at least
# OUTCOME_FLAG_MIN of them) -> a flag; a handful on a tiny crawl is noise
OUTCOME_FLAG_PCT = 5
OUTCOME_FLAG_MIN = 5
NO_OUTCOME = "–"  # dead/blocked/failed not recorded (or status-blind spider)
PER_ATTEMPT_MARK = "†"  # md suffix: a per-attempt figure (older crawl format)
LAST_LEG = " last leg"  # suffix: a resumed crawl whose stats cover one leg
# what the dead/blocked/failed figures are, for the dashboard's detail and
# tooltips: final outcomes / per-attempt counts (older crawl-stats format) /
# the last leg of a resumed crawl whose legs weren't summed
OUTCOME_BASIS = {
    "final": "",
    "attempts": "per attempt, older crawl format — never flagged",
    "last leg": "last crawl leg only (resumed, legs not summed) — flagged on "
    "the leg's own share",
}


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


def outcome_cell(n, base):
    """A dead/blocked/failed figure as `n (p%)` — one decimal under 10% so a
    small share doesn't round to 0 — or plain `0` when there were none."""
    if not n:
        return "0"
    if not base:
        return str(n)
    pct = 100.0 * n / base
    if pct < 0.1:
        return f"{n} (<0.1%)"
    return f"{n} ({pct:.1f}%)" if pct < 10 else f"{n} ({round(pct)}%)"


def outcome_flagged(n, base):
    share = 100.0 * n / base if base else 0.0
    return n >= OUTCOME_FLAG_MIN and share > OUTCOME_FLAG_PCT


def _human_k(v):
    """Compact char count: 838 -> '0.8k', 5500 -> '5.5k', 12053 -> '12k'."""
    if v >= 10000:
        return f"{v / 1000:.0f}k"
    return f"{v / 1000:.1f}k"


# ------------------------------------------------------- sitemaps given/total
def _is_robots_txt(url):
    path = urlparse(url.strip()).path.rstrip("/").lower()
    return path.endswith("/robots.txt")


def _no_query(n):
    """A norm_url key without its query string: a cache-buster (`?v=2`) on a
    sitemap URL names the same sitemap."""
    return n.split("?", 1)[0]


def sitemap_listing(name, sp, ctx):
    """Which of the site's sitemaps a USE_SITEMAP spider was given, for the
    `given/total` sitemap cell and the per-spider list. Returns
    {given, total, list, note}: `list` = [{url, given, in_index}], given first;
    `total` is "?" while a declared sitemap's children are unknown.

    The site's sitemaps = the union of every declared index's children plus the
    declared leaf sitemaps (robots `Sitemap:` lines, read from disk first; the
    index URLs themselves aren't counted, nor is a declared URL whose content
    isn't a sitemap, such as an RSS feed). A start_url that is robots.txt gives
    them all; one that IS a declared index gives all its children, and so does
    one whose cached copy (the spider's own sitemap fetch) is a sitemap index —
    e.g. /sitemap.xml serving the same index robots declares as
    /sitemap_index.xml. Any other start_url not among them is added, marked
    in_index False ("not listed in root index" — e.g. a nested index's
    grandchild). URLs compare via norm_url; when that finds no match, the query
    string is ignored if exactly one of the site's sitemaps then matches, so a
    cache-busted copy (`?v=2`) is the same sitemap, not an extra one."""
    args = ctx.opts
    mode = (
        "none"
        if getattr(args, "no_fetch", False)
        else ("all" if getattr(args, "fetch_all", False) else "missing")
    )
    retry = not getattr(args, "no_browser_retry", False)
    fetch_args = (ctx.project, ctx.cache_dir, ctx.state, mode)
    fetch_args += (sp["browser"], retry)
    # what this spider's own sitemap fetch cached, by URL — read, never fetched
    on_disk = spider_cached_urls(name, ctx.cache_dir)
    declared = robots_sitemaps_on_disk(ctx.project, sp["host"], name)
    notes = []
    if not declared:
        # nothing declared on disk → discovery (robots.txt, /sitemap.xml),
        # once per host; None = it hasn't run or failed: the total stays unknown.
        # robots.txt already on disk isn't fetched again, and a cached
        # /sitemap.xml copy answers the probe without a fetch.
        robots_known = declared is not None
        seeds = [os.path.join(ctx.cache_dir, name + "_smprobe", "page.html")]
        root = on_disk.get("https://" + (sp["host"] or "") + "/sitemap.xml")
        if root:
            seeds.insert(0, root)
        declared, why = discovered_sitemaps(
            sp["host"], *fetch_args, robots_known=robots_known, seeds=seeds
        )
        if declared is None:
            head = "robots.txt lists none" if robots_known else "robots.txt not on disk"
            notes.append(f"{head}; {why}")
    known = {}  # norm → url, in the site's own order
    children = {}  # declared index (norm) → its children (norm)
    unknown = set()  # declared sitemaps whose children we don't know
    skipped = set()  # declared URLs whose content isn't a sitemap
    for u in declared or []:
        m, why = index_manifest(u, *fetch_args, on_disk=on_disk)
        if m is None:
            unknown.add(norm_url(u))
            notes.append(f"{u}: {why}")
        elif m.get("not_sitemap"):
            # robots advertises it on a Sitemap: line, but its content is
            # something else (an RSS feed): not one of the site's sitemaps
            skipped.add(u)
            notes.append(f"{u}: not a sitemap, skipped")
        elif m.get("is_index"):
            kids = m.get("children") or []
            children[norm_url(u)] = [norm_url(k) for k in kids]
            for k in kids:
                known.setdefault(norm_url(k), k)
        else:
            known.setdefault(norm_url(u), u)
    loose = {}  # norm without query → the site's sitemaps (norm) it could be
    for n in list(known) + list(children):
        loose.setdefault(_no_query(n), set()).add(n)

    def match(u):
        n = norm_url(u)
        if n in known or n in children:
            return n
        cands = loose.get(_no_query(n), ())
        return next(iter(cands)) if len(cands) == 1 else n

    given, extra = set(), {}
    for u in sp["start_urls"]:
        n = match(u)
        if _is_robots_txt(u):
            given |= set(known)
            continue
        if n in children:
            given |= set(children[n])
            continue
        if n in known:
            given.add(n)
            continue
        is_index, kids = parse_sitemap(read_page(on_disk.get(u)))
        for k in kids if is_index else [u]:
            kn = match(k)
            if kn in known:
                given.add(kn)
            else:
                extra.setdefault(kn, k)
    # a cache-busted copy of a given sitemap the site doesn't list is still
    # that one sitemap; distinct queries (`?page=2`) stay distinct sitemaps
    plain = {n for n in extra if "?" not in n}
    extra = {
        n: u for n, u in extra.items() if "?" not in n or _no_query(n) not in plain
    }
    complete = declared is not None and not unknown
    listed = [
        {"url": u, "given": True, "in_index": True}
        for n, u in known.items()
        if n in given
    ]
    # while a declared sitemap is unread, a given one can't be called "not
    # listed" — it may be among that sitemap's children; and a site that
    # declares none has no root index to be missing from
    judged = complete and bool(set(declared) - skipped)
    for u in extra.values():
        listed.append({"url": u, "given": True, "in_index": not judged})
    listed += [
        {"url": u, "given": False, "in_index": True}
        for n, u in known.items()
        if n not in given
    ]
    if declared == []:
        notes.append("the site declares no sitemap (robots.txt, /sitemap.xml)")
    elif declared and not set(declared) - skipped:
        notes.append("robots.txt declares no sitemap, only non-sitemap URLs")
    return {
        "given": sum(1 for e in listed if e["given"]),
        "total": len(listed) if complete else "?",
        "list": listed,
        "note": "; ".join(notes),
    }


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
    compute coverage/flags, classify, and apply the review note. Returns the
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
    # The same PDF linked from N pages yields N rows whose fingerprints differ
    # only by found_on provenance. dedupe KEEPS them (fingerprint includes
    # found_on), so the counting must not change — the split below is purely
    # presentational: pdf_multi is shown as its own figure and `versions`
    # shows only HTML re-fetch churn, which is what its "genuine history"
    # description always meant (docs/requests/22, Fix B).
    pdf_uc = c.get("pdf_uc", pdf)
    pdf_multi = max(0, pdf_uc - pdf)
    versions = uc - unique_total - pdf_multi  # same URL, changed content (HTML)
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
    listing = sitemap_listing(name, sp, ctx) if label == "yes" else None
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
        # A callback/manual-sitemap spider (e.g. site37_org) matches the sitemap
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

    est_cached = deltafetch_estimate(project, name)
    # eligible denominator (tidy = just the number). It is the FULL rule-eligible
    # sitemap count: a sitemap URL that answered 404 or 403 during the crawl is
    # still a page the spider should have got, so it stays in the denominator
    # and shows up as a shortfall — instead of being scaled away by a liveness
    # rate, which also counted a 403 block as a "dead" URL.
    denom = eligible if isinstance(eligible, int) else 0
    if isinstance(eligible, int):
        eligible_cell = str(denom)
    status, cpct, cov = classify(denom, urls, content, est_cached)

    # Far more scraped than the sitemap says exists → the yardstick is suspect
    # (a partial sitemap, or rules matching pages it never lists). Decided on
    # the coverage figure itself, so it fires on the crawl-recorded path too —
    # that path has no URL set, so drift below could never catch it there.
    over_expected = (
        cov is not None and cov > OVER_EXPECTED_PCT and urls > OVER_EXPECTED_MIN
    )
    # drift = scraped URLs barely intersect the sitemap → denominator unreliable.
    # Only the set-intersection test: the count test (scraped > 115% of
    # eligible) is over_expected's job, so one condition never flags twice.
    drift = (
        isinstance(eligible, int)
        and eligible > 0
        and urls > 20
        and isinstance(matched, int)
        and matched < 0.3 * eligible
        and urls >= 0.5 * eligible
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
            # 'never-ran' would be a lie.
            flags.append("ran-empty" if crawl_ran(project, name) else "never-ran")
        else:
            flags.append("small/partial")
    if deltafetch_lost(est_cached, unique_total):  # output lost → --reset-deltafetch
        # compared against TOTAL uniques: in extract mode fetched PDFs sit in
        # the DeltaFetch cache, and HTML-only counts would false-flag
        flags.append("deltafetch-stale")
    # dead / blocked / failed: final request outcomes from the crawl's stats.
    # Only a file with the final-outcome keys may flag — an older file's
    # attempt-level counts include retried attempts, so they're shown for
    # information only. A status-blind spider (Cloudflare / browser: every page
    # comes back as 200) can't see dead or blocked at all, so those read "–";
    # its failed figure (no response at all) is still real.
    # A resumed crawl whose legs the writer summed (`summed`) is a whole crawl
    # like any other. Without `summed` the file covers only the last leg, so
    # its figures carry a "last leg" suffix — in the cells and in any flag —
    # but still flag: a leg that is 40% blocked is real evidence of a wall.
    outcomes = crawl_stats_outcomes(project, name)
    dead_cell = blocked_cell = failed_cell = NO_OUTCOME
    basis = ""
    if outcomes:
        base = outcomes["base"]
        blind = sp.get("status_blind", False)
        one_leg = outcomes.get("resumed", False) and not outcomes.get("summed")
        basis = (
            "last leg" if one_leg else ("final" if outcomes["final"] else "attempts")
        )
        leg = LAST_LEG if one_leg else ""
        if not blind:
            dead_cell = outcome_cell(outcomes["dead"], base) + leg
            blocked_cell = outcome_cell(outcomes["blocked"], base) + leg
        if outcomes["failed"] is not None:
            failed_cell = outcome_cell(outcomes["failed"], base) + leg
        if outcomes["final"]:
            # dead never flags: a URL the site removed isn't the spider's fault
            if not blind and outcome_flagged(outcomes["blocked"], base):
                flags.append(f"blocked {blocked_cell}")
                concern = True  # review trigger (the site walled us off)
            if outcome_flagged(outcomes["failed"], base):
                flags.append(f"failed {failed_cell}")
                concern = True  # review trigger (timeouts / dead proxy)
    # Sitemaps the crawl fetched but Scrapy refused to parse (an HTML view or a
    # block page served as 200): every URL in them was dropped and never
    # counted, so the crawl-recorded denominator is short. A file without the
    # key predates it: unknown, no flag.
    rejected = (outcomes or {}).get("sitemap_rejected") or []
    if rejected:
        flags.append(f"sitemap rejected ({len(rejected)})")
        concern = True  # review trigger (coverage denominator short)
    if content_med and content_med < THIN_CHARS and status != "extraction broken":
        flags.append(f"thin? {_human_k(content_med)}")  # over-broad rules / junk?
        concern = True  # review trigger
    if over_expected:
        flags.append(f"scraped more than expected ({round(cov)}%)")
        concern = True  # review trigger (coverage)
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
    # a crawl-recorded denominator depends on no fetch, so the cap can't
    # truncate it (the sitemap listing's own fetches have a separate budget
    # and never count toward it)
    crawl_counted = bool(sm) and label == "yes"
    if (
        state["global"] >= state["global_cap"]
        and label in ("yes", "found")
        and not crawl_counted
    ):
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
        # USE_SITEMAP only: sitemaps given of the site's total ("" elsewhere)
        "sitemaps_given": listing["given"] if listing else "",
        "sitemaps_total": listing["total"] if listing else "",
        "sitemap_list": listing["list"] if listing else [],
        "sitemaps_note": listing["note"] if listing else "",
        # sitemap URLs the crawl's Scrapy rejected (crawl-stats sitemap_rejected)
        "sitemap_rejected": rejected,
        "eligible": eligible_cell,
        "scraped": urls,  # unique HTML article URLs
        "unique": unique_total,  # ALL unique URLs incl. pdf rows (dupe math)
        "pdf": pdf,
        "pdf_own": pdf_own,
        "pdf_ext": pdf_ext,
        "rows": recs,
        "true_dupes": true_dupes,
        "versions": versions,
        "pdf_multi": pdf_multi,  # same PDF, one row per linking page (kept)
        "dup_pct": dup_pct,
        "files": nfiles,
        "content": content,
        "content_pct": round(cpct),
        "content_med": content_med,
        "coverage_pct": "" if cov is None else round(cov),
        # display strings ("n (p%)" / "0" / "–"): flags above already used the
        # raw counts, so nothing downstream needs to parse these back
        "dead": dead_cell,
        "blocked": blocked_cell,
        "failed": failed_cell,
        # final / attempts / last leg ("" = no crawl stats): what they count
        "outcomes_basis": basis,
        "stale": stale,
        "flags": " · ".join(flags),
        "status": status,
    }
