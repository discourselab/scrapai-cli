"""
Scrapy download handler using curl_cffi for TLS fingerprint impersonation.

Bypasses TLS-based bot detection (e.g. derstandard.at) by impersonating a real
Chrome browser at the TLS handshake level — something Scrapy/Twisted cannot do.

Activated via spider setting: CURL_CFFI_ENABLED: true
"""

import gzip
import logging

from curl_cffi import requests as cffi_requests
from scrapy.http import HtmlResponse, TextResponse, Request
from twisted.internet import threads

logger = logging.getLogger(__name__)


class CurlCffiDownloadHandler:
    """
    Download handler that uses curl_cffi with Chrome TLS impersonation.

    Activated per-spider via: CURL_CFFI_ENABLED: true

    Settings:
    - CURL_CFFI_IMPERSONATE: Chrome version to impersonate (default: 'chrome')
    - CURL_CFFI_TIMEOUT: Request timeout in seconds (default: 30)
    """

    lazy = True

    def __init__(self, settings, crawler=None):
        self.settings = settings
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings, crawler)

    def open(self):
        logger.info("CurlCffiDownloadHandler: Ready (Chrome TLS impersonation)")

    def close(self):
        pass

    def download_request(self, request: Request, spider):
        return threads.deferToThread(self._fetch_sync, request, spider)

    def _fetch_sync(self, request: Request, spider):
        spider_settings = getattr(spider, "custom_settings", {})
        impersonate = spider_settings.get("CURL_CFFI_IMPERSONATE", "chrome")
        timeout = spider_settings.get("CURL_CFFI_TIMEOUT", 30)

        # Build headers from request
        # Scrapy headers have list values — flatten to strings for curl_cffi
        headers = {
            k: v[0] if isinstance(v, list) and len(v) == 1 else (", ".join(v) if isinstance(v, list) else v)
            for k, v in request.headers.to_unicode_dict().items()
        }

        # DEFAULT_REQUEST_HEADERS is set dynamically so DefaultHeadersMiddleware
        # never sees it — inject manually from spider.custom_settings
        default_headers = spider_settings.get("DEFAULT_REQUEST_HEADERS", {})
        for k, v in default_headers.items():
            if k not in headers:
                headers[k] = v

        if "Cookie" in headers:
            logger.debug(f"Cookie header: {headers['Cookie'][:80]}...")
        else:
            logger.debug("No Cookie header for this request")

        try:
            response = cffi_requests.get(
                request.url,
                headers=headers,
                impersonate=impersonate,
                timeout=timeout,
                allow_redirects=True,
            )

            url_lower = response.url.lower()

            if url_lower.endswith(".gz"):
                # Decompress gzip in handler — Scrapy middlewares expect text responses
                raw = gzip.decompress(response.content)
                resp_headers = {
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")
                }
                logger.debug(
                    f"curl_cffi fetch (gz): {request.url} -> {response.status_code} "
                    f"({len(raw)} bytes decompressed)"
                )
                return TextResponse(
                    url=response.url,
                    status=response.status_code,
                    headers=resp_headers,
                    body=raw,
                    encoding="utf-8",
                    request=request,
                )
            else:
                body = response.text.encode("utf-8")
                # Strip content-encoding — already decoded by curl_cffi
                resp_headers = {
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ("content-encoding", "transfer-encoding")
                }
                logger.debug(
                    f"curl_cffi fetch: {request.url} -> {response.status_code} "
                    f"({len(body)} bytes, final url: {response.url})"
                )
                return HtmlResponse(
                    url=response.url,
                    status=response.status_code,
                    headers=resp_headers,
                    body=body,
                    encoding="utf-8",
                    request=request,
                )

        except Exception as e:
            logger.error(f"curl_cffi fetch failed for {request.url}: {e}")
            raise
