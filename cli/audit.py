"""Quality-audit command — one read-only view of a project's crawl corpus.

`./scrapai audit --project <p>` runs three lenses over `data/<project>/` and builds a
self-contained HTML dashboard:
  - coverage + extraction quality (did we get the whole site? did extraction work?)
  - compliance (robots / licence / AI — may we crawl? may we reuse?)
  - external-PDF host frequency (where the external PDFs come from)

The audit is READ-ONLY. The one mutating step — dedupe — is a SEPARATE command
(`./scrapai dedupe`); the audit only *surfaces* it (flags dupey spiders + a copy-paste
command in the dashboard). This is deliberate: a "show me quality" command must never
silently rewrite your data.
"""

from types import SimpleNamespace

import click

from core.quality import crawl_audit, external_pdf
from core.quality.dashboard import write_dashboard


@click.command()
@click.option("--project", "-p", required=True, help="Project name (required)")
@click.option(
    "--no-compliance",
    is_flag=True,
    help="skip the compliance stage entirely (read existing snapshots only; "
    "fast, zero network)",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="re-capture compliance for domains that already have a snapshot "
    "(appends a new dated snapshot, keeping history)",
)
@click.option(
    "--reset",
    is_flag=True,
    help="re-capture compliance, OVERWRITING prior dated snapshots (no history)",
)
@click.option(
    "--no-fetch",
    is_flag=True,
    help="never fetch sitemaps; use only cached files + crawl-recorded counts",
)
@click.option(
    "--fetch-all",
    is_flag=True,
    help="re-fetch every spider's sitemap (refresh the cache); default fetches "
    "only spiders with no cached sitemap yet",
)
@click.option(
    "--only", multiple=True, help="restrict to these spider names (repeatable)"
)
@click.option(
    "--no-cache",
    is_flag=True,
    help="ignore the per-file crawl-scan cache and re-read every crawls/*.jsonl",
)
@click.option(
    "--per-cap",
    type=int,
    default=80,
    show_default=True,
    help="max sitemap fetches per spider",
)
@click.option(
    "--global-cap",
    type=int,
    default=2000,
    show_default=True,
    help="max sitemap fetches overall",
)
@click.option(
    "--no-browser-retry",
    is_flag=True,
    help="do not retry failed sitemap fetches with --browser",
)
@click.option("--no-html", is_flag=True, help="skip building the HTML dashboard")
def audit(
    project,
    no_compliance,
    refresh,
    reset,
    no_fetch,
    fetch_all,
    only,
    no_cache,
    per_cap,
    global_cap,
    no_browser_retry,
    no_html,
):
    """Read-only quality audit for a project (coverage · compliance · external PDFs).

    Writes the per-lens markdown/CSV under data/<project>/_audit/ and builds an HTML
    dashboard (data/<project>/_audit/dashboard_<project>.html) unless --no-html.

    First run with no compliance cache fetches every domain's robots/legal pages via
    ./scrapai inspect (can take minutes); subsequent runs read the cache. Use
    --no-compliance to skip it, or --refresh / --reset to re-capture.

    Examples:
        ./scrapai audit --project gscc
        ./scrapai audit --project policy_CARDS --no-compliance --no-html
        ./scrapai audit --project gscc --refresh
    """
    if not crawl_audit.project_exists(project):
        raise click.ClickException(
            f"No project named '{project}'. The audit only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects. Nothing was created."
        )

    opts = SimpleNamespace(
        no_fetch=no_fetch,
        fetch_all=fetch_all,
        per_cap=per_cap,
        global_cap=global_cap,
        no_browser_retry=no_browser_retry,
        only=list(only) or None,
        no_cache=no_cache,
        # --reset implies a re-capture too (overwrite the existing snapshots)
        refresh_compliance=refresh or reset,
        no_compliance=no_compliance,
        reset=reset,
    )

    audit_result = crawl_audit.run(project, opts)
    pdf_result = external_pdf.run(project, SimpleNamespace(only=None))

    if not no_html:
        path = write_dashboard(project, audit_result, pdf_result)
        click.echo(f"\nDashboard → {path}")
        click.echo(
            "  open it in a browser; dupey spiders show a copy-paste "
            "`./scrapai dedupe` command (dedupe is never run from the dashboard)."
        )
