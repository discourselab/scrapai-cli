"""Sitemap fetch/discovery/recursion, the on-disk sitemap cache, and rule-matching
of sitemap URLs against a spider's allow/deny patterns."""

import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
from urllib.parse import urlparse

from core.quality import _env

LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.I | re.S)
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_SITEMAP_ROOT = re.compile(r"<(sitemapindex|urlset)[\s>/]", re.I)
_FEED_ROOT = re.compile(r"<(rss|feed|rdf:rdf)[\s>/]", re.I)
SITEMAP_DIRECTIVE = re.compile(r"(?im)^\s*sitemap:\s*(\S+)")

# Media URLs sometimes appear as plain <loc>s (WordPress image/attachment
# sitemaps): they're media, not content pages, so they must not inflate the
# coverage denominator. (<image:loc> tags aren't matched by LOC_RE at all; this
# catches media that shows up as a plain <loc>.)
_MEDIA_EXT = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tif",
    ".tiff",
    ".ico",
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".wmv",
    ".webm",
    ".mp3",
    ".wav",
    ".ogg",
)


def is_media_loc(url):
    u = url.lower().split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return u.endswith(_MEDIA_EXT)


def _looks_like_html(text):
    """robots.txt is text/plain; an HTML body back is a Cloudflare/challenge or
    soft-404 page, not robots — worth a browser retry before trusting it (a
    non-empty challenge page otherwise sails through as a robots.txt with no
    Sitemap: directive, masking a real sitemap)."""
    head = (text or "")[:4000].lower()
    return "<html" in head or "<!doctype html" in head


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
    return _discover(host, project, spider, cache_dir, state, browser, browser_retry)[0]


def _discover(
    host,
    project,
    spider,
    cache_dir,
    state,
    browser,
    browser_retry,
    budget=None,
    robots_known=False,
    sitemap_text=None,
):
    """discover_sitemap's probes → (found, answered, sitemap_text). `answered` is
    True when the result is a fact rather than a failure: robots.txt came back
    as robots (not empty, not an HTML page) — or `robots_known`: it is on disk
    and lists no sitemap, so it isn't fetched again — and /sitemap.xml came
    back with a body. `sitemap_text` is an already-cached /sitemap.xml body
    (the probe is then skipped). Every probe goes through fetch_once, so a URL
    already fetched this run is never fetched again."""
    base = "https://" + host

    def probe(url, suffix, needs_loc):
        # `needs_loc` True (sitemap.xml) → escalate when empty OR it lacks <loc>
        # (a blocked fetch returns a challenge/error page with no locs).
        # `needs_loc` False (robots.txt) → escalate when empty OR the body is HTML:
        # robots.txt is text/plain, so an HTML body is a Cloudflare/challenge or
        # soft-404 page, not robots — a non-empty CF page used to sail through as
        # a valid robots.txt with no Sitemap: directive, masking a real sitemap.
        def usable(text):
            if needs_loc:
                return _has_locs(text)
            return bool(text) and not _looks_like_html(text)

        out = os.path.join(cache_dir, spider + suffix)
        return fetch_once(
            url, out, project, browser, state, browser_retry, usable, budget
        )

    robots_ok = robots_known
    if not robots_known:
        robots = probe(base + "/robots.txt", "_robots", needs_loc=False)
        found = SITEMAP_DIRECTIVE.findall(robots or "")
        if found:
            return found, True, None
        robots_ok = bool(robots) and not _looks_like_html(robots)
    sm = sitemap_text
    if sm is None:
        sm = probe(base + "/sitemap.xml", "_smprobe", needs_loc=True)
    if _has_locs(sm):
        return [base + "/sitemap.xml"], True, sm
    return [], robots_ok and bool(sm), sm


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


URL_FILE = "url.txt"  # beside a fetched page.html: the URL it came from


def read_page(path):
    """A cached page's text, or None when it is missing or empty."""
    try:
        if path and os.path.getsize(path) > 0:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
    except OSError:
        pass
    return None


