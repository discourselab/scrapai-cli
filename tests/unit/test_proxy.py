"""Tests for the single proxy source of truth (core/proxy.py)."""

import pytest

from core import proxy

pytestmark = pytest.mark.unit

PVARS = [
    "DATACENTER_PROXY_URL",
    "DATACENTER_PROXY_USERNAME",
    "DATACENTER_PROXY_PASSWORD",
    "DATACENTER_PROXY_HOST",
    "DATACENTER_PROXY_PORT",
    "RESIDENTIAL_PROXY_URL",
    "RESIDENTIAL_PROXY_USERNAME",
    "RESIDENTIAL_PROXY_PASSWORD",
    "RESIDENTIAL_PROXY_HOST",
    "RESIDENTIAL_PROXY_PORT",
    "ISP_PROXY_URL",
    "ISP_PROXY_USERNAME",
    "ISP_PROXY_PASSWORD",
    "ISP_PROXY_HOST",
    "ISP_PROXY_PORT",
]

ISP = "http://i:s@isp.x.com:3000"

DC = "http://u:p@dc.x.com:1000"
RES = "http://r:q@res.x.com:2000"


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    for v in PVARS:
        monkeypatch.delenv(v, raising=False)


def _set_dc(monkeypatch):
    monkeypatch.setenv("DATACENTER_PROXY_USERNAME", "u")
    monkeypatch.setenv("DATACENTER_PROXY_PASSWORD", "p")
    monkeypatch.setenv("DATACENTER_PROXY_HOST", "dc.x.com")
    monkeypatch.setenv("DATACENTER_PROXY_PORT", "1000")


def _set_res(monkeypatch):
    monkeypatch.setenv("RESIDENTIAL_PROXY_USERNAME", "r")
    monkeypatch.setenv("RESIDENTIAL_PROXY_PASSWORD", "q")
    monkeypatch.setenv("RESIDENTIAL_PROXY_HOST", "res.x.com")
    monkeypatch.setenv("RESIDENTIAL_PROXY_PORT", "2000")


class TestUrls:
    def test_datacenter_from_components(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.datacenter_url() == DC

    def test_full_url_overrides_components(self, monkeypatch):
        _set_dc(monkeypatch)
        monkeypatch.setenv("DATACENTER_PROXY_URL", "http://full@host:9")
        assert proxy.datacenter_url() == "http://full@host:9"

    def test_none_when_unset(self):
        assert proxy.datacenter_url() is None
        assert proxy.residential_url() is None


class TestSelect:
    def test_datacenter(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.select("datacenter") == (DC, "datacenter")

    def test_static_alias_is_datacenter(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.select("static") == (DC, "datacenter")

    def test_residential_unconfigured(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.select("residential") == (None, None)

    def test_auto_prefers_datacenter(self, monkeypatch):
        _set_dc(monkeypatch)
        _set_res(monkeypatch)
        assert proxy.select("auto") == (DC, "datacenter")

    def test_auto_falls_back_to_residential(self, monkeypatch):
        _set_res(monkeypatch)
        assert proxy.select("auto") == (RES, "residential")

    def test_none_mode(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.select("none") == (None, None)

    def test_nothing_configured(self):
        assert proxy.select("auto") == (None, None)


def _set_isp(monkeypatch):
    monkeypatch.setenv("ISP_PROXY_USERNAME", "i")
    monkeypatch.setenv("ISP_PROXY_PASSWORD", "s")
    monkeypatch.setenv("ISP_PROXY_HOST", "isp.x.com")
    monkeypatch.setenv("ISP_PROXY_PORT", "3000")


class TestNamedProxies:
    def test_arbitrary_name_from_components(self, monkeypatch):
        _set_isp(monkeypatch)
        assert proxy.url_for("isp") == ISP
        assert proxy.select("isp") == (ISP, "isp")

    def test_arbitrary_name_full_url(self, monkeypatch):
        monkeypatch.setenv("MOBILE_PROXY_URL", "http://m@mob:1")
        assert proxy.select("mobile") == ("http://m@mob:1", "mobile")

    def test_unknown_name_fails_loud_not_silent(self, monkeypatch):
        # datacenter IS configured, but selecting an unconfigured 'isp' must NOT
        # silently fall back to datacenter — it returns nothing.
        _set_dc(monkeypatch)
        assert proxy.select("isp") == (None, None)

    def test_chain_named(self, monkeypatch):
        _set_isp(monkeypatch)
        assert proxy.chain("isp") == [ISP]

    def test_chain_unknown_name_is_direct(self):
        assert proxy.chain("isp") == [None]

    def test_configured_names(self, monkeypatch):
        _set_dc(monkeypatch)
        _set_isp(monkeypatch)
        assert proxy.configured_names() == ["datacenter", "isp"]

    def test_configured_names_empty(self):
        assert proxy.configured_names() == []


class TestChain:
    def test_auto_full_chain(self, monkeypatch):
        _set_dc(monkeypatch)
        _set_res(monkeypatch)
        assert proxy.chain("auto") == [None, DC, RES]

    def test_residential_only(self, monkeypatch):
        _set_res(monkeypatch)
        assert proxy.chain("residential") == [RES]

    def test_none_is_direct(self):
        assert proxy.chain("none") == [None]

    def test_static_chain(self, monkeypatch):
        _set_dc(monkeypatch)
        assert proxy.chain("static") == [DC]
