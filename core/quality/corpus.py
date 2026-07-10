"""Shared crawl-output primitives — the ONE home for the JSONL corpus helpers.

`crawl_audit` (true-dupe/version counting) and `dedupe` (the mutating consolidation)
must agree byte-for-byte on what counts as "the same record": both import VOLATILE
and fingerprint() from here, so they can never drift apart. The audit's per-file
scan machinery and its counts-cache live here too.

Two scanners coexist deliberately:
- scan_file() / scan_urls() give noURL records a `__noURL__<filename>_<lineno>`
  placeholder (per-file counter) — deterministic, so cached results equal fresh scans.
- dedupe keeps its own line-preserving scanner with a CROSS-file counter; unifying
  the two would change dedupe's keys (and hence what it collapses), so it only
  shares VOLATILE + fingerprint.
"""

import glob
import hashlib
import json
import os
import statistics
from collections import Counter
from urllib.parse import urlparse

from core.quality._env import DATA_DIR

# Excluded from the content fingerprint: per-run bookkeeping that changes between
# crawls without the page changing (timestamps, and spider_id/source which flip
# when a spider is re-imported).
VOLATILE = {
    "scraped_at",
    "extracted_at",
    "scraped",
    "spider_id",
    "spider_name",
    "source",
}


def fingerprint(rec):
    """Hash the record minus per-run bookkeeping. Identical re-scrapes of an
    unchanged page hash the same (even across re-imports); any real
    content/field change differs."""
    payload = {k: v for k, v in rec.items() if k not in VOLATILE}
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def is_pdf_row(rec):
    """True for the framework's PDF rows — URL-only link records (PDF_MODE=
    links_only) and extract-mode text rows alike: metadata_json (dict, or a JSON
    string in re-serialised corpora) carries content_type == "pdf". The marker IS
    the row model; a marker-less .pdf-suffixed URL is an ordinary row."""
    md = rec.get("metadata_json")
    if isinstance(md, str):
        if "content_type" not in md:
            return False
        try:
            md = json.loads(md)
        except json.JSONDecodeError:
            return False
    return isinstance(md, dict) and md.get("content_type") == "pdf"


def url_host(u):
    """Hostname of a URL, lowercased, www-stripped — THE hostname rule every
    quality lens shares (same-org can never mean two different things)."""
    try:
        net = urlparse(str(u or "")).netloc.lower().split(":")[0]
    except ValueError:
        return ""
    return net[4:] if net.startswith("www.") else net


def host_in_domains(host, domains):
    """Dot-boundary suffix match of `host` against a spider's own domains
    (www-stripped both sides): unep.org also owns wedocs.unep.org."""
    h = (host or "").lower()
    h = h[4:] if h.startswith("www.") else h
    if not h:
        return False
    for d in domains or []:
        d = str(d).lower()
        d = d[4:] if d.startswith("www.") else d
        if d and (h == d or h.endswith("." + d)):
            return True
    return False


def median(vals):
    """Median of a list of numbers (0 if empty). Used for content-depth: robust to
    the odd very-long/very-short page, so a low median means *typically* thin."""
    return statistics.median(vals) if vals else 0


def scan_file(path):
    """Scan one crawls/*.jsonl -> partial aggregates, pure over the file's bytes.

    The expensive step (json.loads + md5 fingerprint of every record) lives here so
    scan_project() can cache it per file: a finished crawl's date-named JSONL never
    changes, so its partial is reused across runs. noURL records get a
    filename+lineno placeholder, keeping them unique across files AND deterministic
    (so the cached result is identical to a fresh scan).
    """
    fname = os.path.basename(path)
    urls, uc, content, title, pdf = set(), set(), set(), set(), set()
    clen = {}  # url -> content length (for the median content-depth signal)
    recs = 0  # successfully-parsed records (rows written to disk)
    n = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # noURL records get a unique placeholder so they count as
            # unique (not duplicates); real repeated URLs do not.
            u = rec.get("url") or f"__noURL__{fname}_{n}"
            urls.add(u)
            uc.add((u, fingerprint(rec)))
            recs += 1
            if is_pdf_row(rec):
                # PDF harvest rows: counted separately, and NEVER into the
                # content/clen signals — extraction quality is judged over HTML
                # rows only (extract-mode PDF text must not inflate content%).
                pdf.add(u)
                continue
            if isinstance(rec.get("content"), str) and rec["content"].strip():
                content.add(u)
                clen[u] = len(rec["content"].strip())  # keep last seen
            if isinstance(rec.get("title"), str) and rec["title"].strip():
                title.add(u)
    return {
        "urls": urls,
        "uc": uc,
        "content": content,
        "title": title,
        "clen": clen,
        "recs": recs,
        "pdf": pdf,
    }


def _scan_cache_path(cache_dir, spider):
    return os.path.join(cache_dir, spider + ".json")


def load_scan_cache(cache_dir, spider):
    """{filename: cache-entry} for a spider, or {} if absent/corrupt."""
    try:
        with open(_scan_cache_path(cache_dir, spider), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_scan_cache(cache_dir, spider, cache):
    os.makedirs(cache_dir, exist_ok=True)
    path = _scan_cache_path(cache_dir, spider)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cache, fh)
    os.replace(tmp, path)  # atomic; never leaves a half-written cache


