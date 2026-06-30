"""GENERATED_URLS — lazy start-request generator from enumerable vars.

A URL template with {name} placeholders + a vars map; emits the cartesian
product of all vars. GET generation routes each URL to a terminal callback (no
dont_filter -> dedup + checkpoint resume). follow=True routes the response
through the rule engine (`_parse`, not the public `parse` which raises) so its
links are followed; POST uses FormRequest with dont_filter (the body isn't in
the URL fingerprint). For enumerable archives / paginated search backends with
no followable links.
"""

import pytest
from pydantic import ValidationError

from spiders.database_spider import _expand_var, _generated_urls, _generated_requests
from core.schemas import GeneratedUrlSchema, GeneratedVarSchema

pytestmark = pytest.mark.unit


# --- variable expansion ---------------------------------------------------


def test_expand_range():
    assert _expand_var({"type": "range", "from": 1, "to": 5}) == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


def test_expand_range_step():
    assert _expand_var({"type": "range", "from": 0, "to": 10, "step": 5}) == [
        "0",
        "5",
        "10",
    ]


def test_expand_list():
    assert _expand_var({"type": "list", "values": ["a", "b"]}) == ["a", "b"]


def test_expand_date():
    out = _expand_var(
        {"type": "date", "from": "2021-01-01", "to": "2021-01-03", "step_days": 1}
    )
    assert out == ["2021-01-01", "2021-01-02", "2021-01-03"]


def test_expand_unknown_type_raises():
    with pytest.raises(ValueError):
        _expand_var({"type": "bogus"})


def test_expand_handles_stored_from_alias():
    # After schema model_dump, `from` is stored under the field name `from_`.
    # _expand_var must read the stored form too, not just the as-authored "from".
    assert _expand_var({"type": "range", "from_": 1, "to": 3}) == ["1", "2", "3"]


def test_roundtrip_through_schema_then_expand():
    from core.schemas import SpiderSettingsSchema

    s = SpiderSettingsSchema(
        GENERATED_URLS=[
            {
                "template": "https://s/{p}",
                "vars": {"p": {"type": "range", "from": 1, "to": 3}},
            }
        ]
    )
    stored = s.model_dump(exclude_none=True, exclude_unset=True)
    cfg = stored["GENERATED_URLS"][0]
    assert list(_generated_urls(cfg)) == ["https://s/1", "https://s/2", "https://s/3"]


# --- url generation (cartesian product) -----------------------------------


def test_generated_urls_cartesian_product():
    cfg = {
        "template": "https://s/{d}/{p}",
        "vars": {
            "d": {"type": "list", "values": ["x", "y"]},
            "p": {"type": "range", "from": 1, "to": 3},
        },
    }
    urls = list(_generated_urls(cfg))
    assert len(urls) == 2 * 3
    assert "https://s/x/1" in urls
    assert "https://s/y/3" in urls


# --- request building -----------------------------------------------------


class _FakeSpider:
    async def parse_page(self, response):
        yield {}

    async def parse_article(self, response):
        yield {}

    def _parse(self, response):  # CrawlSpider's rule engine (follow links)
        pass


def test_generated_requests_default_callback_is_parse_article():
    spider = _FakeSpider()
    cfg = {
        "template": "https://s/{p}",
        "vars": {"p": {"type": "range", "from": 1, "to": 1}},
    }
    reqs = list(_generated_requests(spider, cfg))
    assert reqs[0].callback == spider.parse_article


def test_post_generates_formrequest_with_filled_formdata():
    spider = _FakeSpider()
    cfg = {
        "template": "https://s/buscador",
        "method": "POST",
        "formdata": {"query": "", "pagina": "{p}"},
        "vars": {"p": {"type": "range", "from": 1, "to": 2}},
        "follow": True,
    }
    reqs = list(_generated_requests(spider, cfg))
    assert all(r.method == "POST" for r in reqs)
    assert all(r.url == "https://s/buscador" for r in reqs)  # template not substituted
    assert all(r.dont_filter for r in reqs)  # POST body not in the URL fingerprint
    bodies = [r.body.decode() for r in reqs]
    assert any("pagina=1" in b for b in bodies)
    assert any("pagina=2" in b for b in bodies)


