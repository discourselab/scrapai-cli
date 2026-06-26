"""
URL Extractor - Extract all URLs from an HTML file
"""

from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Set
import logging

logger = logging.getLogger(__name__)


def _looks_like_sitemap(content: str) -> bool:
    """True for a sitemap or sitemap-index document (keyed on the root tags,
    not the substring 'loc', so pages mentioning e.g. 'geolocation' don't trip)."""
    head = content[:4000].lower()
    return "<urlset" in head or "<sitemapindex" in head


def extract_urls_from_html(html_file: str, output_file: str = None) -> List[str]:
    """
    Extract all URLs from a saved page or sitemap.

    - HTML pages: every `<a href>`.
    - Sitemaps / sitemap indexes: every `<loc>` (page URLs from a `<urlset>`,
      sub-sitemap URLs from a `<sitemapindex>`).

    Args:
        html_file: Path to the HTML/XML file to parse
        output_file: Optional path to save the extracted URLs

    Returns:
        List of unique URLs sorted alphabetically
    """
    html_path = Path(html_file)

    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file}")

    logger.info(f"Reading {html_file}")

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    urls: Set[str] = set()
    if _looks_like_sitemap(content):
        # <loc> holds the URL in both <urlset> (page URLs) and <sitemapindex>
        # (sub-sitemap URLs); find_all("loc") catches either.
        soup = BeautifulSoup(content, "xml")
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            if url:
                urls.add(url)
    else:
        soup = BeautifulSoup(content, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href:  # Skip empty hrefs
                urls.add(href)

    # Sort URLs
    sorted_urls = sorted(urls)

    logger.info(f"Extracted {len(sorted_urls)} unique URLs")

    # Save to file if output path specified
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted_urls))

        logger.info(f"Saved URLs to {output_file}")

    return sorted_urls
