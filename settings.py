# Scrapy settings for scrapai_project

BOT_NAME = 'scrapai'

SPIDER_MODULES = ['spiders']
NEWSPIDER_MODULE = 'spiders'

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

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
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

# Configure item pipelines
ITEM_PIPELINES = {
    'pipelines.ScrapaiPipeline': 300,
    'pipelines.DatabasePipeline': 400,
}

# Enable smart proxy middleware (only uses proxy on 403/429 errors)
DOWNLOADER_MIDDLEWARES = {
    'middlewares.SmartProxyMiddleware': 350,
}

# Cloudflare bypass download handler
# This will be activated when spider has CLOUDFLARE_ENABLED=True
DOWNLOAD_HANDLERS = {
    'http': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
    'https': 'handlers.cloudflare_handler.CloudflareDownloadHandler',
}

# Enable and configure HTTP caching
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 3600

# Suppress verbose logs from third-party libraries
import logging
logging.getLogger('nodriver').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('playwright').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)