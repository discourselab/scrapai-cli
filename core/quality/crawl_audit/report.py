"""Output writers: crawl_audit.csv / coverage.csv and audit_<project>.md, one
helper per markdown section (the section order lives in write_outputs)."""

import csv
import os

from .spiders_db import audit_dir
from .text import (
    AGENTS_PREAMBLE,
    DEDUPE_FIX,
    DUPES_CAUSE,
    DUPES_EXPLAINER,
    FETCH_MODES_NOTE,
    GOAL,
    LEGEND,
    NOTES_AND_DEFINITIONS,
    fix_hints,
)

# severity rank for the Compliance section lead-emoji / sort (worst first). The no-data rows
# lead: ‼️ capture-failed and ❓ not-checked are the most actionable (we know nothing), so they
# sort ABOVE the graded 🔴→🟢 rows rather than falling to the bottom.
_COMPL_SEV = {"‼️": -2, "❓": -1, None: -1, "🔴": 0, "🔎": 1, "🟡": 2, "⚪": 3, "🟢": 4}


def compl_lead(e):
    """The worst-of-access/reuse emoji for the section's lead column (eye lands on problems)."""
    if e.get("failed"):
        return "‼️"
    if e.get("checked") is None:
        return "❓"
    cands = [x for x in (e.get("access"), e.get("reuse")) if x]
    return min(cands, key=lambda x: _COMPL_SEV.get(x, 5)) if cands else "❓"


def compl_notes(e):
    """The ONE attention column — compact tokens, shown only when present (no extra columns)."""
    t = []
    if e.get("conflicts"):
        t.append("⚠ " + ", ".join(e["conflicts"]))
    if e.get("ai_scrape"):
        t.append("AI-scrape")
    if e.get("ai_reuse"):
        t.append("AI-reuse (MR)" if e.get("mr_ban") else "AI-reuse (ToS)")
    v = e.get("llms")
    if v in ("prohibits", "partial"):
        t.append("llms✗")
    elif v:
        t.append("llms✓")
    if e.get("stale"):
        t.append("check-behind-crawl")
    return " · ".join(t)


# crawl_audit.csv columns + their read-back types, in the score_spider() row order.
# ONE structure drives both write_csvs and read_csv_rows, so writer and reader can't
# drift. `int` columns are cast back on read; the two that mix a count with a text
# placeholder ("-" sitemap_total, "" coverage_pct) keep the placeholder as-is.
# `eligible` stays str on purpose — scoring stores it as str(...) even when numeric.
CSV_FIELDS = {
    "spider": str,
    "sitemap": str,
    "sitemap_total": int,
    "eligible": str,
    "scraped": int,
    "pdf": int,
    "pdf_own": int,
    "pdf_ext": int,
    "unique": int,
    "rows": int,
    "true_dupes": int,
    "versions": int,
    "pdf_multi": int,
    "dup_pct": int,
    "files": int,
    "content": int,
    "content_pct": int,
    "content_med": int,
    "coverage_pct": int,
    "stale": str,
    "flags": str,
    "status": str,
}


