"""Per-spider host-frequency report for the crawl's harvested PDF links.

The framework records every PDF link it encounters as a URL-only row
(`metadata_json.content_type == "pdf"`, with `found_on` = the page that linked
it; nothing is downloaded under the default `PDF_MODE=links_only`). This lens
splits that harvest per spider into:

- **same-org PDFs** — hosts inside the spider's own `allowed_domains` (the
  org's own documents) — reported as a count;
- **external PDFs** — everything else, ranked by host frequency so a human can
  tell the org's own external repository (a host that recurs heavily, e.g. a
  CDN/S3 bucket) from one-off citations, without any fixed cut-off.

Own-domain resolution degrades explicitly: the DB `allowed_domains` (what the
crawl actually ran with) → the spider's `final_spider.json` → nothing (every
host counts as external, with a printed warning).

Usage (engine behind the audit's PDFs lens; standalone:)
    python3 -m core.quality.external_pdf --project gscc [--only rmi_org]
Writes data/<project>/_audit/external_pdf_report.md and prints a summary.
"""

import argparse
import collections
import glob
import json
import os

from core.quality._env import DATA_DIR
from core.quality.corpus import host_in_domains, is_pdf_row, url_host


def collect(spider_dir):
    """(url, found_on) per PDF-row OCCURRENCE across crawls/*.jsonl — occurrences
    preserved (the same PDF linked from three pages appears three times; citation
    frequency is the ranking signal)."""
    out = []
    for path in glob.glob(os.path.join(spider_dir, "crawls", "*.jsonl")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not is_pdf_row(rec):
                    continue
                u = (rec.get("url") or "").strip()
                if not u:
                    continue
                md = rec.get("metadata_json")
                if isinstance(md, str):
                    try:
                        md = json.loads(md)
                    except json.JSONDecodeError:
                        md = {}
                found_on = (md or {}).get("found_on") or ""
                out.append((u, found_on))
    return out


def _cfg_domains(base, spider):
    """allowed_domains (+ source_url host) from the spider's final_spider.json —
    the fallback when the DB is unreachable."""
    for rel in ("final_spider.json", os.path.join("analysis", "final_spider.json")):
        p = os.path.join(base, spider, rel)
        try:
            with open(p, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        doms = list(cfg.get("allowed_domains") or [])
        src = url_host(cfg.get("source_url") or "")
        if src and src not in doms:
            doms.append(src)
        return doms
    return []


def own_domains(project):
    """{spider: [own domains]} — DB first (what the crawl ran with), never a crash."""
    try:
        from core.quality.crawl_audit.spiders_db import load_spiders

        return {
            name: (sp.get("domains") or ([sp["host"]] if sp.get("host") else []))
            for name, sp in load_spiders(project).items()
        }
    except Exception as e:
        print(
            f"⚠ spider domains unavailable from the DB ({e}); "
            "falling back to final_spider.json per spider"
        )
        return {}


def run(project, opts=None):
    """Per-spider PDF-harvest report for `project`. Writes
    `_audit/external_pdf_report.md`, prints it, and RETURNS the structured result:
    {spiders: [{spider, total, unique, own_total, own_unique,
                hosts: [{host, count, sample, urls, found_on}, ...]}, ...],
     report_path}. `hosts` covers EXTERNAL hosts only (the tab exists to surface
    external repositories); same-org numbers are per-spider counts. `opts` may
    carry `.only` (a single spider name)."""
    only = getattr(opts, "only", None) if opts is not None else None

    base = os.path.join(DATA_DIR, project)
    spiders = sorted(
        d
        for d in os.listdir(base)
        if os.path.isdir(os.path.join(base, d))
        and not d.startswith("_")
        and d != "health"
    )
    if only:
        spiders = [s for s in spiders if s == only]

    db_domains = own_domains(project)

    lines = [f"# {project}: PDF-harvest host report", ""]
    lines.append(
        "PDF links harvested by each spider as URL-only rows (nothing "
        "downloaded). External hosts (outside the spider's own domains) are "
        "grouped by frequency — a host that dominates is likely the org's own "
        "external repository; hosts with 1-2 hits are usually citations. "
        "Decide per spider.\n"
    )
    report = []
    for s in spiders:
        occurrences = collect(os.path.join(base, s))
        own = db_domains.get(s) or _cfg_domains(base, s)
        if not own and occurrences:
            print(
                f"⚠ {s}: no own-domains resolvable (DB and final_spider.json) — "
                "every PDF host counts as external"
            )
        ext = [(u, f) for u, f in occurrences if not host_in_domains(url_host(u), own)]
        own_occ = len(occurrences) - len(ext)
        own_uniq = len({u for u, _ in occurrences if host_in_domains(url_host(u), own)})
        uniq = sorted({u for u, _ in ext})
        hosts = collections.Counter(url_host(u) for u, _ in ext)
        lines.append(
            f"## {s}  —  {len(ext)} external PDF links, {len(uniq)} unique, "
            f"{len(hosts)} hosts · {own_uniq} same-org PDFs"
        )
        host_rows = []
        if not hosts:
            lines.append("  (none)\n")
            report.append(
                {
                    "spider": s,
                    "total": len(ext),
                    "unique": len(uniq),
                    "own_total": own_occ,
                    "own_unique": own_uniq,
                    "hosts": host_rows,
                }
            )
            continue
        lines.append("")
        lines.append("| host | links | sample | found on |")
        lines.append("|---|---:|---|---|")
        by_host, first_found = {}, {}
        for u, f in ext:
            h = url_host(u)
            if u not in by_host.setdefault(h, []):
                by_host[h].append(u)
            first_found.setdefault(h, f)
        for h, n in hosts.most_common():
            hu = sorted(by_host.get(h, []))  # every unique URL on this host
            sample = hu[0] if hu else ""
            if len(sample) > 90:
                sample = sample[:90] + "…"
            fo = first_found.get(h) or ""
            if len(fo) > 70:
                fo = fo[:70] + "…"
            lines.append(f"| {h} | {n} | {sample} | {fo} |")
            host_rows.append(
                {
                    "host": h,
                    "count": n,
                    "sample": sample,
                    "urls": hu,
                    "found_on": first_found.get(h) or "",
                }
            )
        lines.append("")
        report.append(
            {
                "spider": s,
                "total": len(ext),
                "unique": len(uniq),
                "own_total": own_occ,
                "own_unique": own_uniq,
                "hosts": host_rows,
            }
        )

    out_dir = os.path.join(base, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "external_pdf_report.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\nReport → {out}")
    return {"spiders": report, "report_path": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", default=None, help="single spider name")
    args = ap.parse_args()
    run(args.project, args)


if __name__ == "__main__":
    main()
