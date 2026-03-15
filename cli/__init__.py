"""ScrapAI CLI - click-based command interface."""

import click
import sys
import os

# Add parent directory to path to import __version__
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from __version__ import __version__  # noqa: E402

from .spiders import spiders  # noqa: E402
from .queue import queue  # noqa: E402
from .show import show  # noqa: E402
from .export import export  # noqa: E402
from .crawl import crawl, crawl_all  # noqa: E402
from .db import db  # noqa: E402
from .inspect_cmd import inspect_cmd  # noqa: E402
from .analyze import analyze  # noqa: E402
from .setup_cmd import setup, verify  # noqa: E402
from .extract_urls import extract_urls  # noqa: E402
from .projects import projects  # noqa: E402
from .health import health  # noqa: E402
from .add import add  # noqa: E402


@click.group()
@click.version_option(version=__version__, prog_name="scrapai")
def cli():
    """ScrapAI - AI-powered web scraping CLI"""
    pass


cli.add_command(spiders)
cli.add_command(queue)
cli.add_command(show)
cli.add_command(export)
cli.add_command(crawl)
cli.add_command(crawl_all, "crawl-all")
cli.add_command(db)
cli.add_command(inspect_cmd, "inspect")
cli.add_command(analyze)
cli.add_command(setup)
cli.add_command(verify)
cli.add_command(extract_urls, "extract-urls")
cli.add_command(projects)
cli.add_command(health)
cli.add_command(add)
