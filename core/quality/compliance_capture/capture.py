"""Capture stage: capture() (decomposed into per-stage helpers), run(), and the
CLI main(). The fetch/fetch_rich closures stay inside capture() — they carry the
project/tmp/browser/proxy/ts context — and are passed to the stage helpers
explicitly."""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
from urllib.parse import urlparse

from core.quality._env import DATA_DIR

from .assess import crawl_robots_cell
from .fetch import (
    header_signals,
    header_tdm_reserved,
    inspect,
    looks_html,
    visible_text,
)
from .page import (
    detect_license,
    jsonld,
    legal_links,
    meta_copyright,
    robots_meta,
    tdm_meta,
)
from .report import write_report
from .robots import (
    _is_robots,
    ai_bot_signals,
    ai_bots_blocked,
    ai_scrape_block_from,
    parse_robots,
    robots_blocks_pdfs,
    robots_blocks_targets,
    robots_comment_signals,
)
from .signals import (
    SCRAPE_WORDS,
    ai_training_prohibition,
    bespoke_permission,
    classify_llms,
    copyright_statement,
    refine_license,
    scrape_prohibition,
)
from .store import (
    DATE_RE,
    clear_capture_failed,
    existing_snapshots,
    mark_capture_failed,
    norm_domain,
    org_compliance_dir,
    project_exists,
    project_targets,
    spider_target_urls,
    spider_user_agent,
    unwrap_wayback,
    wayback_ts,
)

# Self-documenting note embedded in every compliance.json. This tool is an OVERVIEW of the
# live signals; the verdict/reviewed/notes fields are OPTIONAL annotation slots (review is not
# a core function — leave them or fill them).
INSTRUCTIONS = {
    "_what": "Evidence captured automatically by compliance_capture.py. robots, ai, license, "
    "legal_pages and copyright are FACTS read from the live site — an overview, not a "
    "legal determination.",
    "_two_questions": "Two INDEPENDENT axes. CRAWL (may we fetch?) = robots for our paths + AI "
    "opt-out + anti-scraping ToS. REUSE (may we republish?) = licence. A site "
    "can be fine to crawl but not to republish, or vice versa.",
    "_copyright_caveat": "A blank 'copyright' means no notice was found — it does NOT mean the "
    "content is free. Content is copyrighted by default. The 'license' "
    "field is what grants reuse rights.",
    "_optional_review": "verdict / reviewed / reviewed_by / notes are optional — the tool never "
    "sets them; fill them only if you want to record a manual decision.",
}


