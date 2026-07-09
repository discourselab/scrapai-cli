"""Sitemap fetch/discovery/recursion, the on-disk sitemap cache, and rule-matching
of sitemap URLs against a spider's allow/deny patterns."""

import glob
import os
import re
import shutil
import subprocess

from core.quality import _env

LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
SITEMAP_DIRECTIVE = re.compile(r"(?im)^\s*sitemap:\s*(\S+)")


def discover_sitemap(
    host, project, spider, cache_dir, state, browser=False, browser_retry=True
):
    """For a spider without USE_SITEMAP, find a sitemap entry URL via robots.txt
    (authoritative) then /sitemap.xml. Returns a list of entry URLs (or []).

    Sites that block a lightweight fetch (Cloudflare, or a TLS-fingerprint block
    that the spider works around with curl_cffi) return nothing to a plain probe,
    which used to make discovery conclude `no sitemap` even though one exists. So
    a probe that comes back empty is retried with `--browser` (mirroring
    fetch_spider_sitemaps' escalation) unless `browser_retry` is off. `browser`
    True (set for CLOUDFLARE/BROWSER/CURL_CFFI spiders) goes straight to browser."""
    if not host:
        return []
    base = "https://" + host

    def probe(url, suffix, needs_loc):
        # `needs_loc` False (robots.txt) → escalate only when the fetch came back
        # empty; True (sitemap.xml) → also escalate when it lacks <loc> (a blocked
        # fetch can return a challenge/error page with no locs).
        out = os.path.join(cache_dir, spider + suffix)
        text = fetch(url, out, project, browser, state)
        blocked = not text or (needs_loc and not LOC_RE.search(text))
        if blocked and browser_retry and not browser:
            text = fetch(url, out, project, True, state)  # blocked plain → browser
        return text

    robots = probe(base + "/robots.txt", "_robots", needs_loc=False)
    found = SITEMAP_DIRECTIVE.findall(robots or "")
    if found:
        return found
    sm = probe(base + "/sitemap.xml", "_smprobe", needs_loc=True)
    if sm and LOC_RE.search(sm):
        return [base + "/sitemap.xml"]
    return []


# --------------------------------------------------------------------------- fetch
def fetch(url, outdir, project, browser, state):
    """Fetch `url` via `./scrapai inspect` into `outdir`, returning the HTML text.

    Write-to-temp + validate + swap: the inspector creates its output dir BEFORE
    fetching, so writing straight into `outdir` left two traps — a failed fetch
    still created the dir (which has_cache() then counted as "resolved", so default
    mode never retried), and a leftover page.html from a previous run could be
    served as if this fetch had produced it. Fetching into a sibling `.tmp` dir and
    swapping only on success means failure leaves NOTHING and the returned text is
    always this run's bytes. `.tmp` never matches spider_cache_dirs' ^spider_\\d+$,
    so a crash mid-swap can't count as cache either. A failed RE-fetch of an
    existing dir keeps the previous good content (refresh keeps history on failure).
    """
    if state["global"] >= state["global_cap"]:
        return None
    state["global"] += 1
    tmp = outdir + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    # --output-dir as ABSPATH: with a relative DATA_DIR the child (cwd-pinned to the
    # repo root) and this process could otherwise resolve the path differently.
    cmd = [
        _env.SCRAPAI,
        "inspect",
        url,
        "--project",
        project,
        "--output-dir",
        os.path.abspath(tmp),
        "--log-level",
        "error",
    ]
    if browser:
        cmd.append("--browser")
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=180, text=True, cwd=str(_env.project_root)
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    fp = os.path.join(tmp, "page.html")
    if not os.path.exists(fp) or os.path.getsize(fp) == 0:
        shutil.rmtree(tmp, ignore_errors=True)  # failure leaves NO cache dir
        return None
    with open(fp, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    shutil.rmtree(outdir, ignore_errors=True)
    os.replace(tmp, outdir)
    return text


def parse_sitemap(text):
    if not text:
        return False, []
    locs = [loc.replace("&amp;", "&").strip() for loc in LOC_RE.findall(text)]
    return ("<sitemapindex" in text.lower()), locs


# sub-sitemaps that list taxonomy/archive pages, not content — excluded from the
# coverage denominator (they're listing pages, not articles).
TAXONOMY_HINTS = (
    "category-sitemap",
    "post_tag-sitemap",
    "product_tag-sitemap",
    "product_cat-sitemap",
    "tag-sitemap",
    "author-sitemap",
    "wp-sitemap-taxonomies",
    "wp-sitemap-users",
)


def is_taxonomy_sitemap(url):
    u = url.lower()
    return any(h in u for h in TAXONOMY_HINTS)


# paginated sitemaps that aren't <sitemapindex>es: SilverStripe `.../SiteTree/1`
# (trailing /N) and `?page=N`. We walk N=2,3,… until a page comes back empty.
_PAGE_PATH = re.compile(r"^(.*/)(\d+)$")
_PAGE_QS = re.compile(r"^(.*[?&]page=)(\d+)(.*)$", re.I)


def next_sitemap_page(url):
    """Next page of a paginated sitemap URL, or None if it isn't paginated."""
    m = _PAGE_QS.match(url)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}{m.group(3)}"
    m = _PAGE_PATH.match(url)
    if m and "." not in m.group(2):  # trailing /N segment (no file extension)
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    return None


