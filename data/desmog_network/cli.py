#!/usr/bin/env python3
"""Run the DeSmog network pipeline in the correct order.

Each stage is also runnable on its own (e.g. `python3 geocode_entities.py`);
this is just the single entry point that chains them.

Stages:
  scrape    scrape DeSmog profiles  -> entities.jsonl, relationships.jsonl
  type      classify relationships  -> relationships_typed.{jsonl,csv}
  locate    run every location pass  -> locations.jsonl + *_overrides.jsonl
            (geocode -> wikidata strict -> wikidata loose -> affiliation -> address)
  build     build the dashboard     -> dashboard.html
  all       type -> locate -> build  (works from already-scraped data)

Extra arguments are passed through for single-script stages only, e.g.
  python3 cli.py scrape --limit 5
  python3 cli.py all

Scrape is intentionally NOT part of `all` (it is the one heavy network step
and is normally run once).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STAGES = {
    "scrape": ["scrape_climate_disinfo.py"],
    "type": ["type_relationships.py"],
    "locate": ["geocode_entities.py", "wikidata_locations.py",
               "wikidata_loose_locations.py", "affiliation_locations.py",
               "address_locations.py"],
    "build": ["build_dashboard.py"],
}
STAGES["all"] = STAGES["type"] + STAGES["locate"] + STAGES["build"]


def run(script, extra=()):
    cmd = [sys.executable, str(HERE / script), *extra]
    print(f"\n==> {' '.join([script, *extra])}".rstrip(), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"stage failed: {script} (exit {r.returncode})")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in STAGES:
        print(__doc__)
        print("stages:", ", ".join(STAGES))
        return 0 if argv and argv[0] in ("-h", "--help") else 1
    stage, extra = argv[0], argv[1:]
    scripts = STAGES[stage]
    if extra and len(scripts) != 1:
        sys.exit(f"'{stage}' chains {len(scripts)} scripts; pass-through args "
                 f"are only allowed for single-script stages")
    for s in scripts:
        run(s, extra if len(scripts) == 1 else ())
    return 0


if __name__ == "__main__":
    sys.exit(main())
