"""`scrapai crawl` with no --limit submits itself to Pueue (detached) so a full
crawl survives SSH disconnect. The only non-trivial bit is rebuilding the crawl
invocation with its flags for the detached re-run — that's what this checks.
"""

import pytest

from cli.crawl import _build_detached_cmd

pytestmark = pytest.mark.unit


def test_omits_defaults():
    cmd = _build_detached_cmd("/repo/scrapai", "bbc_com", "news")
    assert cmd[:5] == ["/repo/scrapai", "crawl", "bbc_com", "--project", "news"]
    assert "--detached" in cmd
    for flag in ("--browser", "--proxy-type", "--reset-deltafetch", "--save-html"):
        assert flag not in cmd


def test_passes_flags_through():
    cmd = _build_detached_cmd(
        "/repo/scrapai", "bbc_com", "news",
        proxy_type="residential", browser=True, reset_deltafetch=True,
        save_html=True, timeout=3600, scrapy_args="-L DEBUG", output="out.jsonl",
    )
    for flag in ("--browser", "--reset-deltafetch", "--save-html", "--detached"):
        assert flag in cmd
    for flag, val in [("--proxy-type", "residential"), ("--timeout", "3600"),
                      ("--scrapy-args", "-L DEBUG"), ("--output", "out.jsonl")]:
        i = cmd.index(flag)
        assert cmd[i:i + 2] == [flag, val]
