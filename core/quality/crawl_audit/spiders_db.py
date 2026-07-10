"""Spider metadata from the DB, per-spider crawl-stats readers, and the audit
output directory."""

import json
import os
from urllib.parse import urlparse

from core.quality._env import DATA_DIR
from core.quality import _env


def audit_dir(project):
    """Per-project output dir: data/<project>/_audit/ (created if missing)."""
    d = os.path.join(DATA_DIR, project, "_audit")
    os.makedirs(d, exist_ok=True)
    return d


def crawl_stats_liveness(project, spider):
    """EXACT liveness from a real crawl's own stats (written by
    the spider's closed() handler), preferred over sampling. live = 2xx ÷ (2xx +
    4xx + 5xx) across everything the crawl actually fetched — no extra requests."""
    path = os.path.join(DATA_DIR, project, "_audit", "crawl_stats", spider + ".json")
    try:
        with open(path) as fh:
            d = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    status = d.get("status", {})
    ok = sum(v for k, v in status.items() if k.startswith("2"))
    bad = sum(v for k, v in status.items() if k.startswith(("4", "5")))
    if ok + bad == 0:
        return None
    return {"rate": round(ok / (ok + bad), 4), "sample": ok + bad}


def crawl_ran(project, spider):
    """True if a real crawl recorded its own stats for this spider — proof it
    actually executed, independent of whether it produced any output. Same file
    liveness reads from, so if we trust it for liveness we can trust it here. Used
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
    """Return {name: {start_urls, use_sitemap, rules, browser}} for the project."""
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
            # reports `no` (e.g. unep.org).
            sp["browser"] = True
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