def fetch_once(url, outdir, project, browser, state, retry, usable, budget=None):
    """fetch() plus the browser retry, at most ONCE per URL per audit run: a
    URL already fetched this run (by any spider or step) is served from that
    copy, copied into `outdir` so the caller's cache layout still holds, and a
    URL whose fetch failed this run isn't tried again. `usable(text)` False
    triggers the browser retry. `budget` is the {global, global_cap} the fetch
    is charged to (default `state`); the per-run record lives in `state`."""
    budget = state if budget is None else budget
    done = state.setdefault("fetched", {})
    if url in done:
        src = done[url]
        if src is None:
            return None
        text = read_page(src)
        if text is not None:
            dst = os.path.join(outdir, "page.html")
            if os.path.abspath(src) != os.path.abspath(dst):
                shutil.rmtree(outdir, ignore_errors=True)
                os.makedirs(outdir, exist_ok=True)
                shutil.copyfile(src, dst)
            return text
        # the earlier copy is gone (pruned): nothing on disk to reuse
    text = fetch(url, outdir, project, browser, budget)
    if not usable(text) and retry and not browser:
        text = fetch(url, outdir, project, True, budget)  # blocked plain → browser
    if text or budget["global"] < budget["global_cap"]:
        # a miss caused only by an exhausted budget isn't a site answer
        done[url] = os.path.join(outdir, "page.html") if text else None
    return text


def loc_url(raw):
    """A <loc> body as its URL: a CDATA section is unwrapped as-is (All in One
    SEO writes `<loc><![CDATA[https://...]]></loc>`; CDATA holds no entities),
    anything else has `&amp;` decoded. The ONE place loc text is read."""
    s = raw.strip()
    m = _CDATA.fullmatch(s)
    return m.group(1).strip() if m else s.replace("&amp;", "&")


def sitemap_kind(text):
    """'index' / 'urlset' for a sitemap document, 'other' for a document that
    is plainly something else — an RSS/Atom feed, which robots.txt sometimes
    advertises on a `Sitemap:` line — or None when there is no telling (no
    body, an HTML page: a challenge or error page, never an answer)."""
    if not text:
        return None
    m = _SITEMAP_ROOT.search(text)
    if m:
        return "index" if m.group(1).lower() == "sitemapindex" else "urlset"
    if _looks_like_html(text):
        return None
    return "other" if _FEED_ROOT.search(text[:4000]) else None


def parse_sitemap(text):
    """(is_index, locs) for a sitemap document; (False, []) for anything that
    isn't one (a feed's <link>s, or an HTML page, are never sitemap URLs)."""
    kind = sitemap_kind(text)
    if kind not in ("index", "urlset"):
        return False, []
    return kind == "index", [loc_url(loc) for loc in LOC_RE.findall(text)]


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


def _has_locs(text):
    """A usable sitemap answer: a sitemap document with at least one <loc>."""
    return bool(parse_sitemap(text)[1])


def _answered(text):
    """No browser retry: a sitemap came back, or a document that plainly isn't
    one (a feed) — retrying it can't turn it into a sitemap."""
    return _has_locs(text) or sitemap_kind(text) == "other"


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
        text = fetch_once(
            url, outdir, project, browser, state, browser_retry, _answered
        )  # CF/JS retry inside
        if text:
            with open(os.path.join(outdir, URL_FILE), "w") as fh:
                fh.write(url)  # lets the sitemap listing reuse this copy
        is_index, locs = parse_sitemap(text)
        if sitemap_kind(text) == "other":
            notes.append(f"not a sitemap: {url}")  # e.g. an RSS feed
            continue
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


# -------------------------------------------------------- root sitemap indexes
# The given/total sitemap listing needs the children of each sitemap the site
# declares in robots.txt. Politeness first — nothing already on disk is fetched
# again, and nothing is fetched twice in one run:
#   - a declared sitemap is read from disk first: its host manifest, else the
#     copy a spider's own sitemap fetch cached (sitemap_cache/<spider>_N), else
#     the copy fetched earlier in this run (fetch_once). Only when none exists
#     is it fetched — AT MOST ONCE per host, ever — and cached under
#     sitemap_cache/_host/<host>/ as a manifest of its own <loc>s (children are
#     never fetched).
#   - a failed fetch leaves a dated marker and is never retried except under
#     --fetch-all, which also refreshes cached manifests (once per run:
#     `state["index_seen"]` stops a second spider on the same host from
#     re-fetching; a URL the spider's own fetch already got this run is reused).
#   - these fetches have their own small budget (INDEX_FETCH_CAP), so they can
#     never exhaust the coverage fetches' --global-cap or trip sitemap-cap-hit.
# `_host` can never match a spider's ^<spider>_\d+$ cache dirs, so none of this
# counts as spider cache.
INDEX_FETCH_CAP = 100


def index_budget(state):
    """The listing's own fetch budget, kept inside `state` for the run."""
    return state.setdefault(
        "index_budget", {"global": 0, "global_cap": INDEX_FETCH_CAP}
    )


