"""SmartProxyMiddleware records proxy *successes* (200-after-proxy), not just attempts."""

import pytest
from scrapy.http import Request, HtmlResponse

from middlewares import SmartProxyMiddleware

pytestmark = pytest.mark.unit


def _mw():
    return SmartProxyMiddleware(settings=None, crawler=None)


def _pair(url, status, with_proxy):
    meta = {"proxy": "http://p:1"} if with_proxy else {}
    req = Request(url, meta=meta)
    resp = HtmlResponse(url=url, status=status, request=req, body=b"<html></html>")
    return req, resp


def test_proxied_200_is_a_success():
    mw = _mw()
    req, resp = _pair("http://x.com/a", 200, with_proxy=True)
    mw.process_response(req, resp)
    assert mw.stats["proxy_successes"] == 1


def test_direct_200_is_not_a_proxy_success():
    mw = _mw()
    req, resp = _pair("http://x.com/a", 200, with_proxy=False)
    mw.process_response(req, resp)
    assert mw.stats["proxy_successes"] == 0


def test_proxied_403_is_not_a_success():
    mw = _mw()
    req, resp = _pair("http://x.com/a", 403, with_proxy=True)
    mw.process_response(req, resp)
    assert mw.stats["proxy_successes"] == 0
