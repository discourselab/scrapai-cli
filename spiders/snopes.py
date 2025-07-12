import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article


class SnopesSpider(BaseSpider):
    name = 'snopes'
    allowed_domains = ['snopes.com', 'www.snopes.com']
    start_urls = [
        'https://www.snopes.com/fact-check/',
        'https://www.snopes.com/'
    ]

    rules = (
        # Focus on fact-check articles and news articles
        Rule(LinkExtractor(
            allow=r'/(fact-check|news)/',
            deny=r'/(about|contact|privacy|terms|advertise|support|newsletter|donate|author|rating|sitemap|game|collections|factbot|dmca)/?'
        ), callback='parse_article', follow=True),
        # Also allow following from main pages to discover articles
        Rule(LinkExtractor(
            deny=r'/(about|contact|privacy|terms|advertise|support|newsletter|donate|author|rating|sitemap|game|collections|factbot|dmca)/?'
        ), follow=True),
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

        # Skip obvious navigation pages
        url = response.url.lower()
        skip_patterns = ['/tag/', '/category/', '/archive/', '/page/', '/search/']
        if any(pattern in url for pattern in skip_patterns):
            return False

        return True

    def _validate_content(self, article_data):
        """Validate extracted content quality"""
        return (article_data.get('content') and
                len(article_data['content']) > 200 and
                article_data.get('title'))