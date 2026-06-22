#!/usr/bin/env python3
"""
Scrapy middlewares for proxy support and enhanced downloading
"""

import os
import logging
from scrapy import signals
from dotenv import load_dotenv
from urllib.parse import urlparse

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

        # Load datacenter proxy credentials
        dc_username = os.getenv("DATACENTER_PROXY_USERNAME")
        dc_password = os.getenv("DATACENTER_PROXY_PASSWORD")
        dc_host = os.getenv("DATACENTER_PROXY_HOST")
        dc_port = os.getenv("DATACENTER_PROXY_PORT")

        # Load residential proxy credentials
        res_username = os.getenv("RESIDENTIAL_PROXY_USERNAME")
        res_password = os.getenv("RESIDENTIAL_PROXY_PASSWORD")
        res_host = os.getenv("RESIDENTIAL_PROXY_HOST")
        res_port = os.getenv("RESIDENTIAL_PROXY_PORT")

        # Check what's configured
        self.datacenter_configured = all([dc_username, dc_password, dc_host, dc_port])
        self.residential_configured = all(
            [res_username, res_password, res_host, res_port]
        )

        # Determine active proxy based on mode
        if self.proxy_mode == "residential":
            # Explicit residential mode
            if self.residential_configured:
                self.proxy_url = (
                    f"http://{res_username}:{res_password}@{res_host}:{res_port}"
                )
                self.proxy_available = True
                self.active_proxy_type = "residential"
                logger.info(f"✅ Residential proxy enabled: {res_host}:{res_port}")
                logger.info("📋 Strategy: Direct → Residential (explicit mode)")
            else:
                self.proxy_available = False
                self.active_proxy_type = None
                logger.error(
                    "❌ Residential proxy requested but "
                    "RESIDENTIAL_PROXY_* vars not configured in .env"
                )
                logger.error("   Please add residential proxy credentials")
        elif self.proxy_mode == "datacenter":
            # Explicit datacenter mode
            if self.datacenter_configured:
                self.proxy_url = (
                    f"http://{dc_username}:{dc_password}@{dc_host}:{dc_port}"
                )
                self.proxy_available = True
                self.active_proxy_type = "datacenter"
                logger.info(f"✅ Datacenter proxy enabled: {dc_host}:{dc_port}")
                logger.info("📋 Strategy: Direct → Datacenter (explicit mode)")
            else:
                self.proxy_available = False
                self.active_proxy_type = None
                logger.warning(
                    "⚠️  Datacenter proxy not configured - only direct connections available"
                )
        else:
            # Auto mode (default): prefer datacenter, escalate to expert-in-the-loop for residential
            if self.datacenter_configured:
                self.proxy_url = (
                    f"http://{dc_username}:{dc_password}@{dc_host}:{dc_port}"
                )
                self.proxy_available = True
                self.active_proxy_type = "datacenter"
                logger.info(
                    f"✅ Auto mode: Datacenter proxy available: {dc_host}:{dc_port}"
                )
                logger.info("📋 Strategy: Direct → Datacenter → Expert-in-the-loop")
                if self.residential_configured:
                    logger.info(
                        "💡 Residential proxy detected (will prompt if datacenter fails)"
                    )
            elif self.residential_configured:
                # No datacenter, but residential available - use it in auto mode
                self.proxy_url = (
                    f"http://{res_username}:{res_password}@{res_host}:{res_port}"
                )
                self.proxy_available = True
                self.active_proxy_type = "residential"
                logger.info(
                    f"✅ Auto mode: Residential proxy available: {res_host}:{res_port}"
                )
                logger.info(
                    "📋 Strategy: Direct → Residential (only proxy configured)"
                )
            else:
                self.proxy_available = False
                self.active_proxy_type = None
                logger.warning(
                    "⚠️  No proxies configured - only direct connections available"
                )

        # Track domains that require proxy (learned from 403/429/503 errors)
        self.blocked_domains = set()

        # Track domains that failed even with current proxy (for expert-in-the-loop)
        self.failed_with_proxy_domains = set()

        # Flag to show expert-in-the-loop message only once
        self.expert_message_shown = False

        # Statistics
        self.stats = {"direct_requests": 0, "proxy_requests": 0, "blocked_retries": 0}

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
        proxy_from_start = bool(
            getattr(spider, "custom_settings", {}).get("PROXY_FROM_START")
        ) if spider else False
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
        logger.info(f"📊 Proxy Statistics for '{spider.name}':")
        logger.info(f"   Direct requests: {self.stats['direct_requests']}")
        logger.info(f"   Proxy requests: {self.stats['proxy_requests']}")
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
