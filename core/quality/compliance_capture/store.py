"""Snapshot store + spider-config readers: domain/slug helpers, snapshot dirs and
failure markers, the spider's target URLs / user-agent, and the crawl-capture
witness readers (robots/llms files + legal-page rows the spider stored)."""

import datetime
import glob
import json
import os
import re
from functools import lru_cache
from urllib.parse import urlparse

from core.quality._env import DATA_DIR
from core.quality import _env

from .page import LEGAL_WORDS


def norm_domain(s):
    s = s.strip()
    if "//" not in s:
        s = "https://" + s
    host = (urlparse(s).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def slug(host):
    return host.replace(".", "_")


# Compliance evidence lives WITH the rest of the audit, under the project's _audit folder:
#   data/<project>/_audit/compliance/<orgslug>/<YYYY-MM-DD>/   (orgslug: rmi.org -> rmi_org)
# (previously scattered into each org's own folder as <org>/_compliance/).
def compliance_root(project):
    return os.path.join(DATA_DIR, project, "_audit", "compliance")


def org_compliance_dir(project, domain):
    """The org's compliance snapshot dir under _audit/compliance/. Accepts a domain (it's
    normalised + slugged) or an already-slugged org name (norm_domain leaves it unchanged).
    """
    return os.path.join(compliance_root(project), slug(norm_domain(domain)))


def unwrap_wayback(url):
    """If `url` is a web.archive.org snapshot URL, return the ORIGINAL domain it wraps."""
    m = re.search(r"web\.archive\.org/web/[^/]+/(.+)", url, re.I)
    return norm_domain(m.group(1)) if m else None


def wayback_ts(url):
    """The capture timestamp from a web.archive.org snapshot URL (digits only), or None."""
    m = re.search(r"web\.archive\.org/web/(\d{4,14})", url, re.I)
    return m.group(1) if m else None


def wayback_orig_url(url):
    """The original URL a web.archive.org snapshot wraps (full URL, not just the host)."""
    m = re.search(r"web\.archive\.org/web/[^/]+/(.+)", url, re.I)
    return m.group(1) if m else url


TARGET_CAP = 50  # max representative paths tested against robots per spider


def _allow_target_url(pat, domain):
    """A representative ARTICLE url for an allow-rule regex, e.g.
    `^https://rmi\\.org/resources/[^/]+/?$` → `https://rmi.org/resources/x`. Strips a leading
    `^` and any embedded scheme+host, takes the literal PATH prefix before the first regex
    metachar, and appends a leaf token — so robots is tested against the paths we actually
    scrape, not the bare sitemap files (anchored rules used to yield an empty prefix).
    """
    p = pat.lstrip("^")
    p = re.sub(r"^https?://[^/]+", "", p)  # drop embedded scheme+host if present
    seg = re.split(r"[.*+?(\[\\^$|]", p)[0].strip("/")  # literal path prefix
    return f"https://{domain}/{seg}/x" if seg else f"https://{domain}/x"


def _spider_cfg_path(project, domain):
    """The final_spider.json that crawls `domain`. Prefer the slug-named folder, but fall
    back to ANY spider whose allowed_domains include it — folder names need not equal the
    domain slug (e.g. ncei.noaa.gov lives in folder `noaa_gov_ncei`). None if not found.
    """
    direct = os.path.join(
        DATA_DIR, project, slug(domain), "analysis", "final_spider.json"
    )
    if os.path.exists(direct):
        return direct
    for f in glob.glob(
        os.path.join(DATA_DIR, project, "*", "analysis", "final_spider.json")
    ):
        try:
            ad = [norm_domain(d) for d in json.load(open(f)).get("allowed_domains", [])]
        except (OSError, json.JSONDecodeError):
            continue
        if domain in ad:
            return f
    return None


def spider_target_urls(project, domain):
    """Representative URLs this domain's spider actually crawls — its start_urls plus one
    representative ARTICLE url per allow-rule (Wayback URLs unwrapped to the original).
    Used to test whether robots.txt blocks OUR paths, not just any path. [] if no spider.
    """
    path = _spider_cfg_path(project, domain)
    if not path:
        return []
    try:
        cfg = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return []
    urls = [wayback_orig_url(su) for su in cfg.get("start_urls", [])]
    for rule in cfg.get("rules", []):
        for pat in rule.get("allow", []):
            urls.append(_allow_target_url(pat, domain))
    return list(dict.fromkeys(u for u in urls if u))[:TARGET_CAP]


def _global_user_agent():
    """The project-wide USER_AGENT from settings.py (read textually to avoid importing the
    Scrapy settings module, which isn't loadable standalone here). '*' if not found."""
    try:
        txt = open(_env.SETTINGS_PY, encoding="utf-8", errors="replace").read()
    except OSError:
        return "*"
    # close the paren form on a `)` at the START of a line — the UA value itself contains
    # `)` (e.g. "…10_15_7) AppleWebKit…"), which a non-greedy `\(...\)` would stop on.
    m = re.search(r"USER_AGENT\s*=\s*\((.*?)^\s*\)", txt, re.S | re.M) or re.search(
        r"""USER_AGENT\s*=\s*(['\"].*?['\"])""", txt
    )
    if not m:
        return "*"
    parts = re.findall(r"""['\"]([^'\"]*)['\"]""", m.group(1))
    return " ".join(parts).strip() or "*"


def spider_user_agent(project, domain):
    """The UA our crawler sends for this domain — the spider's own USER_AGENT setting if it
    overrides, else the project-wide one. Robots is judged for THIS agent, not a guess.
    """
    path = _spider_cfg_path(project, domain)
    try:
        ua = (
            (json.load(open(path)).get("settings") or {}).get("USER_AGENT")
            if path
            else None
        )
        if ua:
            return ua
    except (OSError, json.JSONDecodeError):
        pass
    return _global_user_agent()


# ---- crawl-capture witness readers -----------------------------------------
# The spiders now capture /robots.txt + /llms.txt at CRAWL time (through their own
# downloader, same CF/proxy/TLS as the crawl) into data/<proj>/<spider>/crawls/, and the
# legal/terms pages they crawl land as content rows in crawls/*.jsonl. These are the
# AUTHORITATIVE witness; compliance's own fetch is the independent cross-check.


def spider_dir_for_domain(project, domain):
    """The spider's data folder that crawls `domain` (its crawls/ holds the crawl-captured
    robots/llms + the JSONL), or None. Derived from the spider's final_spider.json so it
    works even when the folder name isn't the domain slug (e.g. noaa_gov_ncei)."""
    cfg = _spider_cfg_path(project, domain)
    if cfg:
        return os.path.dirname(
            os.path.dirname(cfg)
        )  # …/<spider>/analysis/x → …/<spider>
    direct = os.path.join(DATA_DIR, project, slug(domain))
    return direct if os.path.isdir(direct) else None


def _stamp_key(fname, stem):
    """Sort key from a crawl-captured filename like robots_30062025.txt → date (newest wins);
    files without a valid DDMMYYYY stamp sort oldest."""
    m = re.search(rf"{re.escape(stem)}_(\d{{8}})\.", fname)
    if not m:
        return datetime.date.min
    try:
        return datetime.datetime.strptime(m.group(1), "%d%m%Y").date()
    except ValueError:
        return datetime.date.min


@lru_cache(maxsize=256)
def latest_crawl_file(spider_dir, stem):
    """(path, text, date) for the newest crawls/<stem>_<DDMMYYYY>.txt the spider captured
    (`stem` ∈ {'robots','llms'}), or None. The crawl-capture witness for that file.
    Per-process lru_cache: cross_check hits this once from compliance_summary and once
    from build_report_data per domain; the file can't change mid-run."""
    if not spider_dir:
        return None
    files = glob.glob(os.path.join(spider_dir, "crawls", f"{stem}_*.txt"))
    files = [
        f for f in files if _stamp_key(os.path.basename(f), stem) != datetime.date.min
    ]
    if not files:
        return None
    newest = max(files, key=lambda f: _stamp_key(os.path.basename(f), stem))
    try:
        with open(newest, encoding="utf-8", errors="replace") as fh:
            return newest, fh.read(), _stamp_key(os.path.basename(newest), stem)
    except OSError:
        return None


@lru_cache(maxsize=256)
def crawl_captured_legal_urls(spider_dir):
    """(legal_page_urls, pdf_urls) the SPIDER actually captured — legal/terms pages it
    scraped (row URL path matches a LEGAL_WORD) plus any article-linked PDFs it recorded
    (pdf_urls / external_pdf_urls). URL-only scan, so it stays cheap on large JSONL.
    Per-process lru_cache (consumers treat the sets as read-only): this is the full-JSONL
    pass cross_check repeats per domain across compliance_summary and build_report_data.
    """
    legal, pdfs = set(), set()
    if not spider_dir:
        return legal, pdfs
    for jf in glob.glob(os.path.join(spider_dir, "crawls", "*.jsonl")):
        try:
            with open(jf, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    u = rec.get("url") or ""
                    if u:
                        segs = [s for s in urlparse(u).path.lower().split("/") if s]
                        if any(any(w in seg for w in LEGAL_WORDS) for seg in segs):
                            legal.add(u.split("?")[0].rstrip("/"))
                    meta = (
                        rec.get("metadata")
                        if isinstance(rec.get("metadata"), dict)
                        else {}
                    )
                    for key in ("pdf_urls", "external_pdf_urls"):
                        vals = rec.get(key) or meta.get(key) or []
                        if isinstance(vals, str):
                            vals = [vals]
                        for p in vals:
                            if isinstance(p, str) and p:
                                pdfs.add(p.split("?")[0].rstrip("/"))
        except OSError:
            continue
    return legal, pdfs


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def existing_snapshots(org_base):
    """Dated snapshot dirs (YYYY-MM-DD) that hold a compliance.json, oldest first."""
    if not os.path.isdir(org_base):
        return []
    return sorted(
        d
        for d in os.listdir(org_base)
        if DATE_RE.match(d)
        and os.path.exists(os.path.join(org_base, d, "compliance.json"))
    )


# ---- capture-failed marker (unreachable domains) ---------------------------
# A domain we tried but couldn't reach (neither robots.txt nor homepage) gets a marker so the
# audit's default 'capture only NEW domains' mode never retries it on every run — it's left
# for a human (likely needs --browser / a working proxy). _capture_failed.json is not a
# YYYY-MM-DD dir, so existing_snapshots() ignores it.


def _failed_marker_path(project, domain):
    return os.path.join(org_compliance_dir(project, domain), "_capture_failed.json")


def has_capture_failed(project, domain):
    """True if the most recent capture ATTEMPT failed (marker present; cleared by the
    next successful capture). May coexist with OLDER successful snapshots when a
    --refresh attempt fails — a failed refresh keeps history, it doesn't erase it."""
    return os.path.exists(_failed_marker_path(project, domain))


def mark_capture_failed(project, domain, reason):
    """Record an unreachable domain + print a big fat error. Keeps first_failed across runs."""
    path = _failed_marker_path(project, domain)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    today = datetime.date.today().isoformat()
    first = today
    try:
        first = json.load(open(path)).get("first_failed", today)
    except (OSError, json.JSONDecodeError):
        pass
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(
            {
                "domain": norm_domain(domain),
                "first_failed": first,
                "last_attempt": today,
                "reason": reason,
            },
            fh,
            indent=2,
        )
        fh.write("\n")
    os.replace(tmp, path)
    print("\n" + "!" * 72)
    print(f"  ‼  COMPLIANCE CAPTURE FAILED — {domain}")
    print(f"     {reason}")
    print(
        "     Skipped on future audits until fixed; rerun with "
        "`./scrapai audit --refresh` to retry."
    )
    print("!" * 72 + "\n")


def clear_capture_failed(project, domain):
    """Remove the failure marker after a successful capture."""
    try:
        os.remove(_failed_marker_path(project, domain))
    except OSError:
        pass


def project_targets(project):
    """{domain: ts_or_None} read live from each spider's final_spider.json. A Wayback
    spider (allowed_domains = web.archive.org) maps the ORIGINAL domain to the archive
    timestamp from its start_urls (so it's checked via the snapshot, the live site being
    dead); every other domain maps to None (checked live)."""
    targets = {}
    for f in glob.glob(
        os.path.join(DATA_DIR, project, "*", "analysis", "final_spider.json")
    ):
        try:
            cfg = json.load(open(f))
        except (json.JSONDecodeError, OSError):
            continue
        ad = [norm_domain(d) for d in cfg.get("allowed_domains", [])]
        if "web.archive.org" in ad:
            for su in cfg.get("start_urls", []):
                inner = unwrap_wayback(su)
                if inner and inner != "web.archive.org":
                    targets.setdefault(inner, wayback_ts(su))
            continue
        for d in ad:
            if d:
                targets.setdefault(d, None)
    return targets


def project_domains(project):
    """Just the domain names for coverage listing (drops the Wayback timestamps)."""
    return list(project_targets(project))


def latest_snapshot(org_base):
    snaps = existing_snapshots(org_base)
    if not snaps:
        return None, None
    try:
        return snaps[-1], json.load(
            open(os.path.join(org_base, snaps[-1], "compliance.json"))
        )
    except (OSError, json.JSONDecodeError):
        return snaps[-1], None


project_exists = _env.project_exists
