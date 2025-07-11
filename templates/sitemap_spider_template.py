#!/usr/bin/env python3
"""
SitemapSpider Template - Use this for sites WITH sitemaps

Copy this template and modify for new sites:
1. Replace SITENAME with actual site name
2. Update sitemap_urls from analysis
3. Modify sitemap_rules if needed
4. Update selectors in parse_article method

Example usage:
- Sites with sitemap.xml files
- Large news sites
- Well-structured websites
"""

import scrapy
from scrapy.spiders import SitemapSpider
from scrapers.items import ArticleItem

class SITENAMESpider(SitemapSpider):
    """
    SITENAME sitemap spider for crawling articles
    
    Site analysis:
    - Base URL: https://example.com
    - Sitemaps found: /sitemap.xml, /news-sitemap.xml
    - Article patterns: All URLs from sitemap
    """
    
    name = 'SITENAME'
    allowed_domains = ['example.com']
    
    # Sitemap URLs (get these from core/sitemap.py analysis)
    sitemap_urls = [
        'https://example.com/sitemap.xml',
        'https://example.com/news-sitemap.xml',
        'https://example.com/articles-sitemap.xml',
    ]
    
    # Sitemap rules (modify if you need to filter URLs)
    sitemap_rules = [
        # Parse all URLs from sitemap
        (r'.*', 'parse_article'),
        
        # OR filter specific patterns:
        # (r'/article/', 'parse_article'),
        # (r'/news/', 'parse_article'),
        # (r'/\d{4}/\d{2}/', 'parse_article'),  # Date patterns
    ]
    
    def parse_article(self, response):
        """
        Extract article content from individual article pages
        
        Modify these selectors based on site analysis:
        - Use bin/inspector to analyze page structure
        - Test selectors in browser console
        - Update CSS selectors below
        """
        item = ArticleItem()
        
        # Basic fields (always required)
        item['url'] = response.url
        item['source'] = self.name
        
        # Extract title (modify selector based on site)
        item['title'] = response.css('h1::text').get()
        # Alternative selectors to try:
        # item['title'] = response.css('h1.article-title::text').get()
        # item['title'] = response.css('.headline::text').get()
        # item['title'] = response.css('title::text').get()
        
        # Extract content (modify selector based on site)
        content_paragraphs = response.css('article p::text').getall()
        item['content'] = '\n'.join(content_paragraphs)
        # Alternative selectors to try:
        # content_paragraphs = response.css('.article-body p::text').getall()
        # content_paragraphs = response.css('.content p::text').getall()
        # content_paragraphs = response.css('.post-content p::text').getall()
        
        # Extract publication date (modify selector based on site)
        item['published_date'] = response.css('time::attr(datetime)').get()
        # Alternative selectors to try:
        # item['published_date'] = response.css('.date::text').get()
        # item['published_date'] = response.css('.published::text').get()
        # item['published_date'] = response.css('[class*="date"]::text').get()
        
        # Extract author (modify selector based on site)
        item['author'] = response.css('.author::text').get()
        # Alternative selectors to try:
        # item['author'] = response.css('.byline::text').get()
        # item['author'] = response.css('[rel="author"]::text').get()
        # item['author'] = response.css('.writer::text').get()
        
        # Extract tags (modify selector based on site)
        item['tags'] = response.css('.tag::text').getall()
        # Alternative selectors to try:
        # item['tags'] = response.css('.category::text').getall()
        # item['tags'] = response.css('.label::text').getall()
        # item['tags'] = response.css('[class*="tag"]::text').getall()
        
        # Clean up fields
        if item.get('title'):
            item['title'] = item['title'].strip()
        if item.get('content'):
            item['content'] = item['content'].strip()
        if item.get('author'):
            item['author'] = item['author'].strip()
        
        # Only yield if we have essential content
        if item.get('title') and item.get('content'):
            yield item
        else:
            self.logger.warning(f"Skipping article with missing data: {response.url}")

# INSTRUCTIONS FOR CLAUDE CODE:
#
# 1. Copy this template to scrapers/spiders/SITENAME.py
# 2. Replace SITENAME with actual site name (e.g., politifact, heritage)
# 3. Use core/sitemap.py to discover sitemap URLs:
#    from core.sitemap import SitemapDiscovery
#    discovery = SitemapDiscovery('https://example.com')
#    sitemaps = discovery.discover_sitemaps()
# 4. Update sitemap_urls with discovered sitemaps
# 5. Use bin/inspector to analyze page structure
# 6. Update selectors in parse_article based on site structure
# 7. Test with: ./scrapai test SITENAME
# 8. Run with: ./scrapai crawl SITENAME --limit 100
#
# WHEN TO USE SITEMAP SPIDER:
# - Site has sitemap.xml files
# - Large number of articles (thousands)
# - Well-structured website
# - Want to crawl everything efficiently
#
# WHEN TO USE CRAWL SPIDER:
# - No sitemap files found
# - Need to follow links manually
# - Complex navigation structure
# - Want more control over crawling