def _capture_robots(fetch, base, project, domain, ua, browser):
    """Stage 1 — robots.txt: fetch (with browser retry), store the raw file, parse,
    and derive the spider-path overlap, PDF block, AI-bot and comment signals."""
    # 1. robots.txt → store raw, parse groups, detect AI-bot opt-out. The lightweight fetch is
    #    blocked at the TLS/Cloudflare layer on some big sites (canada.ca, who.int…), so when it
    #    returns NOTHING we retry with the browser (which bypasses the block; text/plain may come
    #    back HTML-wrapped, so pull the text back out). fetch_status:
    #      ok     = got a real robots.txt
    #      absent = a response came back but it isn't robots (genuine 404/soft-404) → open
    #      failed = nothing came back even via browser → couldn't fetch (must NOT read as open)
    robots_url = f"https://{domain}/robots.txt"
    robots_txt = fetch(robots_url)
    browser_resp = None
    if robots_txt is None and not browser:
        browser_resp = fetch(robots_url, force_browser=True)
        cand = (
            visible_text(browser_resp)
            if (browser_resp and looks_html(browser_resp))
            else browser_resp
        )
        if _is_robots(cand):
            robots_txt = cand

    if _is_robots(robots_txt):
        fetch_status = "ok"
    elif robots_txt is not None or browser_resp is not None:
        fetch_status = (
            "absent"  # some response, just not robots → treat as no robots.txt
        )
    else:
        fetch_status = "failed"  # nothing at all, even via browser → couldn't fetch

    robots = {
        "fetched": fetch_status == "ok",
        "fetch_status": fetch_status,
        "disallow": [],
        "allow": [],
        "crawl_delay": None,
        "sitemaps": [],
    }
    blocked = []
    ai_bots = {"full": [], "partial": [], "allowed": [], "heuristic": [], "channel": []}
    robots_comments = []
    if fetch_status == "ok":
        with open(os.path.join(base, "robots.txt"), "w") as fh:
            fh.write(robots_txt)
        parsed = parse_robots(robots_txt)
        star = parsed["groups"].get(
            "*", {"disallow": [], "allow": [], "crawl_delay": None}
        )
        robots = {
            "fetched": True,
            "fetch_status": "ok",
            **star,
            "sitemaps": parsed["sitemaps"],
        }
        blocked = ai_bots_blocked(parsed["groups"])  # whole-site only (back-compat)
        ai_bots = ai_bot_signals(parsed["groups"])  # full breakdown (partial/allowed/…)
        robots_comments = robots_comment_signals(robots_txt)

    # does robots block the paths OUR spider actually crawls (its start_urls / allow-rules),
    # rather than just admin noise? — the only robots question that matters operationally.
    targets = spider_target_urls(project, domain)
    checked, tblocked = robots_blocks_targets(
        robots_txt if robots["fetched"] else None, targets, ua
    )
    robots["target_urls_checked"] = checked
    robots["target_urls_blocked"] = len(tblocked) if checked is not None else None
    robots["target_blocked_sample"] = tblocked[:8]

    # does robots forbid the article-linked PDFs we capture? (its own signal — important)
    pdf_blocked, pdf_evidence = robots_blocks_pdfs(
        robots_txt if robots["fetched"] else None, domain, ua
    )
    robots["pdf_blocked"] = pdf_blocked
    robots["pdf_block_evidence"] = pdf_evidence[:8]
    robots["ai_bots"] = (
        ai_bots  # full AI-crawler breakdown (partial/allowed/heuristic/channel)
    )
    robots["comments"] = (
        robots_comments  # policy/contact lines parse_robots would discard
    )
    return robots_txt, robots, blocked, ai_bots


def _capture_wellknown(fetch, base, domain, robots_txt):
    """Stage 2 — the .well-known opt-out files (tdmrep.json / ai.txt / llms.txt),
    with the catch-all-server guards."""
    # 2. .well-known / ai.txt opt-out files. Guard against catch-all servers that
    #    return robots.txt (or an HTML soft-404) for unknown paths:
    #    - tdmrep.json must be valid JSON that actually mentions TDM;
    #    - ai.txt must be non-empty AND differ from robots.txt (else it's a duplicate).
    wk = {
        "tdmrep": {"present": False},
        "ai_txt": {"present": False},
        "llms_txt": {"present": False},
    }
    rb = (robots_txt or "").strip()
    t = fetch(f"https://{domain}/.well-known/tdmrep.json")
    if t and t.strip().startswith(("{", "[")) and "tdm" in t.lower():
        try:
            json.loads(t)
            with open(os.path.join(base, "tdmrep.json"), "w") as fh:
                fh.write(t)
            wk["tdmrep"] = {
                "present": True,
                "path": "/.well-known/tdmrep.json",
                "file": "tdmrep.json",
            }
        except Exception:
            pass
    for path in ("/ai.txt", "/.well-known/ai.txt"):
        a = fetch(f"https://{domain}{path}")
        if a and not looks_html(a) and a.strip() and a.strip() != rb:
            with open(os.path.join(base, "ai.txt"), "w") as fh:
                fh.write(a)
            wk["ai_txt"] = {"present": True, "path": path, "file": "ai.txt"}
            break
    # llms.txt — the INDEPENDENT witness for the file the spider also captures. Usually an
    # AI-FRIENDLY curation file (a positive signal), but it CAN carry prohibitions, so we scan
    # it. Same soft-404 guard as ai.txt (not HTML, non-empty, not a robots duplicate).
    for path in ("/llms.txt", "/.well-known/llms.txt"):
        body = fetch(f"https://{domain}{path}")
        if body and not looks_html(body) and body.strip() and body.strip() != rb:
            with open(os.path.join(base, "llms.txt"), "w") as fh:
                fh.write(body)
            verdict, quote = classify_llms(body)
            wk["llms_txt"] = {
                "present": True,
                "path": path,
                "file": "llms.txt",
                "verdict": verdict,
                "quote": quote,
            }
            break
    return wk


