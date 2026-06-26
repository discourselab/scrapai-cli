"""`analyze --test` must accept the SAME selectors a spider runs — including
Scrapy's `::text` and `::attr(...)` pseudo-elements — so a selector can be
verified before it goes into a section's extract. _select_values is the engine.
"""

import pytest

from cli.analyze import _select_values

pytestmark = pytest.mark.unit


def test_text_pseudo_element():
    assert _select_values("<h1 class='t'>Hello</h1>", "h1::text") == ["Hello"]


def test_attr_pseudo_element():
    html = '<meta property="og:image" content="https://x.com/i.jpg">'
    assert _select_values(html, 'meta[property="og:image"]::attr(content)') == [
        "https://x.com/i.jpg"
    ]


def test_element_selector_returns_html():
    out = _select_values("<div class='b'>hi</div>", "div.b")
    assert len(out) == 1 and "hi" in out[0]


def test_get_all_multiple_matches():
    assert _select_values("<ul><li>a</li><li>b</li></ul>", "li::text") == ["a", "b"]


def test_no_match_returns_empty():
    assert _select_values("<p>x</p>", "h1::text") == []