def host_cache_dir(cache_dir, host):
    return os.path.join(cache_dir, "_host", (host or "").lower() or "_nohost")


def _index_dir(cache_dir, url):
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    host_dir = host_cache_dir(cache_dir, urlparse(url).netloc)
    return os.path.join(host_dir, "sm_" + key)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _budget_left(state):
    return state["global"] < state["global_cap"]


def spider_cached_urls(spider, cache_dir):
    """{url: page.html path} for what a spider's own sitemap fetch cached under
    sitemap_cache/<spider>_N — a pure disk read. Only dirs that name their URL
    (url.txt, written since the listing existed) count: an older cache's dirs
    can't be tied to a URL reliably (the spider's start_urls may have changed
    since, and the fetch order changed with them), and a wrongly attributed
    index would misreport the site's sitemaps — so such a declared sitemap is
    fetched once into the host cache instead."""
    out = {}
    for d in spider_cache_dirs(spider, cache_dir):
        page = os.path.join(d, "page.html")
        named = read_page(os.path.join(d, URL_FILE))
        if named and read_page(page) is not None:
            out.setdefault(named.strip(), page)
    return out


def _save_manifest(url, cache_dir, text):
    """Record a fetched sitemap's own <loc>s as its manifest (clearing any
    failure marker) and return the manifest. A declared URL whose content is
    plainly not a sitemap (an RSS feed on a `Sitemap:` line) is recorded as
    not_sitemap, so it is skipped — never counted — without another fetch."""
    d = _index_dir(cache_dir, url)
    is_index, locs = parse_sitemap(text)
    manifest = {
        "url": url,
        "is_index": is_index,
        "children": locs if is_index else [],
        "fetched": datetime.date.today().isoformat(),
    }
    if not is_index:
        manifest["pages"] = sum(1 for u in locs if not is_media_loc(u))
    if sitemap_kind(text) == "other":
        manifest["not_sitemap"] = True
    _write_json(os.path.join(d, "manifest.json"), manifest)
    try:
        os.remove(d + ".failed.json")
    except OSError:
        pass
    return manifest


def index_manifest(
    url,
    project,
    cache_dir,
    state,
    mode,
    browser,
    retry,
    on_disk=None,
    budget=None,
    need_pages=False,
):
    """({url, is_index, children, fetched}, None) for a declared sitemap, or
    (None, why) when its children are unknown. `mode` is the audit fetch mode
    (none / missing / all); `on_disk` maps URLs to pages a spider's own fetch
    cached (spider_cached_urls). Read from disk first and fetched at most once
    per URL (see above); an exhausted fetch budget is not a site failure, so it
    leaves no marker. `need_pages`: a leaf manifest from before page counts
    were kept is recounted from its cached copy, or fetched once if there is
    none; `budget` defaults to the listing's own (index_budget)."""
    d = _index_dir(cache_dir, url)
    mf, failed = os.path.join(d, "manifest.json"), d + ".failed.json"
    seen = state.setdefault("index_seen", set())
    today = datetime.date.today().isoformat()
    done = state.get("fetched", {})
    if url in done:
        # fetched earlier in THIS run (the spider's coverage fetch): reuse it
        seen.add(url)
        text = read_page(done[url]) if done[url] else None
        if _answered(text):
            return _save_manifest(url, cache_dir, text), None
        prior = _read_json(mf)
        if prior is not None:
            return prior, None
        _write_json(failed, {"url": url, "date": today})
        return None, f"fetch failed {today}"
    if mode != "all" or url in seen:
        cached = _read_json(mf)
        stale = need_pages and cached and not cached.get("is_index")
        if stale and "pages" not in cached:
            text = read_page(os.path.join(d, "page.html"))
            if _answered(text):
                return _save_manifest(url, cache_dir, text), None
            cached = None
        if cached is not None:
            return cached, None
        text = read_page((on_disk or {}).get(url))
        if _answered(text):
            return _save_manifest(url, cache_dir, text), None
        marker = _read_json(failed)
        if marker is not None:
            return None, f"fetch failed {marker.get('date', '')}".strip()
        if url in seen:
            return None, "fetch failed"
    if mode == "none":
        return None, "not fetched (--no-fetch)"
    budget = budget or index_budget(state)
    if not _budget_left(budget):
        return None, "fetch budget exhausted"
    seen.add(url)
    text = fetch_once(url, d, project, browser, state, retry, _answered, budget)
    if _answered(text):
        return _save_manifest(url, cache_dir, text), None
    prior = _read_json(mf)  # a failed refresh keeps the previous manifest
    if prior is not None:
        return prior, None
    if not _budget_left(budget):
        return None, "fetch budget exhausted"
    _write_json(failed, {"url": url, "date": today})
    return None, f"fetch failed {today}"


