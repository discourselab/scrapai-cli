#!/usr/bin/env python3
"""
Page Inspector Utility

This tool downloads and analyzes HTML from a source URL to help with creating scrapers.
It's designed to be used as part of the scraper development process.

Usage:
    python -m utils.inspector --url https://example.com/fact-checks
"""

import os
import argparse
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from utils.browser import BrowserClient
from core.config import DATA_DIR

async def inspect_page_async(url, output_dir=None, proxy_type="auto", save_html=True, use_cloudflare=False, project="default"):
    """
    Inspect a page using browser client and output analysis to help with creating a scraper

    Args:
        url (str): URL to inspect
        output_dir (str): Directory to save analysis and HTML. If None, a directory is created based on the domain
        proxy_type (str): Proxy type to use (unused now, browser handles this)
        save_html (bool): Whether to save the full HTML
        use_cloudflare (bool): Whether to use Cloudflare bypass mode
        project (str): Project name for organizing analysis files (default: "default")

    Returns:
        dict: Analysis results
    """
    print(f"Inspecting: {url}")
    if use_cloudflare:
        print("Using Cloudflare bypass mode...")
    
    # Extract domain for folder name if output_dir is not specified
    if output_dir is None:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "")

        # Check if this is a Wayback Machine URL
        if domain == "web.archive.org":
            # Parse Wayback Machine URL structure:
            # https://web.archive.org/web/YYYYMMDDHHMMSS/http://original-domain.com/path
            import re
            wayback_pattern = r'/web/(\d{8})\d*/(?:https?://)?(?:www\.)?([^/]+)'
            match = re.search(wayback_pattern, url)

            if match:
                timestamp = match.group(1)  # 8-digit date (YYYYMMDD)
                original_domain = match.group(2).replace(".", "_").replace(":", "_")
                output_dir = f"{DATA_DIR}/{project}/web_archive_org/{original_domain}/{timestamp}/analysis"
            else:
                # Fallback if pattern doesn't match
                output_dir = f"{DATA_DIR}/{project}/web_archive_org/analysis"
        else:
            source_id = domain.replace(".", "_")
            output_dir = f"{DATA_DIR}/{project}/{source_id}/analysis"
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # Choose browser client based on mode
    if use_cloudflare:
        # Use nodriver with Cloudflare bypass
        from utils.cf_browser import CloudflareBrowserClient

        async with CloudflareBrowserClient(headless=False) as browser:
            html_content = await browser.fetch(url)

            if not html_content:
                print(f"Failed to fetch page (Cloudflare bypass failed): {url}")
                return None

            # Save the HTML if requested
            if save_html:
                html_file = os.path.join(output_dir, "page.html")
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"Saved HTML to: {html_file}")

            # Parse the HTML
            soup = BeautifulSoup(html_content, 'html.parser')
    else:
        # Use existing Playwright path
        async with BrowserClient(headless=True) as browser:
            await browser.goto(url)
            html_content = await browser.get_html()

            if not html_content:
                print(f"Failed to fetch page: {url}")
                return None

            # Save the HTML if requested
            if save_html:
                html_file = os.path.join(output_dir, "page.html")
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"Saved HTML to: {html_file}")

            # Parse the HTML
            soup = BeautifulSoup(html_content, 'html.parser')
    
    title = soup.title.text if soup.title else "No title"
    print(f"\nTitle: {title}")
    print(f"HTML size: {len(html_content)} bytes")

def inspect_page(url, output_dir=None, proxy_type="auto", save_html=True, use_cloudflare=False, project="default"):
    """
    Synchronous wrapper for inspect_page_async
    """
    return asyncio.run(inspect_page_async(url, output_dir, proxy_type, save_html, use_cloudflare, project))

def main():
    parser = argparse.ArgumentParser(description='Inspect a page to help with creating a scraper')
    parser.add_argument('--url', type=str, required=True, help='URL to inspect')
    parser.add_argument('--output-dir', type=str, default=None, help='Directory to save analysis')
    parser.add_argument('--proxy-type', choices=['none', 'static', 'residential', 'auto'], 
                        default='auto', help='Proxy type to use')
    parser.add_argument('--no-save-html', action='store_true', help='Do not save the full HTML')
    
    args = parser.parse_args()
    
    inspect_page(args.url, args.output_dir, args.proxy_type, not args.no_save_html)

if __name__ == "__main__":
    main()