def test_follow_routes_to_rule_engine_parse_not_public_parse():
    spider = _FakeSpider()
    cfg = {
        "template": "https://s/{p}",
        "vars": {"p": {"type": "range", "from": 1, "to": 1}},
        "follow": True,
    }
    reqs = list(_generated_requests(spider, cfg))
    # _parse is the rule engine; public parse raises NotImplementedError on CrawlSpider
    assert reqs[0].callback == spider._parse


def test_get_terminal_keeps_no_dont_filter():
    spider = _FakeSpider()
    cfg = {
        "template": "https://s/{p}",
        "vars": {"p": {"type": "range", "from": 1, "to": 2}},
        "callback": "parse_page",
    }
    reqs = list(_generated_requests(spider, cfg))
    assert [r.url for r in reqs] == ["https://s/1", "https://s/2"]
    assert all(r.callback == spider.parse_page for r in reqs)
    # NOT dont_filter -> dedup within a run + checkpoint can skip completed on resume
    assert all(r.dont_filter is False for r in reqs)


def test_generated_requests_raise_on_missing_callback():
    spider = _FakeSpider()
    cfg = {
        "template": "https://s/{p}",
        "vars": {"p": {"type": "range", "from": 1, "to": 1}},
        "callback": "does_not_exist",
    }
    with pytest.raises(ValueError):
        list(_generated_requests(spider, cfg))


# --- schema validation (at import) ----------------------------------------


def test_schema_callback_optional():
    # callback unset at schema level (runtime defaults a non-follow entry to
    # parse_article); see test_generated_requests_default_callback_is_parse_article
    s = GeneratedUrlSchema(
        template="https://s/{p}", vars={"p": {"type": "range", "from": 1, "to": 2}}
    )
    assert s.callback is None
    assert s.method == "GET" and s.follow is False


def test_schema_post_requires_formdata():
    with pytest.raises(ValidationError):
        GeneratedUrlSchema(
            template="https://s/buscador",
            method="POST",
            vars={},
        )


def test_schema_post_placeholder_in_formdata_validates():
    s = GeneratedUrlSchema(
        template="https://s/buscador",
        method="POST",
        formdata={"query": "", "pagina": "{p}"},
        vars={"p": {"type": "range", "from": 1, "to": 2}},
        follow=True,
    )
    assert s.follow is True


def test_schema_follow_and_callback_mutually_exclusive():
    with pytest.raises(ValidationError):
        GeneratedUrlSchema(
            template="https://s/{p}",
            vars={"p": {"type": "range", "from": 1, "to": 2}},
            follow=True,
            callback="parse_page",
        )


def test_schema_rejects_placeholder_var_mismatch():
    with pytest.raises(ValidationError):
        GeneratedUrlSchema(
            template="https://s/{p}",
            vars={"q": {"type": "range", "from": 1, "to": 2}},
        )


def test_schema_rejects_range_non_int():
    with pytest.raises(ValidationError):
        GeneratedVarSchema(type="range", from_="a", to=5)


def test_schema_rejects_date_non_str():
    with pytest.raises(ValidationError):
        GeneratedVarSchema(type="date", from_=1, to=2)


def test_schema_rejects_empty_list():
    with pytest.raises(ValidationError):
        GeneratedVarSchema(type="list", values=[])


# --- empty start_urls is allowed only when a generator seeds the crawl --------


def _base(**over):
    cfg = {
        "name": "lun_com",
        "source_url": "https://www.lun.com",
        "allowed_domains": ["lun.com"],
        "start_urls": ["https://www.lun.com"],
    }
    cfg.update(over)
    return cfg


def test_config_allows_empty_start_urls_with_generated_urls():
    from core.schemas import SpiderConfigSchema

    SpiderConfigSchema(
        **_base(
            start_urls=[],
            settings={
                "GENERATED_URLS": [
                    {
                        "template": "https://www.lun.com/{p}",
                        "vars": {"p": {"type": "range", "from": 1, "to": 2}},
                    }
                ]
            },
        )
    )


def test_config_rejects_empty_start_urls_without_any_seed():
    from core.schemas import SpiderConfigSchema

    with pytest.raises(ValidationError):
        SpiderConfigSchema(**_base(start_urls=[]))
