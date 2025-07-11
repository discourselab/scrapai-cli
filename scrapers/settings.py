# Scrapy settings for scrapai_project

BOT_NAME = 'scrapai'

SPIDER_MODULES = ['scrapers.spiders']
NEWSPIDER_MODULE = 'scrapers.spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure delays for requests
DOWNLOAD_DELAY = 1
RANDOMIZE_DOWNLOAD_DELAY = True

# Configure concurrent requests
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# Enable AutoThrottle
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0

# User agent
USER_AGENT = 'scrapai (+https://github.com/discourselab/scrapai-cli)'

# Configure item pipelines
ITEM_PIPELINES = {
    'scrapers.pipelines.ScrapaiPipeline': 300,
}

# Enable and configure HTTP caching
HTTPCACHE_ENABLED = True
HTTPCACHE_EXPIRATION_SECS = 3600