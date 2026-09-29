"""Repo-environment resolution shared by the quality engines.

The engines shell out to the `./scrapai` CLI and read repo-level files
(`settings.py`, `.scrapy/`). Resolving those relative to the *current working
directory* made every one of them silently wrong when imported from anywhere
but the repo root (cron, tests, another service): fetches returned None, the
robots user-agent fell back to `*`, and `db_query` returned [] for real
projects. Everything here is anchored to `core.config.project_root` instead,
and subprocesses always run with that as their cwd (the CLI itself resolves a
relative DATA_DIR against ITS cwd, so pinning it keeps parent and child in
agreement).

`db_query` fails LOUDLY: the `scrapai db query` command prints errors to
stdout with exit code 0 and `(no results)` for an empty result set, so exit
codes alone can't distinguish "empty" from "broken". A broken DB must raise —
never masquerade as "no spiders" and let a caller overwrite a good report
with an empty one.
"""

import json
import os
import re
import subprocess

from core.config import DATA_DIR as _RAW_DATA_DIR, project_root

SCRAPAI = str(project_root / "scrapai")
SETTINGS_PY = str(project_root / "settings.py")
SCRAPY_DIR = str(project_root / ".scrapy")
# DATA_DIR defaults to the RELATIVE "./data" (core/config.py), which resolves against
# the process cwd — from any other directory the engines would silently read/write a
# stray <cwd>/data tree. A relative value in .env clearly means repo-relative, so it
# is anchored to the repo root here; an absolute value passes through unchanged. The
# quality modules import DATA_DIR from THIS module, never from core.config directly.
DATA_DIR = (
    _RAW_DATA_DIR if os.path.isabs(_RAW_DATA_DIR) else str(project_root / _RAW_DATA_DIR)
)


class ScrapaiCliError(RuntimeError):
    """The ./scrapai subprocess failed (distinct from an empty result)."""


def run_scrapai(args, timeout=None):
    """Run `./scrapai <args>` from the repo root, capturing output."""
    return subprocess.run(
        [SCRAPAI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(project_root),
    )


def db_query(sql):
    """Run a read-only query through the scrapai CLI; return a list of row dicts.

    Returns [] ONLY for a genuinely empty result set. Any CLI failure —
    non-zero exit, an error printed to stdout, unparseable output — raises
    ScrapaiCliError so callers can abort instead of proceeding on false
    emptiness.
    """
    out = run_scrapai(["db", "query", sql, "--format", "json"])
    txt = (out.stdout or "").strip()
    if out.returncode != 0:
        raise ScrapaiCliError(
            f"scrapai db query exited {out.returncode}: "
            f"{(out.stderr or txt).strip()[:400]}"
        )
    if "(no results)" in txt:
        return []
    if "❌" in txt:  # cli/db.py prints errors on stdout, exit 0
        raise ScrapaiCliError(f"scrapai db query failed: {txt[:400]}")
    # The JSON may be preceded by log lines (some containing '[' — e.g. [INFO]),
    # so try each line-leading bracket until one parses.
    for m in re.finditer(r"^\s*[\[{]", txt, re.M):
        start = m.start()
        try:
            return json.loads(txt[start:])
        except json.JSONDecodeError:
            continue
    raise ScrapaiCliError(f"unparseable db query output: {txt[:200]!r}")


def project_exists(project):
    """True if the project actually exists: its project.json is present, OR it has at
    least one spider or queued URL in the DB (project.json covers freshly-created,
    not-yet-built projects; the DB covers established ones — same set as
    `./scrapai projects list`). The quality tools must NOT run on an unknown name:
    doing so would spawn an empty data/<project>/ folder and a blank report.
    """
    if os.path.exists(os.path.join(DATA_DIR, project, "project.json")):
        return True
    p = project.replace("'", "''")
    if db_query(f"SELECT 1 FROM spiders WHERE project='{p}' LIMIT 1"):
        return True
    return bool(db_query(f"SELECT 1 FROM crawl_queue WHERE project_name='{p}' LIMIT 1"))