def _capture_homepage(fetch_rich, domain):
    """Stage 3 — homepage: readable text, JSON-LD, and the legal links to fetch."""
    # 3. homepage → copyright, meta/JSON-LD, legal links. For Wayback the raw (id_)
    #    snapshot keeps the ORIGINAL links, so legal_links still matches the real domain.
    home = fetch_rich(f"https://{domain}/")
    home_text = visible_text(home)
    jl = jsonld(home)
    legals = legal_links(home, domain)[:6]
    return home, home_text, jl, legals


def _capture_legal_pages(fetch_rich, base, legals, home, home_text):
    """Stage 4 — fetch + store each legal page and scan it for the directed clauses;
    returns (legal_pages, lic_pages) with the homepage as the first licence source."""
    # 4. legal pages → store clean text, scan for scraping clauses. License detection
    #    runs across home + every legal page (see detect_license) so an explicit grant
    #    is not masked by a homepage footer "all rights reserved".
    legal_pages = []
    lic_pages = [("home", home, home_text)]
    for url in legals:
        raw = fetch_rich(url)
        text = visible_text(raw)
        name = (
            "legal_"
            + (urlparse(url).path.strip("/").replace("/", "_") or "root")
            + ".txt"
        )
        if text:
            with open(os.path.join(base, name), "w") as fh:
                fh.write(text)
        prohibition = scrape_prohibition(text)
        ai_train = ai_training_prohibition(text)
        grant = bespoke_permission(text)
        legal_pages.append(
            {
                "url": url,
                "file": name if text else None,
                # strong: a directed "you may not scrape/crawl" clause → a real Crawl signal
                "prohibits_scraping": bool(prohibition),
                "prohibition_snippet": prohibition,
                # a directed "may not be used to train AI/ML" clause → a site-wide AI opt-out
                "prohibits_ai_training": bool(ai_train),
                "ai_training_snippet": ai_train,
                # a directed NON-named reuse grant ("may be reproduced for non-commercial use")
                "bespoke_permission": bool(grant),
                "permission_snippet": grant,
                # weak: page just mentions automated processing (often the site's OWN); info only
                "mentions_automated": bool(SCRAPE_WORDS.search(text)),
            }
        )
        lic_pages.append((url, raw, text))
    return legal_pages, lic_pages


