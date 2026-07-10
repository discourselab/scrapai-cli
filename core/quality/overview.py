"""Content-profile engine — summarise what each spider ACTUALLY collected.

The audit answers "did we get the whole site and did extraction not crash?" (coverage vs
sitemap, dupes, thin content). This is the complementary lens: a per-spider *content profile*
of the crawl output, so a human can judge whether a scrape faithfully mirrors the source site
WITHOUT opening the raw `crawls/*.jsonl`.

Read-only. Reads the same on-disk corpus as the audit (`data/<project>/<spider>/crawls/*.jsonl`,
skipping `.superseded`) plus each spider's `final_spider.json` (fallback
`analysis/final_spider.json`) for config intent (allowed_domains, allow-rules, field list).

Per spider it computes:
  - sections      — from the URL path, so it does not depend on the fragile `section` field;
                    plus per-allow-rule yield, flagging a configured section that produced 0 items
  - dates         — publication min/max, null %, and a per-year histogram (gaps = truncated crawl,
                    outliers stay visible instead of blowing out a bare min/max)
  - field coverage— % of items where each configured field is non-empty (the strongest
                    "is extraction faithful?" signal)
  - thin items    — count of suspiciously short pages (likely listings/nav scraped as articles)
  - degenerate    — fields that are the same constant on every item (selector grabbing a label)
  - off-domain    — scraped URLs outside allowed_domains (misconfiguration)
  - samples       — a few real titles/URLs to eyeball plausibility

Writes `data/<project>/_audit/overview_<project>.md` + `overview_<project>.csv` and returns
`{"spiders": [row, ...], "report_path": md_path}` for the HTML dashboard.
"""

import csv
import glob
import json
import os
import re
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

from core.quality._env import DATA_DIR
from core.quality import _env
from core.quality.corpus import host_in_domains, is_pdf_row, median, url_host

# Fields that are long free text — never candidates for the "degenerate constant" check and
# not worth listing distinct values for.
_LONGTEXT = {"content", "markdown_content", "html", "headline_image"}
# Default core fields when a spider uses a generic extractor (no FIELD_EXTRACT of its own).
_CORE_FIELDS = ["title", "content", "author", "published_date"]
# Inherently-sparse fields: a page legitimately may not have a video, a PDF, a tag, etc.
# Low coverage on these is NORMAL, so they never drive the "worst field" headline or attention.
_OPTIONAL_FIELDS = {
    "tags",
    "pdf_links",
    "video_links",
    "headline_image",
    "section",
    "markdown_content",
    "image",
    "images",
    "keywords",
    "summary",
    "top_image",
}
# Fields that should extract on essentially every content page — flag hard if they don't.
_ALWAYS_FIELDS = {"title", "content"}
_DISTINCT_CAP = 80  # stop tracking distinct values past this (not degenerate anyway)
_MAX_SAMPLES = 5


# --------------------------------------------------------------------------- config
def _config_path(spider_dir):
    """final_spider.json, else analysis/final_spider.json, else None."""
    for rel in ("final_spider.json", os.path.join("analysis", "final_spider.json")):
        p = os.path.join(spider_dir, rel)
        if os.path.exists(p):
            return p
    return None


def _load_config(spider_dir):
    path = _config_path(spider_dir)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        # sections-authored configs desugar to rules+callbacks+FIELDS (pure
        # dict->dict; documented no-op when `sections` is absent)
        from core.sections import expand_sections

        return expand_sections(cfg)
    except Exception:
        return cfg


def _configured_fields(cfg):
    """The fields this spider promises to extract, in a stable order. FIELD_EXTRACT keys +
    every callback's extract keys; falls back to the core set for generic-extractor spiders.
    """
    settings = (cfg.get("settings") or {}) if cfg else {}
    fields = list(
        (settings.get("FIELDS") or settings.get("FIELD_EXTRACT") or {}).keys()
    )
    for cb in (cfg.get("callbacks") or {}).values() if cfg else []:
        for k in (cb.get("extract") or {}).keys():
            if k not in fields:
                fields.append(k)
    if not fields:
        fields = list(_CORE_FIELDS)
    return fields


def _extractor_label(cfg):
    order = ((cfg.get("settings") or {}).get("EXTRACTOR_ORDER") or []) if cfg else []
    if not order:
        return "?"
    return "+".join(order)


def _allow_patterns(cfg):
    pats = []
    for r in (cfg.get("rules") or []) if cfg else []:
        for p in r.get("allow") or []:
            if isinstance(p, str):
                pats.append(p)
    return pats


