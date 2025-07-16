import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article


class CaadInfoSpider(BaseSpider):
    name = 'caad_info'
    allowed_domains = ['caad.info', 'www.caad.info']
    start_urls = ['https://caad.info/', 'https://caad.info/analysis/']
    
    # Phase 2: URL Discovery Rules - Focus on /analysis/ path
    rules = (
        # Follow analysis section articles
        Rule(LinkExtractor(
            allow=r'^https://caad\.info/analysis/[^/]+/[^/]+/?$',  # /analysis/type/slug/
            deny=r'/(about|contact|privacy-policy|what-is-misinformation-disinformation|type/briefings)/?$'
        ), callback='parse_article', follow=False),
        
        # Follow main article pages (direct under analysis)
        Rule(LinkExtractor(
            allow=r'^https://caad\.info/analysis/[^/]+/?$',
            deny=r'/(about|contact|privacy-policy|feed|wp-|xmlrpc)/?$'
        ), callback='parse_article', follow=False),
        
        # Follow homepage and analysis section for discovery
        Rule(LinkExtractor(
            allow=r'^https://caad\.info(/analysis)?/?$'
        ), follow=True),
    )

    def parse_article(self, response):
        """Parse article using shared newspaper4k parser"""
        # Quick quality check before processing
        if not self._is_article_page(response):
            return

        # Use the shared newspaper4k parser with automatic proxy handling
        article_data = parse_article(response.url, source_name=self.name)
        
        if article_data and self._validate_content(article_data):
            # Create enhanced item using newspaper4k extracted data
            item = self.create_item(response, **article_data)
            yield item
        else:
            # Fallback for failed parsing
            self.logger.warning(f"Failed to parse article: {response.url}")

    def _is_article_page(self, response):
        """Filter out non-article pages based on content analysis"""
        # Check if URL is in analysis section (main content area)
        if '/analysis/' not in response.url:
            return False
        
        # Content length check
        body_text = ' '.join(response.css('body ::text').getall())
        if len(body_text.strip()) < 500:
            return False

        # Title check
        title = response.css('title::text').get() or ''
        if len(title.strip()) < 10:
            return False

        return True

    def _validate_content(self, article_data):
        """Validate extracted content quality"""
        return (article_data.get('content') and
                len(article_data['content']) > 200 and
                article_data.get('title') and
                len(article_data['title']) > 10)