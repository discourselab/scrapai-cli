#!/usr/bin/env python3
"""
Scrapy middlewares for proxy support and enhanced downloading
"""
import os
import logging
from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
logger = logging.getLogger(__name__)


class SmartProxyMiddleware:
    """
    Intelligent proxy middleware that only uses proxies when encountering rate limits or blocks.

    Strategy:
    1. Start with direct connections (no proxy)
    2. Detect 403/429 errors (blocked/rate-limited)
    3. Automatically retry with proxy
    4. Remember domains that need proxies
    """

    def __init__(self):
        # Load proxy credentials from environment
        self.proxy_username = os.getenv('DATACENTER_PROXY_USERNAME')
        self.proxy_password = os.getenv('DATACENTER_PROXY_PASSWORD')
        self.proxy_host = os.getenv('DATACENTER_PROXY_HOST')
        self.proxy_port = os.getenv('DATACENTER_PROXY_PORT')

        # Check if proxy is configured
        if all([self.proxy_username, self.proxy_password, self.proxy_host, self.proxy_port]):
            self.proxy_url = f"http://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}"
            self.proxy_available = True
            logger.info(f"✅ Datacenter proxy available: {self.proxy_host}:{self.proxy_port}")
            logger.info(f"📋 Strategy: Direct connections first, proxy on 403/429 errors")
        else:
            self.proxy_available = False
            logger.warning("⚠️  Datacenter proxy not configured - only direct connections available")

        # Track domains that require proxy (learned from 403/429 errors)
        self.blocked_domains = set()

        # Statistics
        self.stats = {
            'direct_requests': 0,
            'proxy_requests': 0,
            'blocked_retries': 0
        }

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def process_request(self, request, spider):
        """
        Decide whether to use proxy based on domain history.
        If domain was previously blocked, use proxy proactively.
        """
        domain = urlparse(request.url).netloc

        # Check if this domain needs proxy (learned from previous blocks)
        if domain in self.blocked_domains and self.proxy_available:
            if not request.meta.get('proxy'):
                request.meta['proxy'] = self.proxy_url
                self.stats['proxy_requests'] += 1
                logger.debug(f"🔒 Using proxy for known-blocked domain: {domain}")
        else:
            # Direct connection (no proxy)
            self.stats['direct_requests'] += 1

        return None

    def process_response(self, request, response, spider):
        """
        Detect rate limiting (429) or blocking (403) and retry with proxy.
        """
        domain = urlparse(request.url).netloc

        # Check for rate limiting or blocking
        if response.status in [403, 429]:
            # Check if we already tried with proxy
            if request.meta.get('proxy'):
                # Already used proxy and still blocked - give up
                logger.error(f"❌ Blocked even with proxy ({response.status}): {request.url}")
                return response

            # First block - retry with proxy if available
            if self.proxy_available:
                logger.warning(f"⚠️  Blocked ({response.status}): {request.url}")
                logger.info(f"🔄 Retrying with datacenter proxy...")

                # Remember this domain needs proxy
                self.blocked_domains.add(domain)
                self.stats['blocked_retries'] += 1

                # Create new request with proxy
                new_request = request.copy()
                new_request.meta['proxy'] = self.proxy_url
                new_request.dont_filter = True  # Allow retry even if URL was seen

                return new_request
            else:
                logger.error(f"❌ Blocked ({response.status}) but no proxy available: {request.url}")

        return response

    def spider_opened(self, spider):
        if self.proxy_available:
            logger.info(f"🕷️  Spider '{spider.name}' started - Smart proxy mode enabled")
            logger.info(f"   Strategy: Direct → Proxy on block (403/429)")
        else:
            logger.info(f"🕷️  Spider '{spider.name}' started - Direct connections only")

    def spider_closed(self, spider):
        """Log statistics when spider finishes"""
        logger.info(f"📊 Proxy Statistics for '{spider.name}':")
        logger.info(f"   Direct requests: {self.stats['direct_requests']}")
        logger.info(f"   Proxy requests: {self.stats['proxy_requests']}")
        logger.info(f"   Blocked & retried: {self.stats['blocked_retries']}")
        logger.info(f"   Blocked domains: {len(self.blocked_domains)}")
        if self.blocked_domains:
            logger.info(f"   Domains that needed proxy: {', '.join(sorted(self.blocked_domains))}")