def capture(domain, project, browser, proxy, update, reset=False, ts=None):
    """Capture compliance evidence for `domain`. If `ts` is set the site is DEAD and
    crawled via the Wayback Machine — every page is fetched from the archive snapshot
    (web/<ts>id_/<url>, raw, links un-rewritten) instead of the (gone) live domain, so
    robots/legal/licence reflect what the archived site said.

    Snapshot modes: default skips a domain that already has one; `update` adds a new dated
    snapshot, KEEPING the old ones (time-versioning); `reset` OVERWRITES — it removes this
    domain's prior dated snapshots and writes a single fresh one (no history)."""
    domain = norm_domain(domain)
    if domain == "web.archive.org":
        print(f"  skip {domain} (Wayback wrapper with no resolvable original domain)")
        return "skipped"
    org_base = org_compliance_dir(project, domain)
    snaps = existing_snapshots(org_base)
    today = datetime.date.today().isoformat()
    if snaps and not (update or reset):
        print(
            f"  skip {domain} (have snapshot {snaps[-1]}; --update to add a dated copy, "
            "--reset to overwrite)"
        )
        return "skipped"
    if reset:
        # --reset: clean slate — drop ALL prior dated snapshots for this domain, leaving only
        # today's fresh capture (runs only because the user explicitly passed --reset).
        for d in glob.glob(os.path.join(org_base, "*")):
            if DATE_RE.match(os.path.basename(d)) and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
    base = os.path.join(org_base, today)  # each check is its own dated snapshot
    os.makedirs(base, exist_ok=True)
    # clean only THIS date's dir (older dated snapshots are history — never touched here)
    for old in glob.glob(os.path.join(base, "*")):
        if os.path.isfile(old):
            os.remove(old)
    record = os.path.join(base, "compliance.json")
    tmp = os.path.join(base, "_tmp")

    ua = spider_user_agent(project, domain)  # robots judged for the UA we actually send

    def fetch(url, force_browser=False):
        """Fetch a live URL, or its raw Wayback snapshot when this is an archived site."""
        return inspect(
            f"https://web.archive.org/web/{ts}id_/{url}" if ts else url,
            project,
            tmp,
            browser or force_browser,
            proxy,
        )

    def fetch_rich(url):
        """Fetch a content page, retrying once with the browser if the readable text is thin
        (JS-rendered terms/licence pages return little to a lightweight fetch)."""
        raw = fetch(url) or ""
        if not browser and len(visible_text(raw)) < 200:
            raw2 = fetch(url, force_browser=True) or ""
            if len(visible_text(raw2)) > len(visible_text(raw)):
                return raw2
        return raw

    robots_txt, robots, blocked, ai_bots = _capture_robots(
        fetch, base, project, domain, ua, browser
    )
    wk = _capture_wellknown(fetch, base, domain, robots_txt)
    home, home_text, jl, legals = _capture_homepage(fetch_rich, domain)
    legal_pages, lic_pages = _capture_legal_pages(
        fetch_rich, base, legals, home, home_text
    )

    lic = refine_license(detect_license(lic_pages, jl))
    # "All Rights Reserved" notice — its OWN signal (not the licence): near-ubiquitous footer
    # boilerplate that does NOT preclude a licence elsewhere on the site.
    all_rights_reserved = any(
        re.search(r"all rights reserved", t or "", re.I) for _, _, t in lic_pages
    )

    # Copyright — the FULL statement, read across home + every legal page (not an 80-char
    # homepage snippet). Pick the fullest; flag an INTRA-SITE discrepancy only on a MATERIAL
    # difference (the named rights-holder differs between pages), never year/wording variance.
    cprt = []
    for src, _, text in lic_pages:
        full, years, holder = copyright_statement(text)
        if full:
            cprt.append(
                {"source": src, "statement": full, "years": years, "holder": holder}
            )
    copyright_full = cprt[0]["statement"] if cprt else None
    copyright_years = (
        next((c["years"] for c in cprt if c["years"]), None) or jl["copyright_year"]
    )
    copyright_holder = jl["copyright_holder"] or next(
        (c["holder"] for c in cprt if c["holder"]), None
    )
    copyright_discrepancy = None
    holders = {(c["holder"] or "").lower() for c in cprt if c["holder"]}
    if len(holders) > 1:
        copyright_discrepancy = {"kind": "holder", "claims": cprt[:4]}

    # Bespoke non-named reuse grant anywhere (home or a legal page) — the most useful informal
    # reuse signal; LICENSE_RE misses it because it isn't a named CC/OGL licence.
    bespoke = bespoke_permission(home_text) or next(
        (p["permission_snippet"] for p in legal_pages if p.get("bespoke_permission")),
        None,
    )

    rmeta = robots_meta(home)
    tdmm = tdm_meta(home)
    # HTTP-header-only signals inspect can't surface (it returns the body only): X-Robots-Tag
    # and the TDMRep Tdm-Reservation/Tdm-Policy headers. Best-effort stdlib probe (tri-state —
    # see header_signals). Skipped for Wayback: the archive serves ITS headers, not the
    # original site's, so a live header read would be meaningless.
    hdrs = (
        header_signals(f"https://{domain}/")
        if not ts
        else {
            "fetch_status": "skipped",
            "x_robots_tag": None,
            "tdm_reservation": None,
            "tdm_policy": None,
            "noai": None,
        }
    )

    # ---- AI signals SPLIT across the two axes, CLASSIFIED by type ----
    # ACCESS (may we FETCH for AI?) — machine-readable: robots AI-bot bans (whole/partial/
    # heuristic) + Spawning ai.txt.
    ai_scrape_block = ai_scrape_block_from(ai_bots, wk.get("ai_txt", {}).get("present"))
    # REUSE (may it ENTER the corpus?) — TDMRep / noai / a prohibiting llms.txt are
    # MACHINE-READABLE; a no-AI-training ToS clause is LEGAL-TEXT only.
    tdm_reserved = bool(
        wk.get("tdmrep", {}).get("present") or tdmm or header_tdm_reserved(hdrs)
    )
    noai = bool(
        (rmeta and re.search(r"noai|noimageai", rmeta, re.I)) or hdrs.get("noai")
    )
    llms_prohibits = wk.get("llms_txt", {}).get("verdict") in ("prohibits", "partial")
    ai_train_clause = any(p.get("prohibits_ai_training") for p in legal_pages)
    ai_reuse_reserved = bool(tdm_reserved or noai or llms_prohibits or ai_train_clause)
    # "machine-readable prohibition" = any MR signal; a ToS clause ALONE never sets it.
    machine_readable_prohibition = bool(
        ai_scrape_block or tdm_reserved or noai or llms_prohibits
    )

    # legacy fields — kept so older readers and the existing report fallbacks keep working
    per_ai_bot = bool(blocked)
    site_wide_ai = ai_reuse_reserved
    ai_opt_out = ai_scrape_block or ai_reuse_reserved

    summary = {
        "_instructions": INSTRUCTIONS,
        "domain": domain,
        "checked": today,
        # live site, or read from the Wayback Machine because the original is gone
        "source": "wayback" if ts else "live",
        "archived_timestamp": ts,
        "user_agent": ua,  # the UA robots was judged for (what our crawler sends)
        "robots": robots,
        # header-only signals (X-Robots-Tag / TDMRep headers) the body-fetch can't see —
        # tri-state fetch_status: 'ok' trusts an absence, 'blocked' does not, 'skipped' = Wayback
        "http_headers": hdrs,
        "ai": {
            # --- legacy (back-compat with older snapshots / report fallbacks) ---
            "ai_opt_out": ai_opt_out,
            "site_wide_ai": site_wide_ai,
            "per_ai_bot": per_ai_bot,
            "ai_bots_blocked": blocked,  # whole-site names — EVIDENCE only
            # --- split typed signals ---
            "ai_scrape_block": ai_scrape_block,  # ACCESS axis (machine-readable)
            "ai_reuse_reserved": ai_reuse_reserved,  # REUSE axis
            "machine_readable_prohibition": machine_readable_prohibition,
            "tdm_reserved": tdm_reserved,
            "noai": noai,
            "ai_training_clause": ai_train_clause,  # LEGAL-text only (not MR)
            "channel_blocked": ai_bots.get("channel")
            or [],  # PerplexityBot etc. — by name
            "ai_bot_signals": ai_bots,  # full/partial/allowed/heuristic
            "llms": wk.get("llms_txt", {"present": False}),
            "robots_meta": rmeta,
            "tdmrep": wk.get("tdmrep", {"present": False}),
            "tdm_meta": tdmm,
            "ai_txt": wk.get("ai_txt", {"present": False}),
        },
        "license": lic["license"],
        "license_url": lic["license_url"],
        "license_source": lic["license_source"],
        "license_quote": lic.get("license_quote"),
        "license_confidence": lic.get("license_confidence"),
        "license_jsonld": jl["license"],
        # bespoke non-named reuse grant (separate from a CC/OGL licence)
        "bespoke_permission": bespoke,
        "legal_pages": legal_pages,
        # an "all rights reserved" notice — its own signal, NOT a licence (can coexist with a grant)
        "all_rights_reserved": all_rights_reserved,
        # copyright — FULL statement across pages + parsed holder/year + intra-site discrepancy
        "copyright": copyright_full,
        "copyright_all": cprt,
        "copyright_meta": meta_copyright(home),
        "copyright_holder": copyright_holder,
        "copyright_year": copyright_years,
        "copyright_discrepancy": copyright_discrepancy,
        # --- human review fields (NOT set by the tool; see _instructions) ---
        "verdict": None,
        "reviewed": False,
        "reviewed_by": None,
        "notes": "",
    }

    # Reachability: 'failed' = we reached NEITHER robots.txt NOR a homepage body (total block /
    # dead site). A reachable-but-sparse site is a real finding, not a failure.
    # A dated snapshot is written ONLY for a reachable domain: writing it first used to
    # stamp an unreachable domain "checked: <today>" with an empty record, which the
    # report then presented as a real (all-absent) compliance result and the audit's
    # default mode treated as "already captured" forever.
    reachable = bool(home_text) or robots.get("fetched")
    shutil.rmtree(tmp, ignore_errors=True)
    if reachable:
        clear_capture_failed(project, domain)
        with open(record, "w") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    else:
        mark_capture_failed(
            project,
            domain,
            "unreachable — neither robots.txt nor homepage fetched"
            + ("" if browser else " (try --browser / a proxy)"),
        )
        # drop TODAY's empty dated dir; OLDER good snapshots survive a failed --refresh
        shutil.rmtree(base, ignore_errors=True)

    notes = []
    if ai_bots["full"]:
        notes.append(f"⚠ AI bots blocked: {', '.join(ai_bots['full'])}")
    if ai_reuse_reserved:
        notes.append("⚠ AI-reuse reserved")
    if any(p["prohibits_scraping"] for p in legal_pages):
        notes.append("⚠ ToS prohibits scraping")
    via = f" [Wayback @{ts}]" if ts else ""
    print(
        f"  {'✓' if reachable else '‼'} {domain}{via}: crawl={crawl_robots_cell(summary)!r} "
        f"ai_scrape={ai_scrape_block} ai_reuse={ai_reuse_reserved} "
        f"license={summary['license']!r} legal={len(legal_pages)} {' · '.join(notes)}"
    )
    return "ok" if reachable else "failed"


