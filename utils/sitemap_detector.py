"""
Utility functions for detecting and handling sitemap URLs.
"""

def is_sitemap_url(url):
    """
    Detect if a URL is likely a sitemap.

    Args:
        url: URL string to check

    Returns:
        bool: True if URL appears to be a sitemap
    """
    if not url:
        return False

    url_lower = url.lower()

    # Common sitemap patterns
    sitemap_indicators = [
        'sitemap.xml',
        'sitemap_index.xml',
        'sitemap-index.xml',
        'post-sitemap.xml',
        'page-sitemap.xml',
        'sitemap1.xml',
        '/sitemap/',
        'sitemaps.xml',
    ]

    return any(indicator in url_lower for indicator in sitemap_indicators)


def detect_spider_type(start_urls):
    """
    Detect if spider should use sitemap or regular crawl based on start URLs.

    Args:
        start_urls: List of start URLs

    Returns:
        str: 'sitemap' if any URL is a sitemap, 'regular' otherwise
    """
    if not start_urls:
        return 'regular'

    # Check if any URL is a sitemap
    for url in start_urls:
        if is_sitemap_url(url):
            return 'sitemap'

    return 'regular'


def get_spider_class_name(spider_type):
    """
    Get the Scrapy spider class name based on spider type.

    Args:
        spider_type: 'sitemap' or 'regular'

    Returns:
        str: Spider class name to use with 'scrapy crawl'
    """
    if spider_type == 'sitemap':
        return 'sitemap_database_spider'
    else:
        return 'database_spider'