def _primary_host(cfg):
    doms = (cfg.get("allowed_domains") or []) if cfg else []
    if doms:
        return doms[0]
    src = (cfg.get("source_url") or "") if cfg else ""
    return urlparse(src).netloc if src.startswith("http") else ""


# --------------------------------------------------------------------------- helpers
def _in_domains(host, domains):
    # Unlike corpus.host_in_domains, empty domains means "can't judge" here —
    # never off-domain-flag a spider with no configured domains.
    return True if not domains else host_in_domains(host, domains)


def _section_of(url):
    """First non-empty path segment — a robust, config-independent section key."""
    try:
        path = urlparse(url).path
    except ValueError:
        return "(?)"
    segs = [s for s in path.split("/") if s]
    if not segs:
        return "(home)"
    return segs[0]


def _parse_date(v):
    """A datetime from a crawl `published_date`, or None. Handles the normalised
    'YYYY-MM-DD HH:MM:SS' / ISO forms, a few common locale formats, then a bare-year fallback.
    """
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    iso = s.replace("Z", "").replace("T", " ").split(".")[0].strip()
    try:
        # tzinfo stripped: a corpus can mix naive ('2024-01-05 10:00:00') and aware
        # ('2024-01-05 10:00:00+02:00') stamps, and min/max across them raises
        return datetime.fromisoformat(iso).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    m = re.search(r"(?:19|20)\d{2}", s)
    if m:
        try:
            return datetime(int(m.group()), 1, 1)
        except ValueError:
            return None
    return None


def _populated(v):
    """Is a crawl-field value non-empty?"""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    return True


def _first_str(rec, *keys):
    for k in keys:
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# --------------------------------------------------------------------------- scan
def _crawl_files(spider_dir):
    return [
        p
        for p in sorted(glob.glob(os.path.join(spider_dir, "crawls", "*.jsonl")))
        if not p.endswith(".superseded")
    ]


