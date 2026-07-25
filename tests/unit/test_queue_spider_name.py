"""Spider-name derivation from URL (queue complete).

Pins the fix for lstrip("www.") stripping a char-set, not a prefix:
www.wsj.com must become wsj_com, not sj_com.
"""

from cli.queue import _spider_name_from_url


def test_www_prefix_stripped():
    assert _spider_name_from_url("https://www.example.com/page") == "example_com"


def test_lstrip_charset_bug_wsj():
    # lstrip("www.") would eat the leading "w" of wsj -> "sj_com"
    assert _spider_name_from_url("https://www.wsj.com/news") == "wsj_com"


def test_no_www():
    assert _spider_name_from_url("https://blog.python.org/") == "blog_python_org"


def test_hyphen_replaced():
    assert _spider_name_from_url("https://my-site.com") == "my_site_com"
