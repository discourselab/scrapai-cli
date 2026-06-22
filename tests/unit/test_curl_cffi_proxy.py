"""The curl_cffi handler must honor request.meta['proxy'] (previously dropped)."""

import pytest
from scrapy import Request

from handlers.curl_cffi_handler import proxies_from_request

pytestmark = pytest.mark.unit


def test_proxy_from_meta():
    req = Request("https://example.com", meta={"proxy": "http://u:p@host:1000"})
    assert proxies_from_request(req) == {
        "http": "http://u:p@host:1000",
        "https": "http://u:p@host:1000",
    }


def test_no_proxy_returns_none():
    req = Request("https://example.com")
    assert proxies_from_request(req) is None
