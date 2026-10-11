"""ComplianceFileCapture writes robots/llms witnesses beside the crawl output.

Covers the three behaviours that matter: a real plain-text file is saved
date-stamped under crawls/, an HTML soft-404 is never stored as a .txt witness,
and redirects are re-scheduled manually (spiders may run with
REDIRECT_ENABLED=False).
"""

from datetime import datetime
from unittest.mock import Mock

import pytest

from scrapy import Request
from scrapy.http import TextResponse

from extensions.compliance_files import ComplianceFileCapture

pytestmark = pytest.mark.unit


def _ext(tmp_path, monkeypatch):
    monkeypatch.setattr("core.config.DATA_DIR", str(tmp_path / "data"))
    ext = ComplianceFileCapture(Mock())
    spider = Mock()
    spider.spider_config.project = "proj"
    spider.spider_name = "x_com"
    ext.spider = spider
    return ext


def _resp(body, status=200, fname="robots.txt", headers=None, meta=None):
    url = "https://x.com/" + fname
    req = Request(url, meta={"compliance_file": fname, **(meta or {})})
    return TextResponse(
        url,
        body=body,
        status=status,
        headers=headers or {},
        request=req,
        encoding="utf-8",
    )


def test_saves_plain_text_witness(tmp_path, monkeypatch):
    ext = _ext(tmp_path, monkeypatch)
    ext._save(_resp(b"User-agent: *\nDisallow: /admin\n"))
    stamp = datetime.now().strftime("%d%m%Y")
    path = tmp_path / "data" / "proj" / "x_com" / "crawls" / f"robots_{stamp}.txt"
    assert path.read_bytes() == b"User-agent: *\nDisallow: /admin\n"


def test_html_soft_404_not_saved(tmp_path, monkeypatch):
    ext = _ext(tmp_path, monkeypatch)
    ext._save(_resp(b"<!doctype html><html>Not found page</html>", fname="llms.txt"))
    assert not (tmp_path / "data").exists()


def test_non_200_not_saved(tmp_path, monkeypatch):
    ext = _ext(tmp_path, monkeypatch)
    ext._save(_resp(b"User-agent: *\n", status=404))
    assert not (tmp_path / "data").exists()


def test_redirect_rescheduled_with_depth(tmp_path, monkeypatch):
    ext = _ext(tmp_path, monkeypatch)
    ext._save(
        _resp(b"", status=301, headers={"Location": "https://x.com/real-robots.txt"})
    )
    assert not (tmp_path / "data").exists()
    (req,), _ = ext.crawler.engine.crawl.call_args
    assert req.url == "https://x.com/real-robots.txt"
    assert req.meta["compliance_redirects"] == 1


def test_redirect_loop_capped(tmp_path, monkeypatch):
    ext = _ext(tmp_path, monkeypatch)
    ext._save(
        _resp(
            b"",
            status=302,
            headers={"Location": "https://x.com/again.txt"},
            meta={"compliance_redirects": 4},
        )
    )
    ext.crawler.engine.crawl.assert_not_called()
