"""CLI entry (main) and the audit orchestrator (run): compliance stage, crawl-output
scan, per-spider scoring loop, and the compliance summary joined into the report."""

import argparse
import glob
import os
import sys
import time

from core.quality._env import DATA_DIR
from core.quality import (
    compliance_capture as cc,
)  # reused for the inline compliance stage + summary

# The JSONL scan machinery (fingerprinting, per-file scan + counts cache, project
# aggregation) lives in core.quality.corpus — the ONE home shared with dedupe, so
# the report's "true dupes" always equals what the default dedupe collapses.
from core.quality.corpus import scan_project as crawl_audit

from .report import write_outputs
from .review import ensure_review_configs, load_notes, load_skip
from .scoring import ScoreContext, score_spider
from .sitemaps import spider_cache_dirs
from .spiders_db import audit_dir, load_spiders, project_exists

DEFAULT_PER_CAP = 80  # max sitemap fetches per spider
DEFAULT_GLOBAL_CAP = 2000  # max sitemap fetches overall


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Coverage & extraction audit for a project."
    )
    ap.add_argument("--project", required=True)
    ap.add_argument(
        "--no-fetch",
        "--skip-fetch",
        action="store_true",
        dest="no_fetch",
        help="never fetch sitemaps; use only cached files + crawl-recorded "
        "counts (--skip-fetch is a back-compat alias)",
    )
    ap.add_argument(
        "--fetch-all",
        action="store_true",
        help="re-fetch every spider's sitemap (refresh the cache); the "
        "DEFAULT fetches only spiders with no cached sitemap yet. "
        "Spiders whose counts came from the crawl are never fetched.",
    )
    ap.add_argument(
        "--per-cap",
        type=int,
        default=DEFAULT_PER_CAP,
        help=f"max sitemap fetches per spider (default {DEFAULT_PER_CAP})",
    )
    ap.add_argument(
        "--global-cap",
        type=int,
        default=DEFAULT_GLOBAL_CAP,
        help=f"max sitemap fetches overall (default {DEFAULT_GLOBAL_CAP})",
    )
    ap.add_argument(
        "--no-browser-retry",
        action="store_true",
        help="do not retry failed sitemap fetches with --browser",
    )
    ap.add_argument("--only", nargs="+", help="restrict to these spider names")
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the per-file crawl-scan cache and re-read every "
        "crawls/*.jsonl from scratch (the cache is still rewritten)",
    )
    ap.add_argument(
        "--refresh-compliance",
        action="store_true",
        help="re-run compliance_capture for domains that ALREADY have a snapshot "
        "(and retry failed ones), appending a new dated snapshot (keeps "
        "history). Default: capture only NEW domains, never retry a failure.",
    )
    ap.add_argument(
        "--no-compliance",
        action="store_true",
        help="skip the compliance stage entirely (read existing snapshots only; "
        "fast, zero network).",
    )
    args = ap.parse_args()

    project = args.project
    if not project_exists(project):
        sys.exit(
            f"❌ No project named '{project}'. The audit only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects, or create the project "
            f"first. Nothing was created."
        )
    run(project, args)


