"""The curl_cffi handler must honor request.meta['proxy'] (previously dropped),
and carry proxy credentials on the tunnel only — never to the origin server."""

import base64

import pytest
from scrapy import Request

from handlers.curl_cffi_handler import proxies_from_request

pytestmark = pytest.mark.unit


def _auth_header(creds):
    return "Basic " + base64.b64encode(creds.encode()).decode()


def test_proxy_from_meta():
    req = Request("https://example.com", meta={"proxy": "http://u:p@host:1000"})
    assert proxies_from_request(req) == {
        "http": "http://u:p@host:1000",
        "https": "http://u:p@host:1000",
    }


def test_no_proxy_returns_none():
    req = Request("https://example.com")
    assert proxies_from_request(req) is None


def test_credentials_restored_from_proxy_authorization_header():
    # HttpProxyMiddleware strips creds out of meta['proxy'] into the header; curl_cffi
    # authenticates from the URL only, so they must go back or the proxy answers 407.
    req = Request(
        "https://example.com",
        meta={"proxy": "http://host:1000"},
        headers={"Proxy-Authorization": _auth_header("u:p")},
    )
    assert proxies_from_request(req) == {
        "http": "http://u:p@host:1000",
        "https": "http://u:p@host:1000",
    }


def test_credentials_in_url_win_over_the_header():
    # a meta['proxy'] that still carries its own credentials is left alone
    req = Request(
        "https://example.com",
        meta={"proxy": "http://real:secret@host:1000"},
        headers={"Proxy-Authorization": _auth_header("other:creds")},
    )
    assert proxies_from_request(req)["http"] == "http://real:secret@host:1000"


def test_proxy_authorization_never_reaches_the_origin():
    # the handler builds outgoing headers from the request, then drops the tunnel's
    # credentials — they belong to the proxy, not the site being crawled
    from handlers.curl_cffi_handler import CurlCffiDownloadHandler

    captured = {}

    class _FakeSpider:
        custom_settings = {}

    def _fake_get(url, **kwargs):
        captured.update(kwargs.get("headers") or {})
        raise RuntimeError("stop after header assembly")

    req = Request(
        "https://example.com",
        meta={"proxy": "http://host:1000"},
        headers={"Proxy-Authorization": _auth_header("u:p"), "Accept": "text/html"},
    )
    handler = CurlCffiDownloadHandler(settings={})
    import handlers.curl_cffi_handler as mod

    original = mod.cffi_requests.get
    mod.cffi_requests.get = _fake_get
    try:
        with pytest.raises(RuntimeError):
            handler._fetch_sync(req, _FakeSpider())
    finally:
        mod.cffi_requests.get = original

    assert "Accept" in captured  # the rest of the headers still go out
    assert not any(k.lower() == "proxy-authorization" for k in captured)