# The site-wide `total` also counts the pages of the sitemaps a spider was NOT
# given. Each is read like a declared sitemap above (disk first, fetched at most
# once per host, refreshed only by --fetch-all), on its own larger budget: a
# site lists far more sitemaps than it declares.
COUNT_FETCH_CAP = 1000


def count_budget(state):
    return state.setdefault(
        "count_budget", {"global": 0, "global_cap": COUNT_FETCH_CAP}
    )


def sitemap_page_count(url, *fetch_args, on_disk=None, nested=False):
    """Page URLs a sitemap lists (an index: its children's, one level deep), or
    None while any of them is unknown. `fetch_args` as for index_manifest."""
    m, _ = index_manifest(
        url,
        *fetch_args,
        on_disk=on_disk,
        budget=count_budget(fetch_args[2]),
        need_pages=True,
    )
    if m is None:
        return None
    if m.get("not_sitemap"):
        return 0
    if not m.get("is_index"):
        return m["pages"]
    if nested:
        return None
    counts = [
        sitemap_page_count(k, *fetch_args, on_disk=on_disk, nested=True)
        for k in m.get("children") or []
    ]
    return None if None in counts else sum(counts)


def discovered_sitemaps(
    host, project, cache_dir, state, mode, browser, retry, robots_known=False, seeds=()
):
    """(sitemaps, why) for a host with no robots `Sitemap:` line on disk:
    discovery (robots.txt, then /sitemap.xml) run at most once per host and
    remembered in _host/<host>/declared.json. `robots_known` = robots.txt is on
    disk and lists none, so it isn't fetched again; `seeds` are cached
    /sitemap.xml copies (a spider's earlier probe or sitemap fetch) read before
    any fetch. An empty answer is stored only when it is a fact — robots.txt
    read (or on disk) and /sitemap.xml answered without a sitemap; a blocked or
    failed discovery leaves a dated marker instead, retried only by --fetch-all,
    and returns (None, why): the total stays unknown."""
    hd = host_cache_dir(cache_dir, host)
    path = os.path.join(hd, "declared.json")
    failed = os.path.join(hd, "declared.failed.json")
    seen = state.setdefault("index_seen", set())
    key = "declared:" + (host or "")
    if mode != "all" or key in seen:
        cached = _read_json(path)
        if cached is not None:
            return cached.get("sitemaps", []), None
        marker = _read_json(failed)
        if marker is not None:
            date = marker.get("date", "")
            return None, f"sitemap discovery failed {date}; retried only by --fetch-all"
        if key in seen:
            return None, "sitemap discovery failed"
    if not host:
        return None, "no host to discover"
    base = "https://" + host
    sm_text = None
    if mode != "all":
        for page in list(seeds) + [os.path.join(hd, "_smprobe", "page.html")]:
            sm_text = read_page(page)
            if sm_text is not None:
                break
    if mode == "none" and not (robots_known and sm_text is not None):
        return None, "not fetched (--no-fetch)"
    budget = index_budget(state)
    if not _budget_left(budget) and not (robots_known and sm_text is not None):
        return None, "fetch budget exhausted"
    seen.add(key)
    os.makedirs(hd, exist_ok=True)
    found, answered, sm_text = _discover(
        host, project, "", hd, state, browser, retry, budget, robots_known, sm_text
    )
    date = datetime.date.today().isoformat()
    if found == [base + "/sitemap.xml"] and sm_text:
        # the /sitemap.xml answer already holds the sitemap: keep it as the
        # manifest so the same URL isn't fetched a second time
        _save_manifest(found[0], cache_dir, sm_text)
    if found or answered:
        _write_json(path, {"host": host, "sitemaps": found, "date": date})
        try:
            os.remove(failed)
        except OSError:
            pass
        return found, None
    if not _budget_left(budget):
        return None, "fetch budget exhausted"  # not an answer worth keeping
    _write_json(failed, {"host": host, "date": date})
    return None, f"sitemap discovery failed {date}; retried only by --fetch-all"


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
        is_index, locs = parse_sitemap(text)  # a feed or HTML page → no locs
        if is_index:
            continue
        for loc in locs:
            if is_media_loc(loc):
                continue  # image/AV attachment loc — media, not a content page
            pages.add(loc)
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
