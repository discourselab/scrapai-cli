#!/usr/bin/env python3
"""
Page Inspector Utility

Downloads and analyzes HTML from a source URL to help create scrapers.

In the default (lightweight) mode it ESCALATES transports automatically:
plain HTTP → curl_cffi (TLS impersonation). If both are blocked it reports that a
browser is needed; the CLI then runs the browser subprocess (with Xvfb handling).
It tells you which transport worked and the flag to set in the spider config.

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
from core.block_signals import is_blocked
from settings import USER_AGENT


def _resolve_output_dir(url, output_dir, project):
    """Resolve the analysis output directory from the URL (domain-based)."""
    if output_dir is not None:
        return output_dir

    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace("www.", "")

    if domain == "web.archive.org":
        import re

        wayback_pattern = r"/web/(\d{8})\d*/(?:https?://)?(?:www\.)?([^/]+)"
        match = re.search(wayback_pattern, url)
        if match:
            timestamp = match.group(1)
            original_domain = match.group(2).replace(".", "_").replace(":", "_")
            return str(
                Path(DATA_DIR)
                / project
                / "web_archive_org"
                / original_domain
                / timestamp
                / "analysis"
            )
        return str(Path(DATA_DIR) / project / "web_archive_org" / "analysis")

    source_id = domain.replace(".", "_")
    return str(Path(DATA_DIR) / project / source_id / "analysis")


async def _fetch_http(url):
    """Plain aiohttp fetch. Returns (status, html) or (None, None) on error."""
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                return response.status, await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        print(f"Plain HTTP fetch failed: {e}")
        return None, None


def _fetch_curl_cffi(url):
    """curl_cffi (Chrome TLS impersonation). Returns (status, html) or (None, None)."""
    try:
        from curl_cffi import requests as cffi_requests

        resp = cffi_requests.get(
            url, impersonate="chrome", timeout=30, allow_redirects=True
        )
        return resp.status_code, resp.text
    except Exception as e:
        print(f"curl_cffi fetch failed: {e}")
        return None, None


async def _fetch_browser(url, proxy_type):
    """CloakBrowser fetch (JS rendering + Cloudflare bypass). Returns html or None."""
    from utils.cf_browser import CloudflareBrowserClient

    def _env_proxy(prefix):
        user = os.getenv(f"{prefix}_PROXY_USERNAME")
        pw = os.getenv(f"{prefix}_PROXY_PASSWORD")
        host = os.getenv(f"{prefix}_PROXY_HOST")
        port = os.getenv(f"{prefix}_PROXY_PORT")
        return (
            f"http://{user}:{pw}@{host}:{port}" if all([user, pw, host, port]) else None
        )

    dc_url = _env_proxy("DATACENTER")
    res_url = _env_proxy("RESIDENTIAL")

    if proxy_type == "residential":
        proxy_chain = [res_url] if res_url else [None]
    elif proxy_type == "static":
        proxy_chain = [dc_url] if dc_url else [None]
    elif proxy_type == "none":
        proxy_chain = [None]
    else:
        proxy_chain = [None]
        if dc_url:
            proxy_chain.append(dc_url)
        if res_url:
            proxy_chain.append(res_url)

    async with CloudflareBrowserClient(
        headless=False, proxy_chain=proxy_chain
    ) as browser:
        return await browser.fetch(url)


_FLAG_HINT = {
    "http": "Plain HTTP works — no transport flag needed.",
    "curl_cffi": "curl_cffi works (plain HTTP was blocked). "
    'Set "CURL_CFFI_ENABLED": true in the spider config.',
    "browser": 'Browser works. Set "CLOUDFLARE_ENABLED": true '
    '(or "BROWSER_ENABLED": true for JS-only sites).',
}


def _report(transport):
    print(f"\n✓ Transport: {transport} — {_FLAG_HINT[transport]}")


async def inspect_page_async(
    url,
    output_dir=None,
    proxy_type="auto",
    save_html=True,
    mode="http",
    project="default",
):
    """Inspect a page, escalating transport as needed.

    Returns a dict: {"transport": "http"|"curl_cffi"|"browser"|None,
                     "needs_browser": bool}.
    In http mode, escalates plain HTTP → curl_cffi; if both blocked, returns
    needs_browser=True so the caller can run the browser path.
    """
    print(f"Inspecting: {url}")
    output_dir = _resolve_output_dir(url, output_dir, project)
    os.makedirs(output_dir, exist_ok=True)

    html_content = None
    transport = None

    if mode == "browser":
        print("Using CloakBrowser (JS rendering + Cloudflare bypass)...")
        html_content = await _fetch_browser(url, proxy_type)
        if not html_content:
            print(f"Failed to fetch page: {url}")
            return {"transport": None, "needs_browser": True}
        transport = "browser"
    else:
        print("Trying plain HTTP...")
        status, html_content = await _fetch_http(url)
        if not is_blocked(status, html_content):
            transport = "http"
        else:
            print(f"Plain HTTP blocked (status {status}) — trying curl_cffi...")
            status, html_content = await asyncio.to_thread(_fetch_curl_cffi, url)
            if not is_blocked(status, html_content):
                transport = "curl_cffi"
            else:
                print("curl_cffi also blocked — a browser is needed.")
                return {"transport": None, "needs_browser": True}

    if save_html and html_content:
        html_file = os.path.join(output_dir, "page.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Saved HTML to: {html_file}")

    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        title = soup.title.text if soup.title else "No title"
        print(f"\nTitle: {title}")
        print(f"HTML size: {len(html_content)} bytes")

    _report(transport)
    return {"transport": transport, "needs_browser": False}


def inspect_page(
    url,
    output_dir=None,
    proxy_type="auto",
    save_html=True,
    mode="http",
    project="default",
):
    """Synchronous wrapper for inspect_page_async."""
    return asyncio.run(
        inspect_page_async(url, output_dir, proxy_type, save_html, mode, project)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a page to help with creating a scraper"
    )
    parser.add_argument("url", type=str, help="URL to inspect")
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
    parser.add_argument(
        "--browser", action="store_true", help="Use CloakBrowser for JS + Cloudflare"
    )
    parser.add_argument("--project", type=str, default="default", help="Project name")

    args = parser.parse_args()

    mode = "browser" if args.browser else "http"
    inspect_page(
        args.url,
        args.output_dir,
        args.proxy_type,
        not args.no_save_html,
        mode=mode,
        project=args.project,
    )


if __name__ == "__main__":
    main()
