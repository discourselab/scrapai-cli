#!/usr/bin/env python3
"""
Scrapy middlewares for proxy support and enhanced downloading
"""

import logging
import time
from scrapy import signals, Request
from scrapy_deltafetch import DeltaFetch
from dotenv import load_dotenv
from urllib.parse import urlparse

from core import proxy

load_dotenv()
logger = logging.getLogger(__name__)


class SmartProxyMiddleware:
    """
    Intelligent proxy middleware that only uses proxies when encountering rate limits or blocks.

    Strategy (auto mode - default):
    1. Start with direct connections (no proxy)
    2. Detect 403/429/503 errors (blocked/rate-limited/unavailable)
    3. Retry with datacenter proxy (if configured)
    4. If datacenter fails → expert-in-the-loop (ask user to use residential)

    Expert-in-the-loop: Expensive proxies (residential) require explicit user approval.
    """

    def __init__(self, settings=None, crawler=None):
        # Store crawler reference for accessing spider (Scrapy new API)
        self.crawler = crawler

        # Determine proxy type (auto, datacenter, or residential)
        self.proxy_mode = settings.get("PROXY_TYPE", "auto") if settings else "auto"

        # All proxy URLs come from core.proxy — the single, env-driven source.
        self.datacenter_configured = proxy.datacenter_url() is not None
        self.residential_configured = proxy.residential_url() is not None
        self.proxy_url, self.active_proxy_type = proxy.select(self.proxy_mode)
        self.proxy_available = self.proxy_url is not None

        if self.proxy_available:
            logger.info(
                f"✅ Proxy active: {self.active_proxy_type} (mode={self.proxy_mode}). "
                "Strategy: Direct → proxy on block."
            )
            if self.proxy_mode == "auto" and self.residential_configured:
                logger.info(
                    "💡 Residential proxy detected (will prompt if datacenter fails)"
                )
        else:
            logger.warning(
                f"⚠️  No proxy active (mode={self.proxy_mode}) — direct connections only"
            )

        # Track domains that require proxy (learned from 403/429/503 errors)
        self.blocked_domains = set()

        # Track domains that failed even with current proxy (for expert-in-the-loop)
        self.failed_with_proxy_domains = set()

        # Flag to show expert-in-the-loop message only once
        self.expert_message_shown = False

        # Statistics
        self.stats = {
            "direct_requests": 0,
            "proxy_requests": 0,  # proxy attempts
            "proxy_successes": 0,  # proxied requests that came back 200
            "blocked_retries": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(settings=crawler.settings, crawler=crawler)
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def process_request(self, request):
        """
        Decide whether to use proxy based on domain history.
        - Explicit residential mode OR spider setting PROXY_FROM_START: proxy every request from the start.
        - Otherwise: proxy only for domains previously seen to block (403/429/503).
        """
        domain = urlparse(request.url).netloc

        # Spider opted into "proxy from start" or explicit residential mode → always proxy
        spider = getattr(self, "crawler", None) and self.crawler.spider
        proxy_from_start = (
            bool(getattr(spider, "custom_settings", {}).get("PROXY_FROM_START"))
            if spider
            else False
        )
        if (
            (self.proxy_mode == "residential" or proxy_from_start)
            and self.proxy_available
            and not request.meta.get("proxy")
        ):
            request.meta["proxy"] = self.proxy_url
            self.stats["proxy_requests"] += 1
            return None

        # Check if this domain needs proxy (learned from previous blocks)
        if domain in self.blocked_domains and self.proxy_available:
            if not request.meta.get("proxy"):
                request.meta["proxy"] = self.proxy_url
                self.stats["proxy_requests"] += 1
                logger.debug(f"🔒 Using proxy for known-blocked domain: {domain}")
        else:
            # Direct connection (no proxy)
            self.stats["direct_requests"] += 1

        return None

    def process_response(self, request, response):
        """
        Detect rate limiting (429), blocking (403), or service-unavailable (503) and retry with proxy.
        Implements expert-in-the-loop for expensive proxy escalation.
        """
        domain = urlparse(request.url).netloc

        # Check for rate limiting or blocking
        if response.status in [403, 429, 503]:
            # Check if we already tried with proxy
            if request.meta.get("proxy"):
                # Already used proxy and still blocked
                self.failed_with_proxy_domains.add(domain)
                logger.error(
                    f"❌ Blocked even with {self.active_proxy_type} proxy "
                    f"({response.status}): {request.url}"
                )

                # Expert-in-the-loop: suggest residential if in auto mode with datacenter
                if (
                    self.proxy_mode == "auto"
                    and self.active_proxy_type == "datacenter"
                    and self.residential_configured
                    and not self.expert_message_shown
                ):
                    self._show_expert_message()

                return response

            # First block - retry with proxy if available
            if self.proxy_available:
                logger.warning(f"⚠️  Blocked ({response.status}): {request.url}")
                logger.info(f"🔄 Retrying with {self.active_proxy_type} proxy...")

                # Remember this domain needs proxy
                self.blocked_domains.add(domain)
                self.stats["blocked_retries"] += 1

                # Create new request with proxy
                new_request = request.copy()
                new_request.meta["proxy"] = self.proxy_url
                new_request.dont_filter = True  # Allow retry even if URL was seen

                return new_request
            else:
                logger.error(
                    f"❌ Blocked ({response.status}) but no proxy available: {request.url}"
                )

        # Not blocked. If this request went through a proxy and returned 200,
        # the proxy actually got us through — record a real success (vs. attempt).
        if request.meta.get("proxy") and response.status == 200:
            self.stats["proxy_successes"] += 1
            if self.crawler is not None and getattr(self.crawler, "stats", None):
                self.crawler.stats.inc_value("proxy/success")

        return response

    def _show_expert_message(self):
        """Show expert-in-the-loop message for residential proxy escalation."""
        self.expert_message_shown = True
        spider_name = (
            self.crawler.spider.name
            if self.crawler and self.crawler.spider
            else "unknown"
        )
        logger.warning("")
        logger.warning("=" * 80)
        logger.warning(
            "⚠️  EXPERT-IN-THE-LOOP: Datacenter proxy failed for some domains"
        )
        logger.warning("")
        logger.warning("🏠 Residential proxy is available but may incur HIGHER COSTS")
        logger.warning("")
        logger.warning(
            f"Blocked domains: {', '.join(sorted(self.failed_with_proxy_domains))}"
        )
        logger.warning("")
        logger.warning("To proceed with residential proxy, run:")
        logger.warning(
            f"  ./scrapai crawl {spider_name} --project <project> --proxy-type residential"
        )
        logger.warning("")
        logger.warning("=" * 80)
        logger.warning("")

    def spider_opened(self, spider):
        # Store proxy type in spider state for checkpoint tracking
        if not hasattr(spider, "state"):
            spider.state = {}
        spider.state["proxy_type_used"] = self.proxy_mode

        if self.proxy_available:
            logger.info(
                f"🕷️  Spider '{spider.name}' started - Smart proxy mode enabled"
            )
            logger.info("   Strategy: Direct → Proxy on block (403/429/503)")
        else:
            logger.info(f"🕷️  Spider '{spider.name}' started - Direct connections only")

    def spider_closed(self, spider):
        """Log statistics when spider finishes"""
        attempts = self.stats["proxy_requests"]
        successes = self.stats["proxy_successes"]
        logger.info(f"📊 Proxy Statistics for '{spider.name}':")
        logger.info(f"   Direct requests: {self.stats['direct_requests']}")
        if attempts:
            pct = round(100 * successes / attempts)
            logger.info(
                f"   Proxy: {attempts} attempts, {successes} unblocked (200) "
                f"— {pct}% success"
            )
        else:
            logger.info("   Proxy: not used")
        logger.info(f"   Blocked & retried: {self.stats['blocked_retries']}")
        logger.info(f"   Blocked domains: {len(self.blocked_domains)}")
        if self.blocked_domains:
            logger.info(
                f"   Domains that needed proxy: {', '.join(sorted(self.blocked_domains))}"
            )

        # Show expert-in-the-loop message at end if not shown during crawl
        if (
            self.failed_with_proxy_domains
            and self.proxy_mode == "auto"
            and self.active_proxy_type == "datacenter"
            and self.residential_configured
            and not self.expert_message_shown
        ):
            self._show_expert_message()


class AsyncDeltaFetch(DeltaFetch):
    """DeltaFetch with async spider-output support for Scrapy 2.16+.

    Upstream ``scrapy_deltafetch.DeltaFetch`` only defines a synchronous
    ``process_spider_output`` generator. Scrapy 2.16 rejects that when the
    spider produces output asynchronously (our database spider does), raising
    a TypeError at engine start. This subclass adds an async-generator variant
    that applies the same skip/store logic over an async ``result`` stream.
    The sync method is kept (inherited) for non-async spiders.
    """

    async def process_spider_output_async(self, response, result, spider):
        async for r in result:
            if isinstance(r, Request):
                key = self._get_key(r)
                if key in self.db and self._is_enabled_for_request(r):
                    logger.info(f"Ignoring already visited: {r}")
                    if self.stats:
                        self.stats.inc_value("deltafetch/skipped", spider=spider)
                    continue
            else:
                key = self._get_key(response.request)
                self.db[key] = str(time.time())
                if self.stats:
                    self.stats.inc_value("deltafetch/stored", spider=spider)
            yield r
