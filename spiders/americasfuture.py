import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article

class AmericasfutureSpider(BaseSpider):
    name = 'americasfuture'
    allowed_domains = ['americasfuture.org', 'www.americasfuture.org']
    start_urls = ['https://americasfuture.org/commentary/']

    rules = (
        # Focus on commentary articles - use broader patterns to catch actual articles
        Rule(LinkExtractor(
            deny=r'/(about|contact|privacy|terms|mission|staff|board|job-openings|faq|events|media|tag|category|page|author|opportunities|wp-content)/?'
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

        # Check if it looks like an article page based on content structure
        # Looking for post content or article content
        article_content = response.css('article.post, .entry-content, .post-content').get()
        if not article_content:
            return False

        return True

    def _validate_content(self, article_data):
        """Validate extracted content quality"""
        return (article_data.get('content') and
                len(article_data['content']) > 200 and
                article_data.get('title'))