def run(project, opts):
    """Programmatic entry point for the audit. Runs the crawl-output audit + sitemap
    fetch/match and (unless disabled) the inline compliance stage for `project`; writes
    `audit_<project>.md`, `crawl_audit.csv`, `coverage.csv`; and RETURNS the structured
    result `{'rows': [...], 'compliance': {...}}` the dashboard renders from. `opts` carries
    the same switches as the root CLI: `no_fetch`, `fetch_all`, `per_cap`, `global_cap`,
    `no_browser_retry`, `only`, `no_cache`, `refresh_compliance`, `no_compliance`, and
    (optionally) `reset` for the compliance snapshot."""
    args = opts
    if not project_exists(project):
        # Guard the programmatic path too (main() and the CLI wrapper already check):
        # running on an unknown name would scaffold an empty data/<project>/ tree and
        # write a blank report.
        raise SystemExit(
            f"❌ No project named '{project}'. The audit only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects. Nothing was created."
        )
    cache_dir = os.path.join(DATA_DIR, project, "_audit", "sitemap_cache")
    state = {"global": 0, "global_cap": args.global_cap, "per_cap": args.per_cap}

    # Fetch mode. Spiders whose sitemap counts came from the crawl (crawl_stats)
    # are NEVER fetched in any mode (handled separately below).
    #   missing (default) — fetch only spiders with no cached sitemap yet
    #   none  (--no-fetch / --skip-fetch) — never fetch; use whatever is cached
    #   all   (--fetch-all) — re-fetch every spider, refreshing the cache
    fetch_mode = "none" if args.no_fetch else ("all" if args.fetch_all else "missing")

    def has_cache(name):
        """True if a prior run already RESOLVED this spider's sitemap: a sitemap was
        fetched (sub-sitemap dirs with actual content), the /sitemap.xml probe ran
        (_smprobe), or we recorded 'no sitemap here' (_nositemap). robots.txt alone
        doesn't count — it's fetched for every site and doesn't mean we concluded
        anything. So 'missing' mode never re-probes a site we've already confirmed
        has no sitemap. Requires a non-empty page.html: legacy caches (pre temp+swap
        fetch) can hold empty dirs from failed fetches, and counting those as
        "resolved" is what used to freeze a transient outage into a permanent
        total=0 until someone thought to run --fetch-all."""
        if any(
            os.path.exists(fp) and os.path.getsize(fp) > 0
            for d in spider_cache_dirs(name, cache_dir)
            for fp in [os.path.join(d, "page.html")]
        ):
            return True
        sm = os.path.join(cache_dir, name + "_smprobe", "page.html")
        if os.path.exists(sm) and os.path.getsize(sm) > 0:
            return True
        return os.path.exists(os.path.join(cache_dir, name + "_nositemap"))

    def mark_no_sitemap(name):
        """Record that discovery found no sitemap, so default (missing) mode won't
        re-probe it on the next run. --fetch-all ignores this and re-checks."""
        os.makedirs(cache_dir, exist_ok=True)
        open(os.path.join(cache_dir, name + "_nositemap"), "w").close()

    def should_fetch(name):
        if fetch_mode == "none":
            return False
        if fetch_mode == "all":
            return True
        return not has_cache(name)  # 'missing' — only where nothing cached

    print(f"[1/3] loading spider metadata for project '{project}'...", flush=True)
    spiders = load_spiders(project)
    ensure_review_configs(
        project
    )  # create stubs if absent; keep `_instructions` current (entries untouched)
    skip, config_warnings = load_skip(project)
    notes, note_warnings = load_notes(project)
    config_warnings = config_warnings + note_warnings
    for w in config_warnings:
        print(f"  ⚠ {w}", flush=True)
    if args.only:
        spiders = {k: v for k, v in spiders.items() if k in args.only}

    # A spider whose project data folder has been deleted is treated as removed
    # from the project: drop it from the audit (even if its DB row lingers). The
    # folder is the source of truth for "is this spider part of the working set",
    # so deleting the folder is enough to make it disappear here. Not silent — log
    # each one — and clean up its orphaned audit artifacts so they don't pile up.
    removed = [
        n for n in spiders if not os.path.isdir(os.path.join(DATA_DIR, project, n))
    ]
    for n in removed:
        print(
            f"      ⤬ skipping '{n}' — {os.path.join(DATA_DIR, project, n)}/ folder is "
            f"gone (removed from project)",
            flush=True,
        )
        spiders.pop(n, None)
        for stale in (
            os.path.join(DATA_DIR, project, "_audit", "crawl_stats", f"{n}.json"),
            os.path.join(DATA_DIR, project, "_audit", "scan_cache", f"{n}.json"),
        ):
            try:
                os.remove(stale)
            except OSError:
                pass

    print(
        f"      {len(spiders)} spiders; "
        f"{sum(1 for s in spiders.values() if s['use_sitemap'])} use sitemaps; "
        f"{len(skip)} sitemap-skip entries"
    )

    # ---- compliance stage: capture NEW domains only; never retry a FAILED one (default).
    # --refresh-compliance re-captures existing snapshots + retries failures (keeps history);
    # --no-compliance skips entirely. Guarded so it can never break the audit. ----
    compliance_data = None  # build_report_data triple, shared with the dashboard
    if not args.no_compliance:
        print(
            "[compliance] capture (new domains only; --refresh-compliance for existing) ...",
            flush=True,
        )
        seen_dom, n_cap, n_fail, n_skip = set(), 0, 0, 0
        for name in sorted(spiders):
            host = cc.norm_domain(spiders[name].get("host") or "")
            if not host or host == "web.archive.org" or host in seen_dom:
                continue
            seen_dom.add(host)
            org_base = cc.org_compliance_dir(project, host)
            if not args.refresh_compliance and (
                cc.existing_snapshots(org_base) or cc.has_capture_failed(project, host)
            ):
                n_skip += 1
                continue  # already captured, or a known failure we deliberately don't retry
            try:
                status = cc.capture(
                    host,
                    project,
                    browser=spiders[name].get("browser", False),
                    proxy="auto",
                    update=args.refresh_compliance,
                    reset=getattr(args, "reset", False),
                )
            except Exception as e:  # a crash counts as a failed attempt
                cc.mark_capture_failed(project, host, f"capture crashed: {e!r}")
                status = "failed"
            n_cap += status == "ok"
            n_fail += status == "failed"
        print(
            f"      compliance: {n_cap} captured, {n_fail} failed, "
            f"{n_skip} skipped (already done / known-failed)",
            flush=True,
        )
        try:
            # one snapshot load + refine, shared with the dashboard via the return dict
            compliance_data = cc.build_report_data(project)
            cc.write_report(project, data=compliance_data)
        except Exception as e:
            print(f"      ⚠ compliance report refresh failed: {e}", flush=True)

    print("[2/3] crawl-output audit...", flush=True)
    crawl = crawl_audit(project, use_cache=not args.no_cache)

    print(f"[3/3] sitemap fetch (mode: {fetch_mode}) + rule-match...", flush=True)
    ctx = ScoreContext(
        project=project,
        opts=args,
        cache_dir=cache_dir,
        state=state,
        skip=skip,
        notes=notes,
        has_cache=has_cache,
        mark_no_sitemap=mark_no_sitemap,
        should_fetch=should_fetch,
    )
    rows = []
    for name in sorted(spiders):
        row = score_spider(name, spiders[name], crawl.get(name, {}), ctx)
        rows.append(row)
        print(
            f"  {name:<35} {row['status']:<26} "
            f"scraped={row['scraped']} cov={row['coverage_pct']}%",
            flush=True,
        )

    compliance = compliance_summary(project, spiders)
    write_outputs(project, rows, config_warnings, compliance)
    out = audit_dir(project)
    print(
        f"\nDone. {state['global']} inspect fetches. "
        f"Wrote {out}/audit_{project}.md, {out}/crawl_audit.csv, {out}/coverage.csv"
    )
    return {
        "rows": rows,
        "compliance": compliance,
        "config_warnings": list(config_warnings),
        # the already-refined snapshot data (or None on --no-compliance / failure) —
        # write_dashboard reuses it so the snapshots aren't loaded + refined twice
        "_compliance_data": compliance_data,
    }


