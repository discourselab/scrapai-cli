"""Spider metadata from the DB, per-spider crawl-stats readers, the robots
`Sitemap:` lines already on disk, and the audit output directory."""

import json
import os
from urllib.parse import urlparse

from core.quality._env import DATA_DIR
from core.quality import _env
from core.quality.compliance_capture.store import (
    DATE_RE,
    latest_crawl_file,
    norm_domain,
    slug,
)

from .sitemaps import SITEMAP_DIRECTIVE, _looks_like_html


def audit_dir(project):
    """Per-project output dir: data/<project>/_audit/ (created if missing)."""
    d = os.path.join(DATA_DIR, project, "_audit")
    os.makedirs(d, exist_ok=True)
    return d


def crawl_stats_liveness(project, spider):
    """EXACT liveness from a real crawl's own stats (written by
    the spider's closed() handler), preferred over sampling. live = 2xx ÷ (2xx +
    4xx) across everything the crawl actually fetched — no extra requests.

    No longer scales the coverage denominator (a 403 block read as a "dead"
    URL and shrank eligible, hiding the shortfall); kept on the facade for
    callers that read the crawl-stats writer's output.

    Only 4xx count as "dead" (the URL doesn't exist). 5xx are transient server
    errors — a 503/502/504 during the crawl says nothing about whether the URL is
    real — so they're excluded from the denominator entirely. Counting them as
    dead used to shrink the eligible denominator and under-report coverage for any
    site that threw transient 5xx mid-crawl (e.g. an 810×503 run reading as 56%
    "live" when the URLs were fine)."""
    path = os.path.join(DATA_DIR, project, "_audit", "crawl_stats", spider + ".json")
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    status = d.get("status", {})
    ok = sum(v for k, v in status.items() if k.startswith("2"))
    bad = sum(v for k, v in status.items() if k.startswith("4"))
    if ok + bad == 0:
        return None
    return {"rate": round(ok / (ok + bad), 4), "sample": ok + bad}


def crawl_ran(project, spider):
    """True if a real crawl recorded its own stats for this spider — proof it
    actually executed, independent of whether it produced any output. Used
    to tell 'never-ran' (no crawl_stats at all) apart from 'ran but came back
    empty' (crawl_stats present, but the crawls/*.jsonl is empty)."""
    path = os.path.join(DATA_DIR, project, "_audit", "crawl_stats", spider + ".json")
    try:
        with open(path) as fh:
            json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return True


def crawl_stats_sitemap(project, spider):
    """Sitemap size + rule-eligible count recorded BY THE CRAWL (sitemap_spider.py
    counts them while parsing; closed() writes them). Preferred over re-fetching the
    sitemap here: it's the denominator the crawl actually faced, at the crawl's own
    point in time, so there's no sitemap-drift mismatch. Returns None when the crawl
    didn't record it (rule-based spider, or a pre-feature crawl) -> caller fetches."""
    path = os.path.join(DATA_DIR, project, "_audit", "crawl_stats", spider + ".json")
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if "sitemap_total" not in d:
        return None
    return {"total": d["sitemap_total"], "eligible": d.get("eligible", 0)}


# HTTP codes behind the dead / blocked outcome figures. dead = the URL is gone;
# blocked = the site refused us (forbidden, rate-limited, auth wall).
DEAD_CODES = ("404", "410")
BLOCKED_CODES = ("403", "429", "401")


def _codes(counts, codes):
    return sum(int(counts.get(c, 0) or 0) for c in codes)