def profile_spider(spider, spider_dir, cfg, thin_chars):
    """Build the content-profile row for one spider by streaming its crawl output."""
    fields = _configured_fields(cfg)
    allow = _allow_patterns(cfg)
    domains = (cfg.get("allowed_domains") or []) if cfg else []
    host = _primary_host(cfg)

    allow_re = []
    for p in allow:
        try:
            allow_re.append((p, re.compile(p)))
        except re.error:
            pass
    allow_hits = {p: 0 for p, _ in allow_re}

    urlset = set()
    rows = 0
    sections = Counter()
    years = Counter()
    n_dated = n_null_date = suspicious_dates = 0
    dmin = dmax = None
    field_pop = {f: 0 for f in fields}
    content_lens = []
    thin = 0
    distinct = {
        f: set() for f in fields if f not in _LONGTEXT
    }  # for degenerate detection
    offdomain = 0
    offdomain_hosts = Counter()
    pdf_urls_set, pdf_rows, pdf_ext_set = set(), 0, set()
    samples = []
    newest = ""
    now_year = datetime.now().year

    files = _crawl_files(spider_dir)
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if is_pdf_row(rec):
                    # PDF harvest rows are their own signal — they must not feed
                    # sections/dates/fields/thin (empty by design) nor the
                    # off-domain check (external PDFs are the POINT, not a leak)
                    pdf_rows += 1
                    u = rec.get("url") or ""
                    if u:
                        pdf_urls_set.add(u)
                        if not _in_domains(url_host(u), domains):
                            pdf_ext_set.add(u)
                    continue
                rows += 1
                url = rec.get("url") or ""
                if url:
                    urlset.add(url)
                    sections[_section_of(url)] += 1
                    h = url_host(url)
                    if h and not _in_domains(h, domains):
                        offdomain += 1
                        offdomain_hosts[h] += 1
                    for p, rx in allow_re:
                        if rx.search(url):
                            allow_hits[p] += 1

                # dates
                d = _parse_date(rec.get("published_date"))
                if d is None:
                    n_null_date += 1
                else:
                    n_dated += 1
                    years[d.year] += 1
                    if d.year < 1995 or d.year > now_year + 1:
                        suspicious_dates += 1
                    if dmin is None or d < dmin:
                        dmin = d
                    if dmax is None or d > dmax:
                        dmax = d

                # field population + degenerate tracking
                for f in fields:
                    v = rec.get(f)
                    if _populated(v):
                        field_pop[f] += 1
                        if f in distinct and len(distinct[f]) <= _DISTINCT_CAP:
                            distinct[f].add(
                                v if isinstance(v, str) else json.dumps(v, default=str)
                            )

                # content length / thin
                content = rec.get("content")
                if isinstance(content, str):
                    clen = len(content.strip())
                    content_lens.append(clen)
                    if clen < thin_chars:
                        thin += 1

                # samples
                if len(samples) < _MAX_SAMPLES:
                    t = _first_str(rec, "title")
                    if t or url:
                        samples.append({"title": t, "url": url})

                # freshness
                stamp = _first_str(rec, "scraped_at", "extracted_at")
                if stamp > newest:
                    newest = stamp

    scraped = len(urlset)
    denom = rows or 1
    field_rows = [
        {
            "field": f,
            "pct": round(100 * field_pop[f] / denom),
            "populated": field_pop[f],
        }
        for f in fields
    ]
    # "worst field" reports only fields that SHOULD be populated — a sparse video_links at 4%
    # is not a defect and must not become the headline metric.
    significant = [f for f in field_rows if f["field"] not in _OPTIONAL_FIELDS]
    worst = (
        min(significant or field_rows, key=lambda x: x["pct"]) if field_rows else None
    )
    degenerate = [
        {"field": f, "value": next(iter(distinct[f]))[:120]}
        for f in distinct
        if field_pop.get(f, 0) >= 5 and len(distinct[f]) == 1
    ]
    zero_yield = [p for p, _ in allow_re if allow_hits[p] == 0]

    return {
        "spider": spider,
        "host": host,
        "config_found": cfg is not None,
        "extractor": _extractor_label(cfg),
        "files": len(files),
        "rows": rows,  # HTML article rows (the profile universe)
        "rows_total": rows + pdf_rows,
        "unique": scraped,
        "pdf_rows": pdf_rows,
        "pdf_unique": len(pdf_urls_set),
        "pdf_ext": len(pdf_ext_set),
        "sections": sections.most_common(),
        "n_sections": len(sections),
        "date_min": dmin.strftime("%Y-%m-%d") if dmin else None,
        "date_max": dmax.strftime("%Y-%m-%d") if dmax else None,
        "n_dated": n_dated,
        "n_null_date": n_null_date,
        "null_date_pct": round(100 * n_null_date / denom),
        "suspicious_dates": suspicious_dates,
        "year_hist": dict(sorted(years.items())),
        "fields": field_rows,
        "worst_field": worst["field"] if worst else "",
        "worst_field_pct": worst["pct"] if worst else 100,
        "content_med": int(median(content_lens)),
        "thin": thin,
        "thin_pct": round(100 * thin / denom),
        "degenerate": degenerate,
        "offdomain": offdomain,
        "offdomain_hosts": offdomain_hosts.most_common(6),
        "zero_yield_rules": zero_yield,
        "samples": samples,
        "newest": newest,
        "flags": "",  # filled by _flags below
        "attention": 0,
    }


# --------------------------------------------------------------------------- flags
def _flags(r, thin_chars):
    """Compact attention tokens ( ` · `-joined ), plus a 0/1 attention verdict."""
    toks = []
    if r["rows"] == 0:
        toks.append("no-output")
    if not r["config_found"]:
        toks.append("no-config")
    for f in r["fields"]:
        if r["rows"] < 3 or f["field"] in _OPTIONAL_FIELDS:
            continue  # sparse fields (video/pdf/tags) legitimately vary
        thresh = 90 if f["field"] in _ALWAYS_FIELDS else 55
        if f["pct"] < thresh:
            toks.append(f'{f["field"]} {f["pct"]}%')
    if r["thin_pct"] > 25 and r["rows"] >= 3:
        toks.append(f'thin {r["thin_pct"]}% (<{thin_chars})')
    for z in r["zero_yield_rules"]:
        toks.append(f"zero-yield {z}")
    for d in r["degenerate"]:
        toks.append(f'constant {d["field"]}')
    if r["offdomain"]:
        toks.append(f'off-domain {r["offdomain"]}')
    if r["suspicious_dates"]:
        toks.append(f'odd-date {r["suspicious_dates"]}')
    if r["n_dated"] and r["null_date_pct"] >= 60:
        toks.append(f'date-null {r["null_date_pct"]}%')
    # a clean spider with only a high date-null (common for date-less sites) is
    # informational: the token stays in `flags`, but on its own it never sets attention
    hard = [t for t in toks if not t.startswith("date-null")]
    r["flags"] = " · ".join(toks)
    r["attention"] = 1 if hard else 0
    return r


