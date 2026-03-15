"""ScrapAI CLI Application.

This module provides the Click-based CLI entrypoint for ScrapAI.
It can be used as: python -m scrapai.cli_app <command>
"""

import click

from cli.setup_cmd import setup, verify
from cli.crawl import crawl, crawl_all
from cli.spiders import spiders
from cli.show import show
from cli.export import export
from cli.db import db
from cli.health import health
from cli.queue import queue
from cli.add import add
from cli.projects import projects
from cli.inspect_cmd import inspect_cmd
from cli.analyze import analyze
from cli.extract_urls import extract_urls


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """ScrapAI - AI-powered web scraping with database-first approach."""
    pass


cli.add_command(setup)
cli.add_command(verify)
cli.add_command(crawl)
cli.add_command(crawl_all)
cli.add_command(spiders)
cli.add_command(show)
cli.add_command(export)
cli.add_command(db)
cli.add_command(health)
cli.add_command(queue)
cli.add_command(add)
cli.add_command(projects)
cli.add_command(inspect_cmd)
cli.add_command(analyze)
cli.add_command(extract_urls)


if __name__ == "__main__":
    cli()