def _check_behind_crawl(project, spider, snapshot_date):
    """True if the spider's newest crawls/*.jsonl is more than a day newer than its latest
    compliance snapshot — i.e. it was scraped WITHOUT a fresh compliance check."""
    if not snapshot_date:
        return False
    files = glob.glob(os.path.join(DATA_DIR, project, spider, "crawls", "*.jsonl"))
    if not files:
        return False
    try:
        snap = time.mktime(time.strptime(snapshot_date, "%Y-%m-%d"))
    except (ValueError, TypeError):
        return False
    return max(os.path.getmtime(f) for f in files) > snap + 86400


def compliance_summary(project, spiders):
    """{spider: {domain, checked, access, reuse, license, ai_scrape, ai_reuse, mr_ban, llms,
    conflicts, failed, stale}} for the audit's Compliance section. Each spider maps to its
    PRIMARY domain (host). Reuses compliance_capture's assessors + cross_check, so this and
    `compliance_<project>.md` can never disagree. Guarded — never breaks the audit."""
    out = {}
    for name, sp in spiders.items():
        try:
            host = cc.norm_domain(sp.get("host") or "")
        except Exception:
            host = ""
        if not host or host == "web.archive.org":
            continue
        org_base = cc.org_compliance_dir(project, host)
        date, rec = cc.latest_snapshot(org_base)
        e = {
            "domain": host,
            "checked": date,
            "failed": cc.has_capture_failed(project, host),
            "access": None,
            "reuse": None,
            "license": None,
            "ai_scrape": False,
            "ai_reuse": False,
            "mr_ban": False,
            "llms": None,
            "conflicts": [],
            "stale": False,
        }
        if rec:
            try:
                cc.refine_license(rec)
                e["access"] = cc.assess_crawl(rec)[1]
                e["reuse"] = cc.assess_reuse(rec)[1]
                e["license"] = rec.get("license")
                ai = rec.get("ai", {})
                e["ai_scrape"] = bool(cc.ai_scrape_flag(ai))
                e["ai_reuse"] = bool(cc.ai_reuse_flag(ai))
                e["mr_ban"] = bool(ai.get("machine_readable_prohibition"))
                llms = ai.get("llms") or {}
                e["llms"] = llms.get("verdict") if llms.get("present") else None
                e["conflicts"] = list(
                    cc.cross_check(project, host, rec).get("conflict_kinds", [])
                )
                e["stale"] = _check_behind_crawl(project, name, date)
            except Exception as ex:
                e["error"] = repr(ex)
        out[name] = e
    return out
