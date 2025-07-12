import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from .base_spider import BaseSpider
from utils.newspaper_parser import parse_article


class CarbonBriefSpider(BaseSpider):
    name = 'carbon_brief'
    allowed_domains = ['carbonbrief.org', 'www.carbonbrief.org']
    start_urls = ['https://www.carbonbrief.org/']
    
    # Phase 1: URL Collection Rules - RESTRICTIVE to avoid non-article pages
    rules = (
        # Follow specific content type articles only
        Rule(LinkExtractor(
            allow=r'^https://www\.carbonbrief\.org/(chart|qa|media-reaction|experts|analysis|explainer|factcheck|guest-post|interview|mapped|daily-brief|debriefed|cropped)-',
            deny=r'/(wp-|feed)/'
        ), callback='parse_article', follow=False),
        
        # Follow only article-pattern URLs (long descriptive slugs, avoid single-word pages)
        Rule(LinkExtractor(
            allow=r'^https://www\.carbonbrief\.org/[a-z0-9]+-[a-z0-9]+-[a-z0-9-]+/$',  # Must have at least 2 hyphens (multi-word titles)
            deny=r'/(about-us|contact-us|privacy|terms|donate|subscribe|newsletter|author|category|tag|page|wp-|feed|in-focus|china-briefing|comments-policy|support-us|cookies|energy|science|policy|nature|global-south-climate-database|newsletter-sign-up|webinar-|thank-you)/'
        ), callback='parse_article', follow=False),
        
        # Follow homepage for article discovery
        Rule(LinkExtractor(
            allow=r'^https://www\.carbonbrief\.org/?$'
        ), follow=True),
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