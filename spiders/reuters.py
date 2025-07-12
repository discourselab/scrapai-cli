import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article

class ReutersSpider(BaseSpider):
    name = 'reuters'
    allowed_domains = ['reuters.com', 'www.reuters.com']
    start_urls = ['https://www.reuters.com/sustainability/']

    rules = (
        # Follow all links but deny obvious navigation pages
        Rule(LinkExtractor(
            deny=r'/(about|contact|privacy|terms|login|register|search|tag|author|topic|section)/?$'
        ), callback='parse_article', follow=True),
    )

    def parse_article(self, response):
        """Extract content with quality validation"""
        # Quick quality check
        if not self._is_article_page(response):
            return

        # Use shared newspaper4k parser (handles proxies automatically)
        article_data = parse_article(response.url, source_name=self.name)

        if article_data and self._validate_content(article_data):
            item = self.create_item(response, **article_data)
            yield item

    def _is_article_page(self, response):
        """Filter out non-article pages"""
        # Content length check
        body_text = ' '.join(response.css('body ::text').getall())
        if len(body_text.strip()) < 500:
            return False

        # Title check
        title = response.css('title::text').get() or ''
        if len(title.strip()) < 10:
            return False

        # Check if URL pattern suggests it's an article
        url = response.url.lower()
        if any(x in url for x in ['/sustainability/', '/business/', '/world/', '/technology/']):
            return True

        return False

    def _validate_content(self, article_data):
        """Validate extracted content quality"""
        return (article_data.get('content') and
                len(article_data['content']) > 200 and
                article_data.get('title'))