# --------------------------------------------------------------------------- outputs
def _spark(year_hist):
    """A tiny unicode bar sparkline over the year histogram (chronological)."""
    if not year_hist:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    vals = list(year_hist.values())
    mx = max(vals)
    out = []
    for y, n in year_hist.items():
        idx = (
            0 if mx == 0 else min(len(blocks) - 1, round((n / mx) * (len(blocks) - 1)))
        )
        out.append(blocks[idx])
    return "".join(out)


def _date_cell(r):
    if not r["date_min"]:
        return "—"
    return f'{r["date_min"]}→{r["date_max"]}'


def _write_markdown(project, rows, out_dir, thin_chars):
    lines = [f"# {project}: spider content profile", ""]
    lines.append(
        "What each spider **actually collected** (complementary to `./scrapai audit`, "
        "which covers coverage vs sitemap + dupes). Read-only. Sections are derived from "
        "the URL path; field % is the share of items where that field is non-empty; "
        f"thin = content shorter than {thin_chars} chars.\n"
    )
    # summary table
    lines.append(
        "| spider | items | pdf | sections | dates | null% | worst field | thin% | flags |"
    )
    lines.append("|---|---:|---:|---:|---|---:|---|---:|---|")
    for r in rows:
        wf = f'{r["worst_field"]} {r["worst_field_pct"]}%' if r["fields"] else "—"
        pdfc = f'{r["pdf_unique"]} ({r["pdf_ext"]} ext)' if r.get("pdf_unique") else "—"
        lines.append(
            f'| {r["spider"]} | {r["rows"]} | {pdfc} | {r["n_sections"]} | {_date_cell(r)} | '
            f'{r["null_date_pct"]} | {wf} | {r["thin_pct"]} | {r["flags"] or "—"} |'
        )
    lines.append("")

    # per-spider detail
    for r in rows:
        lines.append(
            f'## {r["spider"]}  —  {r["rows"]} items, {r["unique"]} unique '
            f'({r["files"]} file{"s" if r["files"] != 1 else ""}, extractor {r["extractor"]})'
        )
        if not r["config_found"]:
            lines.append(
                "- ⚠ no `final_spider.json` found — profiled crawl output only."
            )
        if r.get("pdf_rows"):
            lines.append(
                f'- **PDFs harvested**: {r["pdf_unique"]} unique '
                f'({r["pdf_ext"]} external-host) — {r["pdf_rows"]} link occurrences'
            )
        # sections
        top = ", ".join(f"{s} ({n})" for s, n in r["sections"][:12])
        lines.append(f'- **Sections** ({r["n_sections"]}): {top or "—"}')
        if r["zero_yield_rules"]:
            lines.append(
                "  - ⚠ **allow-rules that matched 0 scraped URLs:** "
                + ", ".join(f"`{z}`" for z in r["zero_yield_rules"])
            )
        # dates
        if r["date_min"]:
            hist = " ".join(f"{y}:{n}" for y, n in r["year_hist"].items())
            lines.append(
                f'- **Dates**: {r["date_min"]} → {r["date_max"]} '
                f'({r["n_dated"]} dated, {r["null_date_pct"]}% null) {_spark(r["year_hist"])}'
            )
            lines.append(f"  - per year: {hist}")
            if r["suspicious_dates"]:
                lines.append(
                    f'  - ⚠ {r["suspicious_dates"]} out-of-range date(s) (<1995 or future)'
                )
        else:
            lines.append(f'- **Dates**: none parsed ({r["null_date_pct"]}% null)')
        # field coverage
        fc = " · ".join(f'{f["field"]} {f["pct"]}%' for f in r["fields"])
        lines.append(f'- **Field coverage**: {fc or "—"}')
        # content / thin
        lines.append(
            f'- **Content**: median {r["content_med"]} chars · '
            f'{r["thin"]} thin items ({r["thin_pct"]}%)'
        )
        if r["degenerate"]:
            lines.append(
                "- ⚠ **Constant fields** (same value on every item): "
                + ", ".join(f'`{d["field"]}` = "{d["value"]}"' for d in r["degenerate"])
            )
        if r["offdomain"]:
            hosts = ", ".join(f"{h} ({n})" for h, n in r["offdomain_hosts"])
            lines.append(f'- ⚠ **Off-domain URLs**: {r["offdomain"]} → {hosts}')
        # samples
        if r["samples"]:
            lines.append("- **Samples**:")
            for s in r["samples"]:
                lines.append(f'  - {s["title"] or "(no title)"} — {s["url"]}')
        if r["newest"]:
            lines.append(f'- Newest item stamp: {r["newest"]}')
        lines.append("")

    out = os.path.join(out_dir, f"overview_{project}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return out


def _write_csv(project, rows, out_dir):
    out = os.path.join(out_dir, f"overview_{project}.csv")
    cols = [
        "spider",
        "host",
        "rows",
        "pdf_unique",
        "pdf_ext",
        "pdf_rows",
        "unique",
        "files",
        "extractor",
        "n_sections",
        "top_section",
        "date_min",
        "date_max",
        "n_dated",
        "null_date_pct",
        "worst_field",
        "worst_field_pct",
        "content_med",
        "thin",
        "thin_pct",
        "degenerate",
        "offdomain",
        "zero_yield",
        "newest",
    ]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(
                {
                    "spider": r["spider"],
                    "host": r["host"],
                    "rows": r["rows"],
                    "pdf_unique": r["pdf_unique"],
                    "pdf_ext": r["pdf_ext"],
                    "pdf_rows": r["pdf_rows"],
                    "unique": r["unique"],
                    "files": r["files"],
                    "extractor": r["extractor"],
                    "n_sections": r["n_sections"],
                    "top_section": r["sections"][0][0] if r["sections"] else "",
                    "date_min": r["date_min"] or "",
                    "date_max": r["date_max"] or "",
                    "n_dated": r["n_dated"],
                    "null_date_pct": r["null_date_pct"],
                    "worst_field": r["worst_field"],
                    "worst_field_pct": r["worst_field_pct"],
                    "content_med": r["content_med"],
                    "thin": r["thin"],
                    "thin_pct": r["thin_pct"],
                    "degenerate": ";".join(d["field"] for d in r["degenerate"]),
                    "offdomain": r["offdomain"],
                    "zero_yield": ";".join(r["zero_yield_rules"]),
                    "newest": r["newest"],
                }
            )
    return out


def _print_terminal(project, rows, thin_chars):
    print(
        f"\n{project}: spider content profile  ({len(rows)} spiders, thin < {thin_chars} chars)\n"
    )
    hdr = (
        f'{"spider":24} {"items":>6} {"pdf":>6} {"sect":>4} {"dates":>23} '
        f'{"null":>5} {"worst field":>18} {"thin":>5}  flags'
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        wf = f'{r["worst_field"]} {r["worst_field_pct"]}%' if r["fields"] else "-"
        mark = "!" if r["attention"] else " "
        print(
            f'{mark}{r["spider"][:23]:23} {r["rows"]:>6} {r["pdf_unique"]:>6} {r["n_sections"]:>4} '
            f'{_date_cell(r):>23} {str(r["null_date_pct"]) + "%":>5} {wf:>18} '
            f'{str(r["thin_pct"]) + "%":>5}  {r["flags"]}'
        )
    print()


# --------------------------------------------------------------------------- run
def run(project, opts=None):
    """Build the content profile for every spider in `project` (or `opts.only`). Writes
    `_audit/overview_<project>.md` + `.csv`, prints a terminal table, and returns
    `{"spiders": [row, ...], "report_path": md_path, "thin_chars": n}`."""
    only = list(getattr(opts, "only", None) or []) if opts is not None else []
    thin_chars = (
        int(getattr(opts, "thin_chars", 200) or 200) if opts is not None else 200
    )

    if not _env.project_exists(project):
        # guard the programmatic path too (the CLI wrapper also checks): a typo'd name
        # would scaffold data/<typo>/_audit/ below and write empty reports into it
        raise SystemExit(
            f"❌ No project named '{project}'. Overview only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects. Nothing was created."
        )
    base = os.path.join(DATA_DIR, project)
    spider_names = sorted(
        d
        for d in (os.listdir(base) if os.path.isdir(base) else [])
        if os.path.isdir(os.path.join(base, d))
        and not d.startswith("_")
        and d != "health"
    )
    if only:
        spider_names = [s for s in spider_names if s in only]

    rows = []
    for s in spider_names:
        spider_dir = os.path.join(base, s)
        cfg = _load_config(spider_dir)
        row = profile_spider(s, spider_dir, cfg, thin_chars)
        _flags(row, thin_chars)
        rows.append(row)

    out_dir = os.path.join(base, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    md = _write_markdown(project, rows, out_dir, thin_chars)
    _write_csv(project, rows, out_dir)
    _print_terminal(project, rows, thin_chars)
    return {"spiders": rows, "report_path": md, "thin_chars": thin_chars}
