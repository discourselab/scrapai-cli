#!/usr/bin/env python3
"""
Page Inspector Utility

This tool downloads and analyzes HTML from a source URL to help with creating scrapers.
It's designed to be used as part of the scraper development process.

Supports three modes:
- HTTP (default): Lightweight aiohttp fetch for most sites
- Browser: Playwright for JS-rendered sites
- Cloudflare: CloakBrowser for Cloudflare-protected sites

Usage:
    python -m utils.inspector https://example.com/fact-checks
"""

import os
import argparse
import asyncio
import aiohttp
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from core.config import DATA_DIR
from settings import USER_AGENT


async def inspect_page_async(
    url,
    output_dir=None,
    proxy_type="auto",
    save_html=True,
    mode="http",
    project="default",
):
    """
    Inspect a page and output analysis to help with creating a scraper

    Args:
        url (str): URL to inspect
        output_dir (str): Directory to save analysis and HTML. If None, a directory is created based on the domain
        proxy_type (str): Proxy type to use (unused now, browser handles this)
        save_html (bool): Whether to save the full HTML
        mode (str): Fetch mode - 'http' (default) or 'browser' (CloakBrowser for JS + Cloudflare)
        project (str): Project name for organizing analysis files (default: "default")

    Returns:
        dict: Analysis results
    """
    print(f"Inspecting: {url}")
    if mode == "browser":
        print("Using CloakBrowser (JS rendering + Cloudflare bypass)...")
    else:
        print("Using lightweight HTTP fetch...")

    # Extract domain for folder name if output_dir is not specified
    if output_dir is None:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "")

        # Check if this is a Wayback Machine URL
        if domain == "web.archive.org":
            # Parse Wayback Machine URL structure:
            # https://web.archive.org/web/YYYYMMDDHHMMSS/http://original-domain.com/path
            import re

            wayback_pattern = r"/web/(\d{8})\d*/(?:https?://)?(?:www\.)?([^/]+)"
            match = re.search(wayback_pattern, url)

            if match:
                timestamp = match.group(1)  # 8-digit date (YYYYMMDD)
                original_domain = match.group(2).replace(".", "_").replace(":", "_")
                output_dir = str(
                    Path(DATA_DIR)
                    / project
                    / "web_archive_org"
                    / original_domain
                    / timestamp
                    / "analysis"
                )
            else:
                # Fallback if pattern doesn't match
                output_dir = str(
                    Path(DATA_DIR) / project / "web_archive_org" / "analysis"
                )
        else:
            source_id = domain.replace(".", "_")
            output_dir = str(Path(DATA_DIR) / project / source_id / "analysis")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Fetch HTML based on mode
    html_content = None

    if mode == "browser":
        # Use CloakBrowser for JS rendering and Cloudflare bypass
        # Always headed mode (headless=False) for best stealth
        from utils.cf_browser import CloudflareBrowserClient

        async with CloudflareBrowserClient(headless=False) as browser:
            html_content = await browser.fetch(url)

            if not html_content:
                print(f"Failed to fetch page: {url}")
                return None

    else:
        # Mode 1: Use lightweight HTTP fetch (default)
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            headers = {"User-Agent": USER_AGENT}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=timeout
                ) as response:
                    if response.status != 200:
                        print(f"HTTP {response.status} - {url}")
                        print(
                            "Hint: Try --browser for JS-rendered or Cloudflare-protected sites"
                        )
                        return None

                    html_content = await response.text()

        except aiohttp.ClientError as e:
            print(f"Failed to fetch page: {e}")
            print(
                "Hint: Try --browser for JS-rendered or Cloudflare-protected sites"
            )
            return None
        except asyncio.TimeoutError:
            print(f"Request timed out: {url}")
            return None

    # Save the HTML if requested
    if save_html and html_content:
        html_file = os.path.join(output_dir, "page.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Saved HTML to: {html_file}")

    # Parse and analyze the HTML
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.title.text if soup.title else "No title"
        print(f"\nTitle: {title}")
        print(f"HTML size: {len(html_content)} bytes")


def inspect_page(
    url,
    output_dir=None,
    proxy_type="auto",
    save_html=True,
    mode="http",
    project="default",
):
    """
    Synchronous wrapper for inspect_page_async

    Args:
        url (str): URL to inspect
        output_dir (str): Directory to save analysis and HTML
        proxy_type (str): Proxy type to use (unused)
        save_html (bool): Whether to save the full HTML
        mode (str): Fetch mode - 'http' (default) or 'browser' (CloakBrowser)
        project (str): Project name for organizing analysis files

    Returns:
        dict: Analysis results
    """
    return asyncio.run(
        inspect_page_async(url, output_dir, proxy_type, save_html, mode, project)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a page to help with creating a scraper"
    )
    parser.add_argument("--url", type=str, required=True, help="URL to inspect")
    parser.add_argument(
        "--output-dir", type=str, default=None, help="Directory to save analysis"
    )
    parser.add_argument(
        "--proxy-type",
        choices=["none", "static", "residential", "auto"],
        default="auto",
        help="Proxy type to use",
    )
    parser.add_argument(
        "--no-save-html", action="store_true", help="Do not save the full HTML"
    )

    args = parser.parse_args()

    inspect_page(args.url, args.output_dir, args.proxy_type, not args.no_save_html)


if __name__ == "__main__":
    main()
