"""ScrapAI CLI - click-based command interface."""

import click

from .spiders import spiders
from .queue import queue
from .show import show
from .export import export
from .crawl import crawl, crawl_all
from .db import db
from .inspect_cmd import inspect_cmd
from .analyze import analyze
from .setup_cmd import setup, verify
from .extract_urls import extract_urls
from .projects import projects


@click.group()
def cli():
    """ScrapAI - AI-powered web scraping CLI"""
    pass


cli.add_command(spiders)
cli.add_command(queue)
cli.add_command(show)
cli.add_command(export)
cli.add_command(crawl)
cli.add_command(crawl_all, 'crawl-all')
cli.add_command(db)
cli.add_command(inspect_cmd, 'inspect')
cli.add_command(analyze)
cli.add_command(setup)
cli.add_command(verify)
cli.add_command(extract_urls, 'extract-urls')
cli.add_command(projects)
