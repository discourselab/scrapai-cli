import asyncio
from pathlib import Path

import click

from generate.pipeline import resolve_llm_config, run_add_pipeline


@click.command()
@click.argument("url")
@click.option("--project", required=True, help="Project name")
@click.option(
    "--description",
    required=True,
    help="Natural language extraction goal (required)",
)
@click.option("--llm-api", default=None, help="LLM API base URL")
@click.option("--llm-key", default=None, help="LLM API key")
@click.option("--llm-model", default=None, help="LLM model name")
@click.option(
    "--llm-timeout",
    type=int,
    default=None,
    help="Per-call LLM timeout in seconds (default: 30)",
)
@click.option("--dry-run", is_flag=True, help="Skip DB write and test crawl")
@click.option("--output", default=None, help="Write JSON to file")
@click.option(
    "--backup/--no-backup",
    default=True,
    help="Backup existing spider before overwrite (default: true)",
)
def add(
    url,
    project,
    description,
    llm_api,
    llm_key,
    llm_model,
    llm_timeout,
    dry_run,
    output,
    backup,
):
    """Generate and import a spider config using an LLM."""
    try:
        primary = resolve_llm_config(llm_api, llm_key, llm_model, llm_timeout)
    except ValueError as exc:
        click.echo(f"❌ {exc}")
        raise SystemExit(1)

    output_path = Path(output) if output else None

    result = asyncio.run(
        run_add_pipeline(
            url=url,
            project=project,
            description=description,
            llm=primary,
            dry_run=dry_run,
            output_path=output_path,
            backup=backup,
        )
    )

    if not result.success:
        click.echo("❌ Spider generation failed")
        if result.error:
            click.echo(result.error)
        raise SystemExit(1)
