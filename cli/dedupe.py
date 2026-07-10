"""Dedupe command — consolidate & dedupe a project's crawl output.

MUTATING and deliberate: kept SEPARATE from `audit` so a read-only "show me quality" run
can never silently rewrite your data. The audit surfaces which spiders have duplicates and
the exact command; running it is always this explicit, separate call.

Reversible: every source file is renamed aside as `*.superseded` before the consolidated
file is written; re-running overwrites the same shadow (backups never accumulate) and
nothing is auto-deleted.
"""

from types import SimpleNamespace

import click

from core.quality import dedupe as dedupe_engine
from core.quality.crawl_audit import project_exists


@click.command()
@click.option("--project", "-p", required=True, help="Project name (required)")
@click.option(
    "--only", multiple=True, help="restrict to these spider names (repeatable)"
)
@click.option(
    "--latest-only",
    is_flag=True,
    help="keep only the newest row per URL (drop older versions); default keeps "
    "distinct-content versions and collapses only identical re-scrapes",
)
def dedupe(project, only, latest_only):
    """Consolidate & dedupe each spider's crawls/*.jsonl into one file (reversible).

    Default keys on URL + content fingerprint: collapses identical re-scrapes but keeps
    genuinely-changed versions of a page. --latest-only keeps just the newest row per URL.

    Examples:
        ./scrapai dedupe --project gscc
        ./scrapai dedupe --project gscc --only rmi_org
        ./scrapai dedupe --project policy --latest-only
    """
    if not project_exists(project):
        raise click.ClickException(
            f"No project named '{project}'. Dedupe only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects. Nothing was created."
        )

    opts = SimpleNamespace(only=list(only) or None, latest_only=latest_only)
    dedupe_engine.run(project, opts)