def crawl_stats_outcomes(project, spider):
    """Final request outcomes from the crawl's own stats, for the dead /
    blocked / failed figures: {dead, blocked, failed, base, final}, or None
    when the crawl recorded no stats. Pure disk read.

    final=True when the crawl-stats writer recorded the FINAL-outcome keys
    (`responses`, `final_status`, `exceptions`, `retries`): dead/blocked
    come from `final_status` (non-2xx responses the crawl gave up on, after
    retry and proxy fallback; the compliance witness fetches never land
    there), and failed = requests that never got a response — per exception
    class, raised count minus the times it was retried. IgnoreRequest is
    skipped: an offsite or robots drop is a deliberate non-request, not a
    failure. base = responses + failed, the denominator for percentages.

    final=False for an older file that has only the attempt-level `status`
    counts (every attempt, retried ones included, plus the robots/llms
    witness fetches): dead/blocked are read from it for information only
    and never flag; failed is None (unknown).

    resumed=True when the writer stamped the file `"resumed": true` (the
    crawl continued from a checkpoint); summed=True when it also stamped
    `"summed": true` — the writer added the earlier legs' counters in, so the
    figures are the whole crawl's. resumed without summed = the last leg
    only (an earlier leg died before it could hand its counters on)."""
    path = os.path.join(
        DATA_DIR,
        project,
        "_audit",
        "crawl_stats",
        spider + ".json",
    )
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(d, dict):
        return None
    if "responses" in d:
        final_status = d.get("final_status") or {}
        retries = d.get("retries") or {}
        failed = 0
        for cls, n in (d.get("exceptions") or {}).items():
            if cls.rsplit(".", 1)[-1] == "IgnoreRequest":
                continue
            failed += max(0, int(n or 0) - int(retries.get(cls, 0) or 0))
        return {
            "dead": _codes(final_status, DEAD_CODES),
            "blocked": _codes(final_status, BLOCKED_CODES),
            "failed": failed,
            "base": int(d["responses"] or 0) + failed,
            "final": True,
            "resumed": bool(d.get("resumed")),
            "summed": bool(d.get("summed")),
        }
    status = d.get("status") or {}
    attempts = sum(int(v or 0) for v in status.values())
    return {
        "dead": _codes(status, DEAD_CODES),
        "blocked": _codes(status, BLOCKED_CODES),
        "failed": None,
        "base": attempts or int(d.get("requests") or 0),
        "final": False,
        "resumed": bool(d.get("resumed")),
        "summed": bool(d.get("summed")),
    }


def _read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def robots_sitemaps_on_disk(project, host, spider):
    """The site's robots.txt `Sitemap:` lines, from what is ALREADY on disk —
    zero fetches. Sources, unioned in this order (deduped, first spelling
    kept): the latest compliance snapshot for the host (its compliance.json
    robots.sitemaps and the stored robots.txt), the spider's newest crawl
    witness crawls/robots_<date>.txt, and the robots.txt an earlier sitemap
    discovery cached under sitemap_cache/<spider>_robots/. Returns the list
    (possibly empty: robots exist but declare no sitemap) or None when no
    robots.txt is on disk at all, so the caller can tell "none declared" from
    "never looked"."""
    texts, declared = [], []
    audit = os.path.join(DATA_DIR, project, "_audit")
    if host:
        org = os.path.join(audit, "compliance", slug(norm_domain(host)))
        dates = sorted(
            d
            for d in (os.listdir(org) if os.path.isdir(org) else [])
            if DATE_RE.match(d)
        )
        if dates:
            snap = os.path.join(org, dates[-1])
            try:
                with open(os.path.join(snap, "compliance.json")) as fh:
                    robots = json.load(fh).get("robots") or {}
                if robots.get("fetched"):
                    texts.append("")  # fetched, even if it lists no sitemap
                declared += robots.get("sitemaps") or []
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
            texts.append(_read_text(os.path.join(snap, "robots.txt")))
    spider_dir = os.path.join(DATA_DIR, project, spider)
    witness = latest_crawl_file(spider_dir, "robots")
    if witness:
        texts.append(witness[1])
    cached = os.path.join(audit, "sitemap_cache", spider + "_robots")
    texts.append(_read_text(os.path.join(cached, "page.html")))
    # an HTML body is a challenge / soft-404 page, not robots — no evidence
    texts = [t for t in texts if t is not None and not _looks_like_html(t)]
    if not texts and not declared:
        return None
    for t in texts:
        declared += SITEMAP_DIRECTIVE.findall(t)
    out, seen = [], set()
    for u in declared:
        if u.strip() and u.strip() not in seen:
            seen.add(u.strip())
            out.append(u.strip())
    return out