def write_csvs(out, rows):
    fields = list(CSV_FIELDS)
    with open(os.path.join(out, "crawl_audit.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    # coverage-only csv (sitemap spiders)
    with open(os.path.join(out, "coverage.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows([r for r in rows if r["sitemap"] in ("yes", "found")])


def read_csv_rows(out):
    """crawl_audit.csv read back into typed row dicts — the inverse of write_csvs,
    used by a --only run to carry the un-scored spiders' rows into the new report.
    Returns None when no CSV exists (no previous report to merge into)."""
    path = os.path.join(out, "crawl_audit.csv")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, newline="") as fh:
        for rec in csv.DictReader(fh):
            for k, cast in CSV_FIELDS.items():
                if cast is int:
                    try:
                        rec[k] = int(rec[k])
                    except (ValueError, TypeError):
                        pass  # placeholder ("-" / "") — kept as written
            rows.append(rec)
    return rows


def merge_only_rows(fresh, stored, present):
    """The full row set for a --only run: freshly scored `fresh` + every `stored`
    row whose spider was neither re-scored nor dropped from the `present` working
    set, in the normal run's sorted-by-spider order."""
    done = {r["spider"] for r in fresh}
    kept = [r for r in stored if r["spider"] not in done and r["spider"] in present]
    return sorted(fresh + kept, key=lambda r: r["spider"])


def write_header(fh, project, rows, config_warnings):
    fh.write(f"# {project}: crawl audit\n\n")
    if config_warnings:
        fh.write("> ⚠ **Config warnings**\n>\n")
        for w in config_warnings:
            fh.write(f"> - {w}\n")
        fh.write("\n")
    fh.write(AGENTS_PREAMBLE)
    fh.write(
        "**Regenerate:** use `./scrapai audit` for the full run — it rebuilds this "
        "markdown, the CSVs, **and** the interactive HTML dashboard "
        f"(`_audit/dashboard_{project}.html`):\n\n"
    )
    fh.write("```bash\n")
    fh.write(
        f"./scrapai audit --project {project}         # report + CSVs + HTML dashboard\n"
    )
    fh.write("```\n\n")
    fh.write(FETCH_MODES_NOTE)
    fh.write(
        f"**Total spiders:** {len(rows)}  ·  "
        "method & column definitions at the end.\n\n"
    )


def write_status_summary(fh, counts):
    fh.write(GOAL)
    fh.write("### Status labels\n\n")
    fh.write("| label | count | meaning |\n")
    fh.write("|---|---:|---|\n")
    for label, defn in LEGEND:
        fh.write(f"| {label} | {counts.get(label, 0)} | {defn} |\n")
    fh.write("\n")


def write_dupes_section(fh, project, rows):
    # --- Duplicate rows -------------------------------------------------
    # Kept SEPARATE from the status groups above on purpose: duplication is
    # orthogonal to coverage/extraction. `status` is one-per-spider and
    # mutually exclusive, so folding dupes in there would mask a spider's
    # real group (e.g. an "incomplete" spider that also has dupes would vanish
    # from the incomplete table). So it's its own axis: this section flags it,
    # and the all-spiders table adds a column.
    dups = sorted(
        (r for r in rows if r["true_dupes"] > 0),
        key=lambda r: r["true_dupes"],
        reverse=True,
    )
    fh.write(f"### Duplicate rows ({len(dups)})\n\n")
    if not dups:
        fh.write(
            "None — no spider has identical rows repeated (same URL **and** "
            "same content).\n\n"
        )
    else:
        fh.write(DUPES_EXPLAINER)
        fh.write(
            "| spider | files | rows | unique | true dupes | dup% | versions "
            "| pdf multi-ref |\n"
        )
        fh.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in dups:
            fh.write(
                f"| {r['spider']} | {r['files']} | {r['rows']} | "
                f"{r.get('unique', r['scraped'])} | {r['true_dupes']} | "
                f"{r['dup_pct']}% | {r['versions']} | {r.get('pdf_multi', 0)} |\n"
            )
        ex = dups[0]["spider"]  # worst offender — used in the example below
        fh.write(DUPES_CAUSE)
        fh.write(DEDUPE_FIX)
        fh.write("```bash\n")
        fh.write(
            f"./scrapai dedupe --project {project}" "              # all spiders\n"
        )
        fh.write(
            f"./scrapai dedupe --project {project} --only {ex}" "   # one spider\n"
        )
        fh.write("```\n\n")
        fh.write(
            "**After deduping, resume WITHOUT `--reset-deltafetch`** "
            f"(`./scrapai crawl --project {project} {ex}`) — DeltaFetch appends "
            "only new records, so it can't reintroduce the duplicates you just "
            "removed; `--reset-deltafetch` would re-append a full copy.\n\n"
        )


def write_table(fh, rowlist, with_status, with_dupes=False):
    head = "| spider | sitemap | total | eligible |"
    sep = "|---|---|---:|---:|"
    head += " scraped | pdf |"
    sep += "---:|---:|"
    if with_dupes:
        head += " true dupes | versions |"
        sep += "---:|---:|"
    head += " content% | coverage | stale | flags |"
    sep += "---:|---:|---|---|"
    if with_status:
        head += " status |"
        sep += "---|"
    fh.write(head + "\n" + sep + "\n")
    for r in rowlist:
        cov = "" if r["coverage_pct"] == "" else f"{r['coverage_pct']}%"
        line = (
            f"| {r['spider']} | {r['sitemap']} | {r['sitemap_total']} | "
            f"{r['eligible']} |"
        )
        line += f" {r['scraped']} |"
        pdf = r.get("pdf", 0)
        line += f" {pdf} ({r.get('pdf_ext', 0)} ext) |" if pdf else " |"
        if with_dupes:
            line += (
                f" {r['true_dupes']} ({r['dup_pct']}%) |" if r["true_dupes"] else " 0 |"
            )
            line += f" {r['versions']} |" if r["versions"] else " 0 |"
        # a pdf-only spider has no HTML to extract — a "0%" here would read as
        # broken extraction, so the cell stays empty (the pdf-only flag explains)
        cpct = f"{r['content_pct']}%" if r["scraped"] else ""
        line += f" {cpct} | {cov} | {r.get('stale', '')} | " f"{r.get('flags', '')} |"
        if with_status:
            line += f" {r['status']} |"
        fh.write(line + "\n")


def write_group_tables(fh, project, srt):
    # per-table fix instruction — the most likely remedy for that problem group
    fix_hint = fix_hints(project)
    # one table per present label, in legend order (skip empty labels)
    for label, _ in LEGEND:
        cat = [r for r in srt if r["status"] == label]
        if not cat:
            continue
        fh.write(f"## {label} ({len(cat)})\n\n")
        if label in fix_hint:
            fh.write(fix_hint[label] + "\n\n")
        write_table(fh, cat, with_status=False)
        fh.write("\n")


def write_notes_definitions(fh):
    # ---- definitions / how everything is calculated --------------------
    fh.write("\n## Notes & definitions\n\n")
    fh.write(NOTES_AND_DEFINITIONS)


def write_all_spiders(fh, srt):
    # full overview table, all spiders alphabetical — kept at the very end as a
    # master reference (the grouped tables above are the actionable view).
    fh.write(f"\n## all spiders ({len(srt)})\n\n")
    write_table(fh, srt, with_status=True, with_dupes=True)


def write_outputs(project, rows, config_warnings=(), compliance=None):
    out = audit_dir(project)
    write_csvs(out, rows)

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    srt = sorted(rows, key=lambda r: r["spider"].lower())

    with open(os.path.join(out, f"audit_{project}.md"), "w") as fh:
        write_header(fh, project, rows, config_warnings)
        write_status_summary(fh, counts)
        write_dupes_section(fh, project, rows)
        write_group_tables(fh, project, srt)
        write_notes_definitions(fh)

        # ---- Compliance section (robots / licence / AI) — a separate axis from
        #      coverage/extraction; full evidence + cross-check live in compliance_<project>.md.
        if compliance:
            write_compliance_section(fh, project, compliance)

        write_all_spiders(fh, srt)


def write_compliance_section(fh, project, compliance):
    """The dedicated ## Compliance block in the audit md — ≤7 columns, one attention column,
    most-restrictive first. The full evidence, quoted clauses and crawl-vs-independent
    cross-check are in `compliance_<project>.md` (this is the at-a-glance summary)."""
    checked = {
        n: e
        for n, e in compliance.items()
        if e.get("checked") is not None or e.get("failed")
    }
    fh.write(f"\n## Compliance — robots / licence / AI ({len(checked)} checked)\n\n")
    failed = [e for e in compliance.values() if e.get("failed")]
    if failed:
        fh.write(
            "> ‼️ **Compliance capture failed — needs investigation:** "
            + ", ".join(f"`{e['domain']}`" for e in failed)
            + ". Skipped on future audits until fixed — rerun "
            "`./scrapai audit --refresh` to retry.\n\n"
        )
    if not checked:
        fh.write(
            "No domains captured yet. Run `./scrapai audit --project "
            f"{project}` — the audit captures new domains inline.\n\n"
        )
        return
    fh.write(
        "Two co-equal axes — **access** (may we fetch?) and **reuse** (may it enter the "
        "corpus?). Lead emoji = worst of the two. 🔴 blocked/reserved · 🟡 review · 🟢 "
        "open/permissive · ⚪ no grant · 🔎 unverifiable · ❓ not checked. `notes`: ⚠ "
        "conflict (crawl-vs-independent), AI-scrape / AI-reuse (MR = machine-readable, "
        "ToS = legal-only), llms✓/llms✗, check-behind-crawl. **Full evidence, quoted "
        f"clauses and the cross-check:** `_audit/compliance_{project}.md`.\n\n"
    )
    fh.write("| | spider | checked | access | reuse | licence | notes |\n")
    fh.write("|---|---|---|---|---|---|---|\n")

    def cell(x):
        return "—" if x in (None, "", "unknown") else str(x).replace("|", "\\|")

    for name in sorted(
        checked, key=lambda n: (_COMPL_SEV.get(compl_lead(checked[n]), 5), n)
    ):
        e = checked[name]
        fh.write(
            f"| {compl_lead(e)} | {name} | {cell(e.get('checked')) if not e.get('failed') else '‼️ failed'} "
            f"| {e.get('access') or '❓'} | {e.get('reuse') or '❓'} | "
            f"{cell(e.get('license'))} | {cell(compl_notes(e))} |\n"
        )
    fh.write("\n")
