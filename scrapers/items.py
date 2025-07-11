import scrapy

class ArticleItem(scrapy.Item):
    """Base article item for all scraped articles"""
    url = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    published_date = scrapy.Field()
    author = scrapy.Field()
    tags = scrapy.Field()
    source = scrapy.Field()
    scraped_at = scrapy.Field()