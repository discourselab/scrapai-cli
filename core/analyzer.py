#!/usr/bin/env python3
"""
Site Analyzer - Analyze websites to extract structure and selectors
"""

import os
import sys
import json
import subprocess
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests

# Add parent directory to path to import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sitemap import SitemapDiscovery
from utils.http import get_client

class SiteAnalyzer:
    """Analyze website structure and generate scraping configuration"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.http_client = get_client()
        self.sitemap_discovery = SitemapDiscovery(base_url)
    
    def analyze_site(self, sample_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Complete site analysis"""
        analysis = {
            'base_url': self.base_url,
            'domain': self.domain,
            'timestamp': self._get_timestamp(),
            'sitemaps': [],
            'has_robots_txt': False,
            'start_urls': [],
            'article_patterns': [],
            'exclude_patterns': [],
            'selectors': {},
            'sample_articles': []
        }
        
        # Discover sitemaps
        print(f"🔍 Discovering sitemaps for {self.domain}...")
        analysis['sitemaps'] = self.sitemap_discovery.discover_sitemaps()
        analysis['has_robots_txt'] = self._check_robots_txt()
        
        # Get sample article URLs
        if analysis['sitemaps']:
            print(f"📄 Found {len(analysis['sitemaps'])} sitemaps")
            sample_articles = self.sitemap_discovery.get_all_article_urls()[:10]
            analysis['sample_articles'] = sample_articles
            analysis['start_urls'] = [self.base_url]
        else:
            print("❌ No sitemaps found, analyzing site structure...")
            # Use inspector tool to analyze site
            inspector_analysis = self._run_inspector_analysis()
            if inspector_analysis:
                analysis.update(inspector_analysis)
            else:
                # Fallback to manual analysis
                analysis.update(self._analyze_site_manually())
        
        # Analyze content structure
        print("🔍 Analyzing content structure...")
        selectors = self._analyze_content_selectors(analysis['sample_articles'][:3])
        analysis['selectors'] = selectors
        
        # Generate URL patterns
        if not analysis['sitemaps']:
            analysis['article_patterns'] = self._generate_article_patterns(analysis['sample_articles'])
            analysis['exclude_patterns'] = self._get_default_exclude_patterns()
        
        return analysis
    
    def _run_inspector_analysis(self) -> Optional[Dict[str, Any]]:
        """Run the inspector tool to analyze site structure"""
        try:
            # Use the existing inspector tool
            inspector_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'bin', 'inspector')
            
            if not os.path.exists(inspector_path):
                print(f"⚠️  Inspector tool not found at {inspector_path}")
                return None
            
            # Run inspector
            cmd = [sys.executable, inspector_path, '--url', self.base_url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print("✅ Inspector analysis completed")
                return self._parse_inspector_output(result.stdout)
            else:
                print(f"❌ Inspector failed: {result.stderr}")
                return None
        
        except Exception as e:
            print(f"❌ Inspector error: {e}")
            return None
    
    def _parse_inspector_output(self, output: str) -> Dict[str, Any]:
        """Parse inspector tool output"""
        # This would need to be implemented based on your inspector tool output format
        # For now, return basic structure
        return {
            'start_urls': [self.base_url],
            'sample_articles': [],
            'analysis_available': True
        }
    
    def _analyze_site_manually(self) -> Dict[str, Any]:
        """Fallback manual site analysis"""
        print("🔍 Manual site analysis...")
        
        # Fetch homepage
        response = self.http_client.get(self.base_url)
        if not response:
            return {
                'start_urls': [self.base_url],
                'sample_articles': [],
                'error': 'Could not fetch homepage'
            }
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find potential article links
        article_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(self.base_url, href)
            
            # Check if it looks like an article
            if self._looks_like_article_link(full_url):
                article_links.append(full_url)
        
        # Find potential start URLs (category pages, etc.)
        start_urls = [self.base_url]
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(self.base_url, href)
            
            # Check if it looks like a category/section page
            if self._looks_like_category_link(full_url):
                start_urls.append(full_url)
        
        return {
            'start_urls': list(set(start_urls))[:5],  # Limit to 5 start URLs
            'sample_articles': list(set(article_links))[:10],  # Limit to 10 samples
        }
    
    def _analyze_content_selectors(self, sample_urls: List[str]) -> Dict[str, str]:
        """Analyze sample articles to detect content selectors"""
        print(f"🔍 Analyzing {len(sample_urls)} sample articles...")
        
        selectors = {
            'title': 'h1::text',
            'content': 'p::text',
            'date': 'time::attr(datetime)',
            'author': '.author::text',
            'tags': '.tag::text'
        }
        
        # Try to improve selectors based on actual content
        for url in sample_urls:
            try:
                response = self.http_client.get(url)
                if response:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Try to find better title selector
                    title_selectors = ['h1', 'h2.title', '.title h1', '.headline', 'title']
                    for selector in title_selectors:
                        if soup.select_one(selector):
                            selectors['title'] = f'{selector}::text'
                            break
                    
                    # Try to find better content selector
                    content_selectors = ['.content p', '.article-body p', '.post-content p', 'article p', '.entry-content p']
                    for selector in content_selectors:
                        if soup.select(selector):
                            selectors['content'] = f'{selector}::text'
                            break
                    
                    # Try to find date selector
                    date_selectors = ['time', '.date', '.published', '.timestamp']
                    for selector in date_selectors:
                        element = soup.select_one(selector)
                        if element:
                            if element.get('datetime'):
                                selectors['date'] = f'{selector}::attr(datetime)'
                            else:
                                selectors['date'] = f'{selector}::text'
                            break
                    
                    print(f"✅ Analyzed {url}")
                    break  # Use first successful analysis
            
            except Exception as e:
                print(f"❌ Error analyzing {url}: {e}")
                continue
        
        return selectors
    
    def _generate_article_patterns(self, sample_urls: List[str]) -> List[str]:
        """Generate article URL patterns from sample URLs"""
        patterns = set()
        
        for url in sample_urls:
            path = urlparse(url).path
            
            # Common patterns
            if '/article/' in path:
                patterns.add(r'/article/')
            elif '/post/' in path:
                patterns.add(r'/post/')
            elif '/story/' in path:
                patterns.add(r'/story/')
            elif '/news/' in path:
                patterns.add(r'/news/')
            elif '/blog/' in path:
                patterns.add(r'/blog/')
            elif '/factcheck/' in path:
                patterns.add(r'/factcheck/')
            
            # Date-based patterns
            if '/20' in path:  # Year pattern
                patterns.add(r'/\d{4}/')
            
            # Generic patterns if no specific ones found
            if not patterns:
                patterns.add(r'/[^/]+/$')  # Single path segment
        
        return list(patterns) if patterns else [r'/.*']  # Fallback to match all
    
    def _get_default_exclude_patterns(self) -> List[str]:
        """Get default exclude patterns"""
        return [
            r'/about/',
            r'/contact/',
            r'/privacy/',
            r'/terms/',
            r'/api/',
            r'/admin/',
            r'/login/',
            r'/register/',
            r'\.pdf$',
            r'\.jpg$',
            r'\.png$',
            r'\.gif$',
            r'\.zip$',
            r'/feed/',
            r'/rss/',
            r'/sitemap',
            r'mailto:',
            r'tel:',
            r'#$'
        ]
    
    def _looks_like_article_link(self, url: str) -> bool:
        """Check if URL looks like an article"""
        path = urlparse(url).path.lower()
        
        # Article indicators
        article_indicators = [
            '/article/', '/post/', '/story/', '/news/', '/blog/',
            '/factcheck/', '/analysis/', '/opinion/', '/review/'
        ]
        
        # Date patterns
        import re
        date_patterns = [
            r'/\d{4}/\d{2}/',  # /2024/01/
            r'/\d{4}/\d{1,2}/\d{1,2}/'  # /2024/1/15/
        ]
        
        # Check indicators
        for indicator in article_indicators:
            if indicator in path:
                return True
        
        # Check date patterns
        for pattern in date_patterns:
            if re.search(pattern, path):
                return True
        
        return False
    
    def _looks_like_category_link(self, url: str) -> bool:
        """Check if URL looks like a category/section page"""
        path = urlparse(url).path.lower()
        
        category_indicators = [
            '/category/', '/section/', '/topic/', '/tag/',
            '/news/', '/articles/', '/posts/', '/factchecks/'
        ]
        
        for indicator in category_indicators:
            if indicator in path:
                return True
        
        return False
    
    def _check_robots_txt(self) -> bool:
        """Check if robots.txt exists"""
        try:
            robots_url = urljoin(self.base_url, '/robots.txt')
            response = requests.get(robots_url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

def analyze_website(base_url: str) -> Dict[str, Any]:
    """Analyze a website and return configuration for spider generation"""
    analyzer = SiteAnalyzer(base_url)
    return analyzer.analyze_site()