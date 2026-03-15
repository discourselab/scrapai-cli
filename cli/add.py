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
@click.option(
    "--llm-api",
    envvar="SCRAPAI_LLM_API",
    default="https://api.openai.com/v1",
    help="LLM API base URL (or set SCRAPAI_LLM_API)",
)
@click.option(
    "--llm-key",
    envvar="SCRAPAI_LLM_KEY",
    help="LLM API key (or set SCRAPAI_LLM_KEY)",
)
@click.option(
    "--llm-model",
    envvar="SCRAPAI_LLM_MODEL",
    help="LLM model name (or set SCRAPAI_LLM_MODEL)",
)
@click.option(
    "--llm-timeout",
    envvar="SCRAPAI_LLM_TIMEOUT",
    type=int,
    default=30,
    help="Per-call LLM timeout in seconds (default: 30)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Skip DB write and test crawl; only print generated JSON",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Write generated JSON to file",
)
@click.option(
    "--backup/--no-backup",
    default=True,
    help="Backup existing spider before overwrite (default: true)",
)
@click.option(
    "--skip-test-crawl",
    is_flag=True,
    help="Skip Phase 4 test crawl (use with --dry-run)",
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
    skip_test_crawl,
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
            skip_test_crawl=skip_test_crawl,
        )
    )

    if not result.success:
        click.echo("❌ Spider generation failed")
        if result.error:
            click.echo(result.error)
        raise SystemExit(1)
