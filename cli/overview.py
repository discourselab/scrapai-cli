"""Overview command — a read-only content profile of every spider in a project.

`./scrapai overview --project <p>` summarises what each spider ACTUALLY collected — sections,
publication date span + null %, per-field coverage, thin/constant/off-domain checks — so you can
judge whether a scrape faithfully mirrors the source site WITHOUT opening the raw crawls/*.jsonl.

Complementary to `./scrapai audit` (which covers coverage-vs-sitemap and duplicates); this one
never recomputes those. Strictly read-only — it never modifies any crawl file.
"""

from types import SimpleNamespace

import click

from core.quality import overview as overview_engine
from core.quality.crawl_audit import project_exists
from core.quality.overview_dashboard import write_overview_dashboard


@click.command()
@click.option("--project", "-p", required=True, help="Project name (required)")
@click.option(
    "--only", multiple=True, help="restrict to these spider names (repeatable)"
)
@click.option(
    "--thin-chars",
    type=int,
    default=200,
    show_default=True,
    help="content shorter than this many chars counts as a 'thin' (likely "
    "listing/nav) item",
)
@click.option("--no-html", is_flag=True, help="skip building the HTML dashboard")
def overview(project, only, thin_chars, no_html):
    """Per-spider content profile for a project (sections · dates · field coverage).

    Writes overview_<project>.md + .csv under data/<project>/_audit/ and builds an HTML
    dashboard (overview_<project>.html) unless --no-html.

    Examples:
        ./scrapai overview --project thinktanks
        ./scrapai overview --project policy --only rstreet_org
        ./scrapai overview --project gscc --thin-chars 300 --no-html
    """
    if not project_exists(project):
        raise click.ClickException(
            f"No project named '{project}'. Overview only runs on an existing project. "
            f"Run `./scrapai projects list` to see existing projects. Nothing was created."
        )

    opts = SimpleNamespace(only=list(only) or None, thin_chars=thin_chars)
    result = overview_engine.run(project, opts)

    click.echo(f"Report → {result['report_path']}")
    if not no_html:
        path = write_overview_dashboard(project, result)
        click.echo(f"Dashboard → {path}")
        click.echo(
            "  open it in a browser; click a spider row to see its date histogram, "
            "field-coverage bars, and sample titles."
        )