def run(project, opts):
    """Standalone compliance capture for `project`: capture the requested domains (or all the
    project's spider domains when none given), ALWAYS (re)write the rollup report, and RETURN
    {report_path, domains}. `opts` supplies `.domains` (list; empty = all spider domains),
    `.browser`, `.proxy_type`, `.update`, `.reset`. The audit runs this stage inline;
    this entry point is for the standalone/programmatic path."""
    domains = getattr(opts, "domains", None) or []
    browser = getattr(opts, "browser", False)
    proxy_type = getattr(opts, "proxy_type", "auto")
    update = getattr(opts, "update", False)
    reset = getattr(opts, "reset", False)

    ptargets = project_targets(project)
    if domains:
        targets = {}
        for d in domains:
            if "web.archive.org" in d:  # a Wayback URL passed directly
                inner = unwrap_wayback(d)
                if inner and inner != "web.archive.org":
                    targets[inner] = wayback_ts(d)
            else:  # a bare domain inherits its
                dom = norm_domain(d)  # Wayback timestamp from the project
                targets[dom] = ptargets.get(dom)  # spider, if it's an archived site
    else:
        targets = ptargets
    targets = {d: ts for d, ts in targets.items() if d}
    if targets:
        print(
            f"Compliance capture → {os.path.join(DATA_DIR, project, '_audit', 'compliance')}"
            f"/<org>/<date>/  ({len(targets)} domain(s))"
        )
        for d in sorted(targets):
            capture(d, project, browser, proxy_type, update, reset, ts=targets[d])
    else:
        print(
            f"No spider domains found in {os.path.join(DATA_DIR, project)}; "
            f"regenerating report from existing snapshots."
        )
    # the project rollup in _audit/ is ALWAYS (re)written
    path = write_report(project)
    print(f"Report → {path}")
    return {"report_path": path, "domains": sorted(targets)}


def main():
    ap = argparse.ArgumentParser(
        description="Capture robots/legal/licence/AI signals per domain."
    )
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "domains",
        nargs="*",
        help="domains/URLs to check; omit to use the project's spiders",
    )
    ap.add_argument(
        "--browser", action="store_true", help="use CloakBrowser (JS/Cloudflare)"
    )
    ap.add_argument("--proxy-type", default="auto", help="none|static|residential|auto")
    ap.add_argument(
        "--update",
        action="store_true",
        help="re-capture domains that already have a snapshot, appending a NEW dated "
        "copy (keeps history — time-versioning)",
    )
    ap.add_argument(
        "--reset",
        action="store_true",
        help="re-capture domains, OVERWRITING: drop their prior dated snapshots and "
        "write a single fresh one (no history). Use --update to keep history.",
    )
    args = ap.parse_args()

    if not project_exists(args.project):
        raise SystemExit(
            f"❌ No project named '{args.project}'. Compliance only runs on an existing "
            f"project. Run `./scrapai projects list` to see existing projects, or create the "
            f"project first. Nothing was created."
        )
    run(args.project, args)


if __name__ == "__main__":
    main()