def file_counts(path):
    """Cheap, mergeless summary of one file for the cache: counts + the list of
    content lengths (for the median). Deliberately DROPS the URL strings — the bulky
    part — which only the rare sitemap-intersection path needs (rebuilt lazily by
    scraped_urlset). Built from a full scan_file so the dedup/fingerprint counts
    are exact."""
    p = scan_file(path)
    pdf_hosts = dict(Counter(url_host(u) for u in p["pdf"]))
    return {
        "unique": len(p["urls"]),
        "uc": len(p["uc"]),
        "content": len(p["content"]),
        "title": len(p["title"]),
        "recs": p["recs"],
        "clen_vals": sorted(p["clen"].values()),
        # pdf harvest: unique-url count + per-host histogram. Both are pure
        # over the file's bytes, so cacheable; the own/external SPLIT is NOT
        # (spider domains can change without the file changing) — it is
        # computed downstream at scoring/report time.
        "pdf": len(p["pdf"]),
        "pdf_hosts": pdf_hosts,
    }


def scan_urls(path):
    """Just the scraped-URL set for one file — no fingerprint/content work. Used to
    rebuild urlset on demand (see scraped_urlset)."""
    fname = os.path.basename(path)
    urls, n = set(), 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            urls.add(rec.get("url") or f"__noURL__{fname}_{n}")
    return urls


def scraped_urlset(c):
    """Raw scraped-URL set for a spider, materialised lazily. scan_project keeps only
    counts (so the GBs of URL strings never touch the common path); the few spiders
    whose coverage is verified by set-intersection against a FETCHED sitemap rebuild
    it here by re-reading their crawl files. Multi-file spiders already carry a
    materialised `urlset`, so they skip the re-read."""
    s = c.get("urlset")
    if s is not None:
        return s
    urls = set()
    for f in c.get("_files", []):
        urls |= scan_urls(f)
    return urls


def merge_partials(partials):
    """Union of per-file scan_file partials (multi-file spiders only). Keeps the
    materialised urlset since we already built it."""
    urls, uc, content, title, pdf = set(), set(), set(), set(), set()
    clen, recs = {}, 0
    for p in partials:
        urls |= p["urls"]
        uc |= p["uc"]
        content |= p["content"]
        title |= p["title"]
        pdf |= p["pdf"]
        clen.update(p["clen"])  # keep last seen (matches single-pass behavior)
        recs += p["recs"]
    pdf_hosts = dict(Counter(url_host(u) for u in pdf))
    return {
        "unique": len(urls),
        "uc": len(uc),
        "content": len(content),
        "title": len(title),
        "rows": recs,
        "content_med": round(median(clen.values())),
        "urlset": urls,
        "pdf": len(pdf),
        "pdf_hosts": pdf_hosts,
    }


def scan_project(project, use_cache=True):
    """{spider: {unique, uc, content, title, rows, files, content_med, ...}} from
    crawls/*.jsonl.

    `rows`   = parsed records on disk          `unique` = distinct URLs
    `uc`     = distinct (url, content-fingerprint) pairs
    -> true dupes = rows - uc   (identical re-scrapes; default dedupe removes)
    -> versions   = uc - unique (same URL, changed content; default dedupe keeps)
    `.bak`/`.superseded` files don't match `*.jsonl`, so they're excluded.

    The per-file scan (json-decode + md5 of every record over GBs of output)
    dominates runtime, so each single-file spider's COUNTS are cached under
    _audit/scan_cache/<spider>.json keyed by (size, mtime): an unchanged file
    reloads instantly from the small counts blob, only changed/new files are
    re-scanned. The bulky URL set is intentionally NOT cached — it's rebuilt lazily
    by scraped_urlset for the handful of spiders whose coverage is checked against a
    fetched sitemap. `use_cache=False` forces a fresh scan and rewrites the cache.
    """
    root = os.path.join(DATA_DIR, project)
    scan_cache_dir = os.path.join(root, "_audit", "scan_cache")
    out = {}
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        if not os.path.isdir(d):
            continue
        spider = os.path.basename(d)
        files = sorted(glob.glob(os.path.join(d, "crawls", "*.jsonl")))
        newest = max((os.path.getmtime(f) for f in files), default=None)
        if not files:
            out[spider] = {
                "unique": 0,
                "uc": 0,
                "content": 0,
                "title": 0,
                "rows": 0,
                "files": 0,
                "content_med": 0,
                "newest": newest,
                "urlset": set(),
                "_files": [],
                "pdf": 0,
                "pdf_hosts": {},
            }
            continue

        if len(files) == 1:
            # Common case: counts from cache when (size, mtime) match; urlset lazy.
            f = files[0]
            fname = os.path.basename(f)
            st = os.stat(f)
            cache = load_scan_cache(scan_cache_dir, spider) if use_cache else {}
            ent = cache.get(fname)
            # "pdf_hosts" is the current-format sentinel: entries from before the
            # pdf-aware scan re-scan exactly once, then re-cache.
            if not (
                ent
                and "clen_vals" in ent
                and "pdf_hosts" in ent
                and ent.get("size") == st.st_size
                and ent.get("mtime") == st.st_mtime
            ):
                ent = file_counts(f)  # changed/new/missing -> re-scan
                ent["size"], ent["mtime"] = st.st_size, st.st_mtime
                save_scan_cache(
                    scan_cache_dir, spider, {fname: ent}
                )  # --no-cache still rewrites
            summary = {
                "unique": ent["unique"],
                "uc": ent["uc"],
                "content": ent["content"],
                "title": ent["title"],
                "rows": ent["recs"],
                "content_med": round(median(ent["clen_vals"])),
                "pdf": ent["pdf"],
                "pdf_hosts": ent["pdf_hosts"],
            }
        else:
            # Rare: multiple crawl files. Counts need cross-file dedup, so the
            # single-file counts-cache doesn't apply — scan all and union.
            summary = merge_partials([scan_file(f) for f in files])

        summary.update(files=len(files), newest=newest, _files=files)
        out[spider] = summary
    return out
