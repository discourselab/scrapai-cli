#!/usr/bin/env python3
"""
CrawlSpider Template - Use this for sites WITHOUT sitemaps

Copy this template and modify for new sites:
1. Replace SITENAME with actual site name
2. Update allowed_domains and start_urls
3. Modify rules based on site analysis
4. Update selectors in parse_article method

Example usage:
- politifact.py
- heritage.py  
- desmog.py
"""

import scrapy
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor
from scrapers.items import ArticleItem

class SITENAMESpider(CrawlSpider):
    """
    SITENAME spider for crawling articles
    
    Site analysis:
    - Base URL: https://example.com
    - Article patterns: /article/, /post/, /news/
    - Exclude patterns: /about/, /contact/, /api/
    """
    
    name = 'SITENAME'
    allowed_domains = ['example.com']
    start_urls = [
        'https://example.com/articles/',
        'https://example.com/news/',
    ]
    
    rules = (
        # Rule 1: Extract article links (don't follow)
        Rule(LinkExtractor(
            allow=[
                r'/article/',
                r'/post/',
                r'/news/',
                r'/\d{4}/\d{2}/',  # Date patterns like /2024/01/
            ],
            deny=[
                r'/about/',
                r'/contact/',
                r'/privacy/',
                r'/terms/',
                r'/api/',
                r'/admin/',
                r'\.pdf$',
                r'\.jpg$',
                r'\.png$',
                r'/feed/',
                r'/rss/',
            ]
        ), callback='parse_article', follow=False),
        
        # Rule 2: Follow navigation links (categories, pagination)
        Rule(LinkExtractor(
            allow=[
                r'/category/',
                r'/page/',
                r'/\?page=',
                r'/articles/',
                r'/news/',
            ],
            deny=[
                r'/about/',
                r'/contact/',
                r'/api/',
            ]
        ), follow=True),
    )
    
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
        
        # Extract content (modify selector based on site)
        content_paragraphs = response.css('article p::text').getall()
        item['content'] = '\n'.join(content_paragraphs)
        # Alternative selectors to try:
        # content_paragraphs = response.css('.article-body p::text').getall()
        # content_paragraphs = response.css('.content p::text').getall()
        
        # Extract publication date (modify selector based on site)
        item['published_date'] = response.css('time::attr(datetime)').get()
        # Alternative selectors to try:
        # item['published_date'] = response.css('.date::text').get()
        # item['published_date'] = response.css('.published::text').get()
        
        # Extract author (modify selector based on site)
        item['author'] = response.css('.author::text').get()
        # Alternative selectors to try:
        # item['author'] = response.css('.byline::text').get()
        # item['author'] = response.css('[rel="author"]::text').get()
        
        # Extract tags (modify selector based on site)
        item['tags'] = response.css('.tag::text').getall()
        # Alternative selectors to try:
        # item['tags'] = response.css('.category::text').getall()
        # item['tags'] = response.css('.label::text').getall()
        
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
# 3. Use core/sitemap.py to check if site has sitemaps
#    - If sitemaps exist, use sitemap_spider_template.py instead
# 4. Use bin/inspector to analyze site structure
# 5. Update allowed_domains and start_urls
# 6. Modify rules based on analysis:
#    - Update allow patterns for article URLs
#    - Update deny patterns for non-article URLs
# 7. Update selectors in parse_article based on site structure
# 8. Test with: ./scrapai test SITENAME
# 9. Run with: ./scrapai crawl SITENAME --limit 100