# ----------------------------------------------------------------------------- DB
# Repo-anchored subprocess + DB access. db_query raises ScrapaiCliError on any CLI
# failure (returns [] only for a genuinely empty result), so a broken DB aborts the
# audit instead of writing an empty report over a good one.
db_query = _env.db_query


def _loads(v, default):
    """JSON columns come back as (double-encoded) strings or None."""
    if v is None:
        return default
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s in ("", "null"):
            return default
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return default
    return default


project_exists = _env.project_exists


def load_spiders(project):
    """Return {name: {start_urls, use_sitemap, rules, browser,
    status_blind, ...}} for the project."""
    p = project.replace("'", "''")
    spiders = {}
    for r in db_query(
        "SELECT name, start_urls, source_url, allowed_domains "
        f"FROM spiders WHERE project='{p}'"
    ):
        src = r.get("source_url") or ""
        host = urlparse(src).netloc if src.startswith("http") else ""
        if not host:
            dom = _loads(r.get("allowed_domains"), [])
            host = (dom[0] if dom else src.split("/")[0]) if (dom or src) else ""
        spiders[r["name"]] = {
            "start_urls": _loads(r.get("start_urls"), []),
            "use_sitemap": False,
            "rules": [],  # list of allow-pattern-lists (one per Rule)
            "deny": [],  # flat list of deny patterns (across all Rules)
            "n_rules": 0,
            "browser": False,
            # Cloudflare / browser mode hands every page back as HTTP 200,
            # so the crawl's status counts can't see a 404 or 403 → the
            # dead/blocked figures read "–". curl_cffi keeps real status
            # codes, so it is NOT status-blind.
            "status_blind": False,
            "host": host,
            # the crawl's own definition of "own org" (gates the offsite
            # middleware) — scoring uses it for the pdf same-org/external split
            "domains": _loads(r.get("allowed_domains"), []),
        }
    for r in db_query(
        "SELECT s.name AS name, ss.key AS key, ss.value AS value "
        "FROM spiders s JOIN spider_settings ss ON ss.spider_id=s.id "
        f"WHERE s.project='{p}' AND ss.key IN "
        "('USE_SITEMAP','CLOUDFLARE_ENABLED','BROWSER_ENABLED','CURL_CFFI_ENABLED')"
    ):
        sp = spiders.get(r["name"])
        if not sp:
            continue
        truthy = str(r["value"]).lower() in ("true", "1")
        if r["key"] == "USE_SITEMAP":
            sp["use_sitemap"] = truthy
        elif (
            r["key"] in ("CLOUDFLARE_ENABLED", "BROWSER_ENABLED", "CURL_CFFI_ENABLED")
            and truthy
        ):
            # Any of these means the site blocks a plain Scrapy/HTTP fetch. The
            # audit's only escalation lever is `--browser` (a real browser also
            # clears the TLS-fingerprint blocks curl_cffi was added for), so a
            # curl_cffi spider is treated as needing browser fetches too —
            # otherwise its sitemap can't be fetched and discovery wrongly
            # reports `no` (e.g. site37.org).
            sp["browser"] = True
            if r["key"] != "CURL_CFFI_ENABLED":
                sp["status_blind"] = True
    for r in db_query(
        "SELECT s.name AS name, sr.allow_patterns AS allow_patterns, "
        "sr.deny_patterns AS deny_patterns "
        "FROM spiders s JOIN spider_rules sr ON sr.spider_id=s.id "
        f"WHERE s.project='{p}'"
    ):
        sp = spiders.get(r["name"])
        if not sp:
            continue
        sp["n_rules"] += 1
        sp["rules"].append(_loads(r.get("allow_patterns"), None))
        sp["deny"].extend(_loads(r.get("deny_patterns"), []) or [])
    return spiders
