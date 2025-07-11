#!/usr/bin/env python3
"""
Spider Generator - Creates Scrapy spider code from site analysis
"""

import os
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
from datetime import datetime

class SpiderGenerator:
    """Generate Scrapy spider code from site analysis"""
    
    def __init__(self, spider_name: str, base_url: str):
        self.spider_name = spider_name
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.spider_class = self._format_class_name(spider_name)
    
    def _format_class_name(self, spider_name: str) -> str:
        """Convert spider name to valid class name"""
        # Remove special characters and capitalize
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', spider_name)
        return clean_name.title() + 'Spider'
    
    def generate_crawl_spider(self, 
                            start_urls: List[str],
                            article_patterns: List[str],
                            exclude_patterns: List[str],
                            selectors: Dict[str, str],
                            max_depth: int = 3) -> str:
        """Generate CrawlSpider code"""
        
        # Format patterns for regex
        allow_patterns = [self._escape_regex(p) for p in article_patterns]
        deny_patterns = [self._escape_regex(p) for p in exclude_patterns]
        
        spider_code = f'''import scrapy
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapers.items import ArticleItem
from datetime import datetime

class {self.spider_class}(CrawlSpider):
    """
    Spider for {self.domain}
    Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    name = '{self.spider_name}'
    allowed_domains = ['{self.domain}']
    start_urls = {start_urls}
    
    rules = (
        # Extract article links
        Rule(LinkExtractor(
            allow={allow_patterns},
            deny={deny_patterns}
        ), callback='parse_article', follow=False),
        
        # Follow navigation links
        Rule(LinkExtractor(
            allow=[r'/page/', r'/category/', r'/\\?page='],
            deny={deny_patterns}
        ), follow=True),
    )
    
    def parse_article(self, response):
        """Extract article content"""
        item = ArticleItem()
        
        item['url'] = response.url
        item['title'] = response.css('{selectors.get("title", "h1::text")}').get()
        item['content'] = '\\n'.join(response.css('{selectors.get("content", "p::text")}').getall())
        item['published_date'] = response.css('{selectors.get("date", "time::attr(datetime)")}').get()
        item['author'] = response.css('{selectors.get("author", ".author::text")}').get()
        item['tags'] = response.css('{selectors.get("tags", ".tag::text")}').getall()
        
        # Clean up empty fields
        for field in ['title', 'content', 'published_date', 'author']:
            if item.get(field):
                item[field] = item[field].strip()
        
        # Only yield if we have essential content
        if item.get('title') and item.get('content'):
            yield item
'''
        
        return spider_code
    
    def generate_sitemap_spider(self, 
                              sitemap_urls: List[str],
                              selectors: Dict[str, str],
                              url_filters: Optional[List[str]] = None) -> str:
        """Generate SitemapSpider code"""
        
        # Format sitemap rules
        sitemap_rules = []
        if url_filters:
            for pattern in url_filters:
                sitemap_rules.append(f"(r'{self._escape_regex(pattern)}', 'parse_article')")
        else:
            sitemap_rules.append("(r'.*', 'parse_article')")
        
        spider_code = f'''import scrapy
from scrapy.spiders import SitemapSpider
from scrapers.items import ArticleItem
from datetime import datetime

class {self.spider_class}(SitemapSpider):
    """
    Sitemap spider for {self.domain}
    Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    name = '{self.spider_name}'
    allowed_domains = ['{self.domain}']
    sitemap_urls = {sitemap_urls}
    
    sitemap_rules = [
        {', '.join(sitemap_rules)}
    ]
    
    def parse_article(self, response):
        """Extract article content"""
        item = ArticleItem()
        
        item['url'] = response.url
        item['title'] = response.css('{selectors.get("title", "h1::text")}').get()
        item['content'] = '\\n'.join(response.css('{selectors.get("content", "p::text")}').getall())
        item['published_date'] = response.css('{selectors.get("date", "time::attr(datetime)")}').get()
        item['author'] = response.css('{selectors.get("author", ".author::text")}').get()
        item['tags'] = response.css('{selectors.get("tags", ".tag::text")}').getall()
        
        # Clean up empty fields
        for field in ['title', 'content', 'published_date', 'author']:
            if item.get(field):
                item[field] = item[field].strip()
        
        # Only yield if we have essential content
        if item.get('title') and item.get('content'):
            yield item
'''
        
        return spider_code
    
    def save_spider(self, spider_code: str, spider_dir: str = "scrapers/spiders") -> str:
        """Save generated spider code to file"""
        spider_filename = f"{self.spider_name}.py"
        spider_path = os.path.join(spider_dir, spider_filename)
        
        # Create directory if it doesn't exist
        os.makedirs(spider_dir, exist_ok=True)
        
        # Write spider code
        with open(spider_path, 'w', encoding='utf-8') as f:
            f.write(spider_code)
        
        return spider_path
    
    def _escape_regex(self, pattern: str) -> str:
        """Escape regex special characters in URL patterns"""
        # Simple escaping for common URL patterns
        pattern = pattern.replace('.', r'\.')
        pattern = pattern.replace('?', r'\?')
        pattern = pattern.replace('*', r'.*')
        return pattern

def generate_spider_from_analysis(spider_name: str, 
                                base_url: str,
                                analysis_data: Dict[str, Any]) -> str:
    """Generate spider from site analysis data"""
    
    generator = SpiderGenerator(spider_name, base_url)
    
    # Check if site has sitemaps
    if analysis_data.get('sitemaps'):
        # Use sitemap spider
        spider_code = generator.generate_sitemap_spider(
            sitemap_urls=analysis_data['sitemaps'],
            selectors=analysis_data.get('selectors', {}),
            url_filters=analysis_data.get('article_patterns')
        )
    else:
        # Use crawl spider
        spider_code = generator.generate_crawl_spider(
            start_urls=analysis_data.get('start_urls', [base_url]),
            article_patterns=analysis_data.get('article_patterns', []),
            exclude_patterns=analysis_data.get('exclude_patterns', []),
            selectors=analysis_data.get('selectors', {}),
            max_depth=analysis_data.get('max_depth', 3)
        )
    
    return spider_code

# Default patterns for common sites
DEFAULT_EXCLUDE_PATTERNS = [
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
    r'\.doc$',
    r'\.xlsx?$',
    r'/feed/',
    r'/rss/',
    r'/sitemap',
    r'mailto:',
    r'tel:',
    r'#$'
]

DEFAULT_ARTICLE_PATTERNS = [
    r'/article/',
    r'/post/',
    r'/story/',
    r'/news/',
    r'/blog/',
    r'/factcheck/',
    r'/analysis/',
    r'/opinion/',
    r'/\d{4}/\d{2}/',
    r'/\d{4}/\d{1,2}/\d{1,2}/'
]