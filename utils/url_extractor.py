"""
URL Extractor - Extract all URLs from an HTML file
"""

from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Set
import logging

logger = logging.getLogger(__name__)


def extract_urls_from_html(html_file: str, output_file: str = None) -> List[str]:
    """
    Extract all href URLs from an HTML file.

    Args:
        html_file: Path to the HTML file to parse
        output_file: Optional path to save the extracted URLs

    Returns:
        List of unique URLs sorted alphabetically
    """
    html_path = Path(html_file)

    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_file}")

    logger.info(f"Reading HTML from {html_file}")

    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Extract all href attributes from <a> tags
    urls: Set[str] = set()
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
