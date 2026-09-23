"""Dead-proxy detection + fail-open to direct (docs/requests/16).

A dead escalation proxy (CONNECT refused/403, hangs) used to wedge auto-mode
crawls: one page-level 403 marked the domain blocked, every request was routed
through the broken tunnel, and each burned timeout x retries. The middleware
now counts consecutive transport failures of proxied requests, declares the
proxy dead at the threshold, and fails open to direct connections. Compliance
witness probes must never mark a domain blocked.
"""

import pytest
from scrapy.http import Request, HtmlResponse

from middlewares import SmartProxyMiddleware

pytestmark = pytest.mark.unit


def _mw(mode="auto"):
    mw = SmartProxyMiddleware(settings=None, crawler=None)
    mw.proxy_mode = mode
    mw.proxy_available = True
    mw.proxy_url = "http://p:1"
    mw.active_proxy_type = "datacenter"
    return mw


def _proxied_request(url="http://x.com/a"):
    return Request(url, meta={"proxy": "http://p:1"})


def _response(req, status=200):
    return HtmlResponse(url=req.url, status=status, request=req, body=b"<html></html>")


def _fail_n(mw, n):
    out = None
    for i in range(n):
        out = mw.process_exception(
            _proxied_request(f"http://x.com/{i}"), OSError("boom")
        )
    return out


def test_threshold_declares_dead_and_reissues_direct():
    mw = _mw()
    mw.blocked_domains.add("x.com")
    retry = _fail_n(mw, mw.proxy_dead_threshold)
    assert mw.proxy_dead is True
    assert mw.blocked_domains == set()
    assert retry is not None and "proxy" not in retry.meta


def test_below_threshold_keeps_escalating():
    mw = _mw()
    assert _fail_n(mw, mw.proxy_dead_threshold - 1) is None
    assert mw.proxy_dead is False


def test_any_proxied_response_resets_counter():
    mw = _mw()
    _fail_n(mw, mw.proxy_dead_threshold - 1)
    req = _proxied_request()
    mw.process_response(req, _response(req, status=403))  # site answered: tunnel works
    assert mw._proxy_consecutive_failures == 0
    _fail_n(mw, mw.proxy_dead_threshold - 1)
    assert mw.proxy_dead is False


def test_direct_failures_do_not_count():
    mw = _mw()
    for _ in range(mw.proxy_dead_threshold + 1):
        assert mw.process_exception(Request("http://x.com/a"), OSError("boom")) is None
    assert mw.proxy_dead is False


def test_dead_proxy_stops_escalation_and_strips_meta():
    mw = _mw()
    _fail_n(mw, mw.proxy_dead_threshold)
    # a fresh 403 no longer escalates
    req = Request("http://y.com/a")
    resp = _response(req, status=403)
    assert mw.process_response(req, resp) is resp
    assert "y.com" not in mw.blocked_domains
    # scheduled/retried requests still carrying the proxy get it stripped
    stale = _proxied_request("http://x.com/z")
    mw.process_request(stale)
    assert "proxy" not in stale.meta


def test_residential_mode_is_never_failed_open():
    mw = _mw(mode="residential")
    assert _fail_n(mw, mw.proxy_dead_threshold + 2) is None
    assert mw.proxy_dead is False


def test_compliance_probe_403_does_not_poison_domain():
    mw = _mw()
    req = Request("http://x.com/llms.txt", meta={"compliance_file": "llms_x.txt"})
    resp = _response(req, status=403)
    assert mw.process_response(req, resp) is resp
    assert mw.blocked_domains == set()
