#!/usr/bin/env python3
"""Deduplicate crawl output for every spider in a project.

Duplicate rows pile up when a crawl is re-run with `--reset-deltafetch` (the
date-named `crawl_DDMMYYYY.jsonl` is opened in *append* mode, so each re-run
appends another full copy) or across multiple full runs / overlapping files.

This consolidates each spider's `crawls/*.jsonl` into ONE file. Every source
file is first renamed aside as `*.superseded` (a rename, not a full copy), then
the deduped result is written fresh to the newest file's name. No `*.bak` copy is
made. Re-running overwrites the same-named `*.superseded` shadows in place, so
backups never accumulate — and nothing is auto-deleted.

Two dedupe modes:
  default        — key = URL + content-fingerprint. Collapses identical
                   re-scrapes (re-run artifacts) but KEEPS genuinely-changed
                   versions of a page (so re-fetching for changed content via
                   --reset-deltafetch stays safe / lossless).
  --latest-only  — key = URL. Keeps only the newest row per URL, dropping older
                   versions. Use when you only want a current snapshot.

Records with no URL (or malformed lines) are always kept verbatim under a
per-line key, so they're never treated as duplicates of each other.

Usage:
  ./scrapai dedupe --project policy                 # url+content dedupe
  ./scrapai dedupe --project policy --latest-only   # keep newest row per URL
  ./scrapai dedupe --project policy --only energy_gov   # one spider only

Writes immediately (no dry-run) — but it's reversible:
  - all source files are preserved as *.superseded (renamed aside, not deleted)
    before the consolidated file is written fresh, so the originals survive
  - re-running overwrites the same-named *.superseded shadow (os.replace); backups
    never accumulate and nothing is auto-deleted
  - idempotent: a spider that's already a single clean file is skipped
  - *.superseded files are ignored (they don't match *.jsonl)
"""

import argparse
import glob
import json
import os

from core.quality._env import DATA_DIR
from core.quality.corpus import fingerprint as _fingerprint


def spider_dirs(project, only):
    root = os.path.join(DATA_DIR, project)
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        if only and name not in only:
            continue
        yield name, d


def crawl_files(spider_dir):
    """crawls/*.jsonl, oldest->newest by mtime (so last-wins = most recent)."""
    fs = glob.glob(os.path.join(spider_dir, "crawls", "*.jsonl"))
    return sorted(fs, key=os.path.getmtime)


# The content fingerprint (and its VOLATILE exclusion set) comes from
# core.quality.corpus — the ONE definition shared with the audit, so the report's
# "true dupes" always equals what this collapses.


def dedupe(files, latest_only=False):
    """Return (total_rows, {key: line}); latest occurrence kept per key.

    latest_only=False (default): key = (url, fingerprint) — collapses identical
      re-scrapes but keeps genuinely-changed versions of a URL.
    latest_only=True: key = url — newest row per URL, drops older versions.
    No-URL / unparseable rows are always kept (unique per-line key).
    """
    uniq = {}  # key -> line (dict preserves first-seen order)
    n = 0  # row counter: the returned total AND the unique-key suffix
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.rstrip("\n")
                if not s.strip():
                    continue
                n += 1
                try:
                    rec = json.loads(s)
                except json.JSONDecodeError:
                    uniq[f"__bad__{n}"] = s  # keep malformed verbatim
                    continue
                url = rec.get("url")
                if not url:
                    uniq[f"__noURL__{n}"] = s
                elif latest_only:
                    uniq[url] = s  # last wins → newest
                else:
                    uniq[(url, _fingerprint(rec))] = s  # keep distinct versions
    return n, uniq


def run(project, opts):
    """Consolidate & dedupe each spider's crawl output for `project`. Performs the
    `.superseded` renames + consolidated writes, prints progress, and RETURNS a structured
    summary: {mode, fixed, total_dupes, spiders: [{spider, files, rows, unique, dupes,
    dup_pct, written}, ...]}. `opts` supplies `.only` (iterable of spider names or None)
    and `.latest_only` (bool)."""
    only = set(opts.only) if getattr(opts, "only", None) else None
    latest_only = getattr(opts, "latest_only", False)

    mode = (
        "latest-only (newest row per URL)"
        if latest_only
        else "url+content (keep changed versions, collapse identical re-scrapes)"
    )
    print(f"dedupe mode: {mode}\n")

    results = []
    fixed = total_dupes = 0
    for name, d in spider_dirs(project, only):
        files = crawl_files(d)
        if not files:
            continue
        total, uniq = dedupe(files, latest_only=latest_only)
        unique = len(uniq)
        dupes = total - unique
        if dupes <= 0:
            continue
        fixed += 1
        total_dupes += dupes
        newest = files[-1]
        print(
            f"\n{name}: {total} rows -> {unique} unique "
            f"({dupes} dupes, {100 * dupes / total:.0f}%) across {len(files)} file(s)"
        )
        print(f"  write  -> {os.path.basename(newest)}  ({unique} rows, consolidated)")
        for o in files:
            print(f"  aside  -> {os.path.basename(o)}.superseded")
        # Rename every source file aside as *.superseded (os.replace overwrites any
        # same-named shadow from a prior run, so backups don't accumulate), then write
        # the consolidated result fresh to the newest file's (now-freed) name.
        for o in files:
            os.replace(o, o + ".superseded")
        with open(newest, "w", encoding="utf-8") as fh:
            fh.writelines(s + "\n" for s in uniq.values())
        print("  done (originals kept as *.superseded)")
        results.append(
            {
                "spider": name,
                "files": len(files),
                "rows": total,
                "unique": unique,
                "dupes": dupes,
                "dup_pct": round(100 * dupes / total),
                "written": os.path.basename(newest),
            }
        )

    print()
    if fixed == 0:
        print(f"No duplicate rows in any '{project}' spider. Nothing to do.")
    else:
        print(f"Fixed {fixed} spider(s), removed {total_dupes} duplicate rows.")
    return {
        "mode": mode,
        "fixed": fixed,
        "total_dupes": total_dupes,
        "spiders": results,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Consolidate & dedupe each spider's crawl output in a project."
    )
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", nargs="+", help="restrict to these spider names")
    ap.add_argument(
        "--latest-only",
        action="store_true",
        help="keep only the newest row per URL (drop older versions); "
        "default keeps distinct-content versions and collapses "
        "only identical re-scrapes",
    )
    args = ap.parse_args()
    run(args.project, args)


if __name__ == "__main__":
    main()
