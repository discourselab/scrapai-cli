import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article


class DesmogSpider(BaseSpider):
    name = 'desmog'
    allowed_domains = ['desmog.com', 'www.desmog.com']
    start_urls = ['https://www.desmog.com/']
    
    # Define crawling rules to collect article URLs
    rules = (
        # Follow article links with date pattern YYYY/MM/DD/article-slug/
        Rule(LinkExtractor(allow=r'/\d{4}/\d{2}/\d{2}/[^/]+/$'), 
             callback='parse_article', follow=True),
        # Follow pagination and navigation pages
        Rule(LinkExtractor(allow=r'/(page|news|analysis|opinion)'), 
             follow=True),
        # Follow homepage and main sections for article discovery
        Rule(LinkExtractor(allow=r'^https://www\.desmog\.com/?$'), 
             follow=True),
    )

    def parse_article(self, response):
        """Parse article using shared newspaper4k parser"""
        # Use the shared newspaper4k parser with automatic proxy handling
        article_data = parse_article(response.url, source_name=self.name)
        
        if article_data:
            # Create enhanced item using newspaper4k extracted data
            item = self.create_item(response, **article_data)
            yield item
        else:
            # Fallback for failed parsing
            self.logger.warning(f"Failed to parse article: {response.url}")
            item = self.create_item(response, 
                url=response.url,
                title=response.css('title::text').get(),
                status='parse_failed'
            )
            yield item