def fetch_spider_sitemaps(spider, sp, project, cache_dir, state, browser_retry):
    """Recurse <sitemapindex> children AND follow paginated sitemaps from
    start_urls; cache files; return notes."""
    # Prune the previous generation of this spider's cache before re-fetching:
    # indices restart at 0 every run, so leftovers from a run with MORE
    # sub-sitemaps (or a different ordering) would otherwise be unioned into
    # collect_pages() as stale locs. Only reached when the caller decided to
    # fetch (should_fetch) — cached/--no-fetch paths never prune.
    for d in spider_cache_dirs(spider, cache_dir):
        shutil.rmtree(d, ignore_errors=True)
    notes = []
    browser = sp["browser"]
    queue = list(sp["start_urls"])
    seen = set()
    page_sigs = set()  # guard against servers that ignore the page param
    idx = 0
    fetches = 0
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if fetches >= state["per_cap"]:
            notes.append(f"capped at {state['per_cap']} fetches; partial")
            break
        outdir = os.path.join(cache_dir, f"{spider}_{idx}")
        idx += 1
        fetches += 1
        text = fetch(url, outdir, project, browser, state)
        if (not text or not LOC_RE.search(text)) and browser_retry and not browser:
            text = fetch(url, outdir, project, True, state)  # CF/JS retry
        is_index, locs = parse_sitemap(text)
        if not locs:
            notes.append(f"0 locs: {url}")
            continue
        if is_index:
            skipped_tax = []
            for loc in locs:
                if is_taxonomy_sitemap(loc):
                    skipped_tax.append(loc.rstrip("/").rsplit("/", 1)[-1])
                    continue  # taxonomy/archive sitemap — not content
                if loc not in seen:
                    queue.append(loc)
            if skipped_tax:
                # list names (not just a count) so a wrongly-skipped content
                # sub-sitemap is visible and auditable
                notes.append(
                    "skipped taxonomy: "
                    + ", ".join(skipped_tax[:6])
                    + ("…" if len(skipped_tax) > 6 else "")
                )
        else:
            # urlset: if this URL is paginated, walk to the next page until empty
            nxt = next_sitemap_page(url)
            sig = (len(locs), locs[0], locs[-1])
            if nxt and nxt not in seen and sig not in page_sigs:
                page_sigs.add(sig)  # stop if a later page repeats this content
                queue.append(nxt)
    return fetches, "; ".join(notes[:3])


# --------------------------------------------------------------------------- match
def spider_cache_dirs(spider, cache_dir):
    pat = re.compile(r"^" + re.escape(spider) + r"_\d+$")
    return [
        d
        for d in glob.glob(os.path.join(cache_dir, "*"))
        if pat.match(os.path.basename(d))
    ]


def collect_pages(spider, cache_dir):
    """Page URLs = locs from cached urlset files (skip index files)."""
    pages = set()
    for d in spider_cache_dirs(spider, cache_dir):
        fp = os.path.join(d, "page.html")
        # zero-length guard: legacy caches (pre temp+swap fetch) may hold empty
        # files from failed fetches — never let them count as a fetched sitemap
        if not os.path.exists(fp) or os.path.getsize(fp) == 0:
            continue
        with open(fp, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if "<sitemapindex" in text.lower():
            continue
        for loc in LOC_RE.findall(text):
            pages.add(loc.replace("&amp;", "&").strip())
    return pages


def match_all_flag(sp):
    """True if the spider follows every sitemap URL (no effective allow filter)."""
    if sp["n_rules"] == 0:
        return True
    # any rule with no allow_patterns matches everything
    return any(not pats for pats in sp["rules"])


def _compile(patterns):
    out = []
    for p in patterns or []:
        try:
            out.append(re.compile(p))
        except re.error:
            pass
    return out


def compile_allow(sp):
    """Compiled allow-regexes for a spider, or None when it matches everything."""
    if match_all_flag(sp):
        return None
    compiled = []
    for pats in sp["rules"]:
        compiled.extend(_compile(pats))
    return compiled or None  # no usable patterns → treat as match-all


def compile_deny(sp):
    """Compiled deny-regexes (e.g. PDFs) — these URLs are excluded from coverage."""
    return _compile(sp.get("deny"))


def matches_rules(url, allow_c, deny_c=()):
    """True if url matches allow-rules (None = match all) AND no deny-rule."""
    if any(c.search(url) for c in deny_c):
        return False
    return allow_c is None or any(c.search(url) for c in allow_c)


def eligible_urls(sp, pages):
    """Sitemap page URLs the spider would scrape: match allow, not deny."""
    allow_c, deny_c = compile_allow(sp), compile_deny(sp)
    return [u for u in pages if matches_rules(u, allow_c, deny_c)]
