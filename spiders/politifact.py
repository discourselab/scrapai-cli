import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
import re


class PolitifactSpider(BaseSpider):
    name = 'politifact'
    allowed_domains = ['politifact.com']
    start_urls = ['https://www.politifact.com/']
    
    rules = (
        # Follow links to article pages
        Rule(LinkExtractor(allow=r'/article/\d{4}/\w+/\d{2}/'), callback='parse_article', follow=True),
        Rule(LinkExtractor(allow=r'/factchecks/\d{4}/\w+/\d{2}/'), callback='parse_article', follow=True),
        # Follow pagination and category pages  
        Rule(LinkExtractor(allow=r'/page/\d+/'), follow=True),
        Rule(LinkExtractor(allow=r'/subjects/'), follow=True),
    )
    
    def parse_article(self, response):
        """Parse individual article pages"""
        # Extract article data using selectors found during analysis
        title = response.css('.m-statement__title h1::text, .m-article__title h1::text, h1::text').get()
        if not title:
            title = response.css('title::text').get()
        
        # Extract content from main article body
        content_selectors = [
            '.m-textblock p::text',
            '.entry-content p::text', 
            '.article-body p::text',
            '.content p::text',
            'article p::text',
            '.story-body p::text'
        ]
        
        content = []
        for selector in content_selectors:
            paragraphs = response.css(selector).getall()
            if paragraphs:
                content = paragraphs
                break
        
        content_text = ' '.join(content).strip() if content else ''
        
        # Extract author from footer or byline
        author = response.css('.m-statement__footer::text, .byline::text, .author::text').get()
        if author:
            # Clean up author text (remove "By " prefix and date)
            author = re.sub(r'^By\s+', '', author)
            author = re.sub(r'\s*•.*$', '', author)  # Remove date after bullet
            author = author.strip()
        
        # Extract published date
        date_text = response.css('.m-statement__footer::text, .published-date::text, time::text').get()
        published_date = self.parse_date(date_text) if date_text else None
        
        # Extract tags/subjects if available
        tags = response.css('.m-statement__subjects a::text, .tags a::text').getall()
        
        # Extract truth-o-meter rating if this is a fact-check
        rating = response.css('.m-statement__meter img::attr(alt)').get()
        
        # Only yield if we have meaningful content
        if title and (content_text or rating):
            item = self.create_item(
                response,
                title=title.strip() if title else '',
                content=content_text,
                author=author or '',
                published_date=published_date,
                tags=tags,
                rating=rating,  # PolitiFact-specific field
                article_type='factcheck' if '/factchecks/' in response.url else 'article'
            )
            yield item
    
    def parse_start_url(self, response):
        """Parse the homepage to find article links"""
        # Extract articles from homepage
        article_links = response.css('.m-article__title a::attr(href)').getall()
        
        for link in article_links:
            if link:
                full_url = response.urljoin(link)
                yield response.follow(full_url, self.parse_article)
        
        # Continue with default crawling behavior
        return super().parse_start_url(response)