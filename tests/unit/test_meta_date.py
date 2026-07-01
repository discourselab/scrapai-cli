"""Publish date from STRUCTURED metadata, never from newspaper/trafilatura guesses.

Order: OG article:published_time -> JSON-LD datePublished (incl @graph) ->
itemprop datePublished -> <time datetime>. Parsed with dateutil (ISO). None if
absent/unparseable — a null beats a wrong date silently corrupting the corpus.
"""

import datetime

import pytest

from core.extractors import extract_meta_date, extract_meta_author

pytestmark = pytest.mark.unit


def test_og_article_published_time():
    html = (
        '<meta property="article:published_time" content="2026-06-30T11:00:00+00:00">'
    )
    d = extract_meta_date(html)
    assert d.year == 2026 and d.month == 6 and d.day == 30 and d.hour == 11


def test_jsonld_date_published():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"NewsArticle","datePublished":"2025-11-07T09:34:06-06:00"}</script>'
    )
    assert extract_meta_date(html).year == 2025


def test_jsonld_graph_nested():
    html = (
        '<script type="application/ld+json">'
        '{"@graph":[{"@type":"WebSite"},{"@type":"NewsArticle","datePublished":"2024-01-15T08:00:00Z"}]}'
        "</script>"
    )
    assert extract_meta_date(html).month == 1


def test_itemprop_date_published():
    html = '<meta itemprop="datePublished" content="2023-05-21T12:00:00-05:00">'
    assert extract_meta_date(html).year == 2023


def test_time_datetime():
    html = '<article><time datetime="2022-03-10T06:30:00+00:00">hace tiempo</time></article>'
    assert extract_meta_date(html).day == 10


def test_og_wins_over_jsonld():
    html = (
        '<meta property="article:published_time" content="2026-06-30T11:00:00+00:00">'
        '<script type="application/ld+json">{"datePublished":"2000-01-01T00:00:00Z"}</script>'
    )
    assert extract_meta_date(html).year == 2026  # OG preferred


def test_z_suffix_parses():
    html = '<meta property="article:published_time" content="2026-06-30T13:18:51.693Z">'
    d = extract_meta_date(html)
    assert isinstance(d, datetime.datetime) and d.year == 2026


def test_no_date_returns_none():
    assert extract_meta_date("<html><body>no dates here</body></html>") is None


def test_malformed_does_not_crash():
    html = '<meta property="article:published_time" content="not a date">'
    assert extract_meta_date(html) is None


def test_malformed_jsonld_skipped():
    html = '<script type="application/ld+json">{bad json,,,</script>'
    assert extract_meta_date(html) is None


def test_empty_html():
    assert extract_meta_date("") is None
    assert extract_meta_date(None) is None


# --- structured author (extruct, JSON-LD) ---------------------------------


def _jsonld(body):
    return f'<script type="application/ld+json">{body}</script>'


def test_author_dict_name():
    html = _jsonld('{"@type":"NewsArticle","author":{"name":"Brenda Camarillo"}}')
    assert extract_meta_author(html) == "Brenda Camarillo"


def test_author_plain_string():
    html = _jsonld('{"@type":"NewsArticle","author":"Juan Pérez"}')
    assert extract_meta_author(html) == "Juan Pérez"


def test_author_list_joined():
    html = _jsonld(
        '{"@type":"NewsArticle","author":[{"name":"Ana Ruiz"},{"name":"Luis Gómez"}]}'
    )
    assert extract_meta_author(html) == "Ana Ruiz, Luis Gómez"


def test_author_in_graph():
    html = _jsonld(
        '{"@graph":[{"@type":"WebSite"},{"@type":"NewsArticle","author":{"name":"Sofía Díaz"}}]}'
    )
    assert extract_meta_author(html) == "Sofía Díaz"


def test_author_url_skipped():
    html = _jsonld('{"@type":"NewsArticle","author":"https://facebook.com/foo"}')
    assert extract_meta_author(html) is None


def test_author_none_when_absent():
    assert extract_meta_author("<html><body>no author</body></html>") is None
    assert extract_meta_author("") is None
