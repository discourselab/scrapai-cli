"""analyze find_by_text: locate the element that holds a value you SAW in the
screenshot (author name, date, title) and return a usable selector — even when
the class name is obfuscated. This is the vision -> value -> selector workflow."""

import pytest

from cli.analyze import find_by_text

pytestmark = pytest.mark.unit

HTML = """<html><body>
<article class="post">
  <h1 class="headline">Big News Today</h1>
  <span class="author-name">John Smith</span>
  <time class="css-1a2b3c">June 20, 2026</time>
  <div id="byline">By Jane Doe</div>
  <p>A long body paragraph that goes on and on and definitely should not be
     returned as the selector for any short field value we search for here.</p>
</article></body></html>"""


def test_finds_author_by_its_value():
    m = find_by_text(HTML, "John Smith")
    assert m
    assert m[0]["selector"] == "span.author-name"
    assert "John Smith" in m[0]["text"]


def test_finds_obfuscated_date_by_value():
    # class name is meaningless (css-1a2b3c) — value search still nails it,
    # where --find 'date' (class/id keyword) would miss entirely.
    m = find_by_text(HTML, "June 20, 2026")
    assert m[0]["selector"] == "time.css-1a2b3c"


def test_finds_by_id_selector():
    m = find_by_text(HTML, "Jane Doe")
    assert m[0]["selector"] == "div#byline"


def test_tightest_container_first():
    # "John Smith" is inside <span>, <article>, <body> too — the leaf wins.
    m = find_by_text(HTML, "John Smith")
    assert m[0]["selector"] == "span.author-name"


def test_case_insensitive():
    m = find_by_text(HTML, "john smith")
    assert m and m[0]["selector"] == "span.author-name"


def test_no_match_returns_empty():
    assert find_by_text(HTML, "Nonexistent Value") == []
