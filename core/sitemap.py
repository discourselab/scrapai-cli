import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from typing import List, Optional
import re

class SitemapDiscovery:
    """Discover and parse sitemaps from websites"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        
    def discover_sitemaps(self) -> List[str]:
        """Discover sitemap URLs from robots.txt and common locations"""
        sitemap_urls = []
        
        # Check robots.txt first
        robots_sitemaps = self._check_robots_txt()
        sitemap_urls.extend(robots_sitemaps)
        
        # Check common sitemap locations
        common_locations = [
            '/sitemap.xml',
            '/sitemap_index.xml',
            '/sitemaps.xml',
            '/sitemap/sitemap.xml',
            '/sitemaps/sitemap.xml'
        ]
        
        for location in common_locations:
            sitemap_url = urljoin(self.base_url, location)
            if sitemap_url not in sitemap_urls:
                if self._check_sitemap_exists(sitemap_url):
                    sitemap_urls.append(sitemap_url)
        
        return sitemap_urls
    
    def _check_robots_txt(self) -> List[str]:
        """Check robots.txt for sitemap declarations"""
        robots_url = urljoin(self.base_url, '/robots.txt')
        sitemap_urls = []
        
        try:
            response = requests.get(robots_url, timeout=10)
            if response.status_code == 200:
                # Find sitemap declarations
                for line in response.text.split('\n'):
                    if line.strip().lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        sitemap_urls.append(sitemap_url)
        except Exception:
            pass
        
        return sitemap_urls
    
    def _check_sitemap_exists(self, sitemap_url: str) -> bool:
        """Check if sitemap URL exists and is valid XML"""
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code == 200:
                # Quick check if it's XML
                return response.text.strip().startswith('<?xml')
        except Exception:
            pass
        return False
    
    def get_article_urls_from_sitemap(self, sitemap_url: str) -> List[str]:
        """Extract article URLs from sitemap"""
        article_urls = []
        
        try:
            response = requests.get(sitemap_url, timeout=10)
            if response.status_code != 200:
                return article_urls
            
            # Parse XML
            root = ET.fromstring(response.text)
            
            # Handle sitemap index (contains other sitemaps)
            if 'sitemapindex' in root.tag:
                for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                    loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None:
                        # Recursively get URLs from each sitemap
                        article_urls.extend(self.get_article_urls_from_sitemap(loc.text))
            
            # Handle regular sitemap (contains URLs)
            else:
                for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                    loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None:
                        url_text = loc.text
                        # Filter for likely article URLs
                        if self._looks_like_article_url(url_text):
                            article_urls.append(url_text)
        
        except Exception as e:
            print(f"Error parsing sitemap {sitemap_url}: {e}")
        
        return article_urls
    
    def _looks_like_article_url(self, url: str) -> bool:
        """Heuristic to determine if URL looks like an article"""
        # Common article URL patterns
        article_patterns = [
            r'/article/',
            r'/post/',
            r'/story/',
            r'/news/',
            r'/blog/',
            r'/factcheck/',
            r'/analysis/',
            r'/opinion/',
            r'/\d{4}/\d{2}/',  # Date-based URLs
            r'/\d{4}/\d{1,2}/\d{1,2}/'  # Full date URLs
        ]
        
        # Exclude common non-article patterns
        exclude_patterns = [
            r'/category/',
            r'/tag/',
            r'/author/',
            r'/page/',
            r'/search/',
            r'/feed/',
            r'/rss/',
            r'\.pdf$',
            r'\.jpg$',
            r'\.png$',
            r'\.gif$'
        ]
        
        # Check exclusions first
        for pattern in exclude_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False
        
        # Check for article patterns
        for pattern in article_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        
        return False
    
    def get_all_article_urls(self) -> List[str]:
        """Get all article URLs from discovered sitemaps"""
        all_urls = []
        sitemaps = self.discover_sitemaps()
        
        for sitemap_url in sitemaps:
            urls = self.get_article_urls_from_sitemap(sitemap_url)
            all_urls.extend(urls)
        
        # Remove duplicates
        return list(set(all_urls))

def discover_site_structure(base_url: str) -> dict:
    """Discover site structure including sitemaps and robots.txt info"""
    discovery = SitemapDiscovery(base_url)
    
    return {
        'base_url': base_url,
        'sitemaps': discovery.discover_sitemaps(),
        'has_robots_txt': discovery._check_sitemap_exists(urljoin(base_url, '/robots.txt')),
        'article_urls_sample': discovery.get_all_article_urls()[:10]  # First 10 as sample
    }