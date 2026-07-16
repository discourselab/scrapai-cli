"""Unit tests for the repository-harvest spider (REPOSITORY_SOURCE / JSON:API).

The spider maps paginated JSON collection records to pipeline items. These tests
exercise the pure mapping layer (dot-paths, fallbacks, includes, templates,
processors, require-skip) and the parse/pagination flow without any DB access:
the spider is constructed via object.__new__ and configured directly.
"""

import json

import pytest
from scrapy.http import Request, TextResponse

from spiders.repository_spider import RepositoryDatabaseSpider

pytestmark = pytest.mark.unit


def make_spider(source):
    spider = object.__new__(RepositoryDatabaseSpider)
    spider.spider_name = "repo_test"
    spider._items_scraped = 0
    spider._item_limit = None
    spider._repo = source
    spider._records_path = source.get("records", "data")
    spider._next_path = source.get("next", "links.next.href")
    spider._included_key = source.get("included_key", "included")
    spider._require_field = source.get("require", "url")
    spider._map = source.get("map") or {}

    class _Cfg:
        id = 42

    spider.spider_config = _Cfg()
    return spider


def make_response(doc, url="https://repo.example/jsonapi/node/thing"):
    return TextResponse(
        url=url,
        body=json.dumps(doc).encode(),
        encoding="utf-8",
        request=Request(url),
    )


async def collect(gen):
    return [x async for x in gen] if hasattr(gen, "__anext__") else list(gen)


BASIC_SOURCE = {
    "records": "data",
    "next": "links.next.href",
    "require": "url",
    "map": {
        "url": {
            "path": "attributes.nid",
            "template": "https://repo.example/node/{}",
        },
        "title": "attributes.display_title || attributes.title",
        "published_date": {
            "path": "attributes.date_issued.0",
            "processors": [{"type": "parse_datetime"}],
        },
        "pdf_urls": {
            "include": "file",
            "path": "attributes.uri.url",
            "template": "https://repo.example{}",
            "list": True,
        },
    },
}


def record(nid, title=None, display=None, date=None, file_id=None):
    rec = {
        "type": "node--thing",
        "id": f"uuid-{nid}",
        "attributes": {
            "nid": nid,
            "title": title,
            "display_title": display,
            "date_issued": [date] if date else [],
        },
        "relationships": {},
    }
    if file_id:
        rec["relationships"]["file"] = {
            "data": {"type": "media--document", "id": file_id}
        }
    return rec


def included_file(file_id, path):
    return {
        "type": "media--document",
        "id": file_id,
        "attributes": {"uri": {"url": path}},
    }


def test_dig_walks_dicts_lists_and_negative_indices():
    dig = RepositoryDatabaseSpider._dig
    obj = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    assert dig(obj, "a.b.0.c") == 1
    assert dig(obj, "a.b.-1.c") == 2
    assert dig(obj, "a.b.5.c") is None
    assert dig(obj, "a.missing") is None
    assert dig(obj, "") == obj


def test_first_path_fallbacks_first_nonempty_wins():
    spider = make_spider(BASIC_SOURCE)
    obj = {"attributes": {"display_title": "", "title": "Real Title"}}
    value = spider._first_path(obj, "attributes.display_title || attributes.title")
    assert value == "Real Title"
    assert spider._first_path(obj, ["attributes.nope", "attributes.title"]) == (
        "Real Title"
    )
    assert spider._first_path(obj, None) is None


def test_build_item_maps_template_include_list_and_processors():
    spider = make_spider(BASIC_SOURCE)
    rec = record(7, title="T", date="1998-05-01", file_id="f1")
    included = spider._index_included([included_file("f1", "/files/report.pdf")])
    item = spider._build_item(rec, included)
    assert item["url"] == "https://repo.example/node/7"
    assert item["title"] == "T"
    assert str(item["published_date"]).startswith("1998-05-01")
    assert item["pdf_urls"] == ["https://repo.example/files/report.pdf"]
    assert item["spider_id"] == 42
    assert item["source"] == "repository_spider"


def test_build_item_missing_include_yields_null_field_not_crash():
    spider = make_spider(BASIC_SOURCE)
    rec = record(8, title="T", file_id="ghost")  # relationship present, not included
    item = spider._build_item(rec, included={})
    assert item["pdf_urls"] is None
    assert item["url"] == "https://repo.example/node/8"


def test_build_item_require_skips_records_without_url():
    spider = make_spider(BASIC_SOURCE)
    rec = record(None, title="unpublished parent")
    rec["attributes"]["nid"] = None
    assert spider._build_item(rec, included={}) is None


@pytest.mark.asyncio
async def test_parse_emits_items_and_follows_next_link():
    spider = make_spider(BASIC_SOURCE)
    doc = {
        "data": [record(1, title="A"), record(2, title="B")],
        "links": {"next": {"href": "https://repo.example/jsonapi?page[offset]=50"}},
    }
    results = [x async for x in spider.parse(make_response(doc))]
    items = [r for r in results if isinstance(r, dict)]
    requests = [r for r in results if isinstance(r, Request)]
    assert [i["url"] for i in items] == [
        "https://repo.example/node/1",
        "https://repo.example/node/2",
    ]
    assert len(requests) == 1
    assert "offset" in requests[0].url


@pytest.mark.asyncio
async def test_parse_stops_paging_on_last_page_and_bad_records_path():
    spider = make_spider(BASIC_SOURCE)
    last_page = {"data": [record(3, title="C")], "links": {}}
    results = [x async for x in spider.parse(make_response(last_page))]
    assert all(isinstance(r, dict) for r in results)

    not_a_list = {"data": {"oops": 1}, "links": {}}
    assert [x async for x in spider.parse(make_response(not_a_list))] == []


@pytest.mark.asyncio
async def test_parse_item_limit_stops_pagination():
    spider = make_spider(BASIC_SOURCE)
    spider._item_limit = 1
    doc = {
        "data": [record(1, title="A"), record(2, title="B")],
        "links": {"next": {"href": "https://repo.example/jsonapi?page[offset]=50"}},
    }
    results = [x async for x in spider.parse(make_response(doc))]
    assert not any(isinstance(r, Request) for r in results)
