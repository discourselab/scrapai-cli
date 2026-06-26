"""The `sections` authoring format is desugared into the existing
rules + callbacks + settings shape at import time (core.sections.expand_sections),
so the runtime spiders consume it unchanged.

A `section` is {match, extract?, follow?, ...}:
  - extract absent            -> follow-only rule (callback=None)
  - extract == "auto"         -> the built-in article path (callback=parse_article)
  - extract == {field: ...}   -> per-field selectors; each field is "auto"
                                 (core fields only) or a {css/xpath/...} directive
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.sections import expand_sections
from core.schemas import SpiderConfigSchema
from core.schema_validator import check_sections_coverage
from core.models import Spider, SpiderRule
from spiders.sitemap_spider import SitemapDatabaseSpider

pytestmark = pytest.mark.unit


def _rule_mock(d):
    r = Mock(spec=SpiderRule)
    r.allow_patterns = d.get("allow")
    r.deny_patterns = d.get("deny")
    r.restrict_xpaths = d.get("restrict_xpaths")
    r.restrict_css = d.get("restrict_css")
    r.tags = d.get("tags")
    r.callback = d.get("callback")
    r.follow = d.get("follow", True)
    r.priority = d.get("priority", 0)
    return r


def _build_sitemap_spider(expanded):
    rec = Mock(spec=Spider)
    rec.name = expanded["name"]
    rec.active = True
    rec.allowed_domains = expanded["allowed_domains"]
    rec.start_urls = expanded["start_urls"]
    rec.rules = [_rule_mock(r) for r in expanded["rules"]]
    rec.callbacks_config = expanded.get("callbacks") or {}
    rec.settings = []
    rec.id = 1
    with patch("spiders.sitemap_spider.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = rec
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        with patch.object(
            SitemapDatabaseSpider, "_load_settings_from_db"
        ), patch.object(SitemapDatabaseSpider, "_setup_cloudflare_handlers"):
            return SitemapDatabaseSpider(spider_name=rec.name)


def _write_schema(tmp_path, fields):
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "project.json").write_text(json.dumps({"schema": {"fields": fields}}))
    return str(tmp_path)


def test_no_sections_key_is_passthrough():
    cfg = {"name": "x_com", "rules": [{"allow": ["/a"]}]}
    assert expand_sections(cfg) == cfg


def test_sections_key_is_removed_after_expansion():
    cfg = {"name": "x_com", "sections": [{"match": ["/.*"], "follow": True}]}
    out = expand_sections(cfg)
    assert "sections" not in out


def test_follow_only_section_becomes_callbackless_rule():
    cfg = {"name": "x_com", "sections": [{"match": ["/.*"], "follow": True}]}
    out = expand_sections(cfg)
    assert out["rules"] == [{"allow": ["/.*"], "follow": True, "callback": None}]


def test_auto_section_routes_to_parse_article():
    cfg = {"name": "x_com", "sections": [{"match": ["/blog/.*"], "extract": "auto"}]}
    out = expand_sections(cfg)
    assert out["rules"] == [
        {"allow": ["/blog/.*"], "follow": True, "callback": "parse_article"}
    ]


def test_selector_section_becomes_named_callback():
    cfg = {
        "name": "x_com",
        "sections": [
            {
                "match": ["/product/.*"],
                "extract": {
                    "name": {"css": "h1::text"},
                    "price": {"css": ".price::text"},
                },
            }
        ],
    }
    out = expand_sections(cfg)
    assert out["rules"][0]["callback"] == "parse_section_1"
    assert out["callbacks"]["parse_section_1"] == {
        "extract": {"name": {"css": "h1::text"}, "price": {"css": ".price::text"}}
    }


def test_mixed_auto_and_override_emits_global_fields():
    cfg = {
        "name": "x_com",
        "sections": [
            {
                "match": ["/blog/.*"],
                "extract": {
                    "title": "auto",
                    "content": "auto",
                    "author": {"css": ".byline a::text"},
                    "published_date": "auto",
                },
            }
        ],
    }
    out = expand_sections(cfg)
    # The article extractor still runs (callback=parse_article); only the
    # overridden field becomes a global FIELDS directive.
    assert out["rules"][0]["callback"] == "parse_article"
    assert out["settings"]["FIELDS"] == {"author": {"css": ".byline a::text"}}


def test_auto_on_non_core_field_is_rejected():
    cfg = {
        "name": "x_com",
        "sections": [{"match": ["/p/.*"], "extract": {"price": "auto"}}],
    }
    with pytest.raises(ValueError):
        expand_sections(cfg)


def test_two_override_sections_are_rejected():
    # Only one section may mix "auto" with overrides, because the override
    # path (global FIELDS + the single article extractor) is spider-wide.
    cfg = {
        "name": "x_com",
        "sections": [
            {"match": ["/a/.*"], "extract": {"title": "auto", "author": {"css": ".x"}}},
            {"match": ["/b/.*"], "extract": {"title": "auto", "author": {"css": ".y"}}},
        ],
    }
    with pytest.raises(ValueError):
        expand_sections(cfg)


def test_unknown_section_key_is_rejected():
    cfg = {"name": "x_com", "sections": [{"match": ["/a"], "xtract": "auto"}]}
    with pytest.raises(ValueError):
        expand_sections(cfg)


def test_non_object_section_is_rejected():
    cfg = {"name": "x_com", "sections": ["/a/.*"]}
    with pytest.raises(ValueError):
        expand_sections(cfg)


def test_expanded_config_validates_against_spider_config_schema():
    # The whole point of the additive design: the expanded config is the
    # existing shape, so it passes the strict SpiderConfigSchema unchanged.
    cfg = {
        "name": "x_com",
        "source_url": "https://example.com",
        "allowed_domains": ["example.com"],
        "start_urls": ["https://example.com"],
        "sections": [
            {
                "match": ["/blog/.*"],
                "extract": {"title": "auto", "author": {"css": ".by::text"}},
            },
            {
                "match": ["/product/.*"],
                "extract": {
                    "name": {"css": "h1::text"},
                    "price": {"css": ".price::text"},
                },
            },
            {"match": ["/.*"], "follow": True},
        ],
    }
    out = expand_sections(cfg)
    validated = SpiderConfigSchema(**out)  # must not raise

    assert validated.rules[0].callback == "parse_article"
    assert validated.callbacks is not None
    assert "parse_section_2" in validated.callbacks
    assert validated.settings.FIELDS is not None
    assert "author" in validated.settings.FIELDS


def test_existing_settings_are_preserved_and_merged():
    cfg = {
        "name": "x_com",
        "settings": {"DOWNLOAD_DELAY": 0, "CONCURRENT_REQUESTS": 32},
        "sections": [
            {
                "match": ["/blog/.*"],
                "extract": {"title": "auto", "author": {"css": ".by::text"}},
            }
        ],
    }
    out = expand_sections(cfg)
    assert out["settings"]["DOWNLOAD_DELAY"] == 0
    assert out["settings"]["CONCURRENT_REQUESTS"] == 32
    assert out["settings"]["FIELDS"] == {"author": {"css": ".by::text"}}


# --- slice 3: sections-aware schema coverage ----------------------------------


def test_coverage_skips_when_no_project_schema(tmp_path):
    sections = [{"match": ["/a"], "extract": "auto"}]
    assert check_sections_coverage("missing", sections, str(tmp_path)) == []


def test_auto_section_covers_required_core_fields(tmp_path):
    dd = _write_schema(
        tmp_path,
        [{"name": "title", "required": True}, {"name": "content", "required": True}],
    )
    sections = [{"match": ["/a"], "extract": "auto"}]
    assert check_sections_coverage("myproj", sections, dd) == []


def test_required_field_with_no_section_source_is_flagged(tmp_path):
    dd = _write_schema(tmp_path, [{"name": "price", "required": True}])
    sections = [{"match": ["/a"], "extract": {"name": {"css": "h1::text"}}}]
    problems = check_sections_coverage("myproj", sections, dd)
    assert any("price" in p for p in problems)


def test_required_field_covered_by_selector_passes(tmp_path):
    dd = _write_schema(tmp_path, [{"name": "price", "required": True}])
    sections = [{"match": ["/a"], "extract": {"price": {"css": ".price::text"}}}]
    assert check_sections_coverage("myproj", sections, dd) == []


def test_url_is_always_considered_covered(tmp_path):
    dd = _write_schema(tmp_path, [{"name": "url", "required": True}])
    sections = [{"match": ["/a"], "extract": "auto"}]
    assert check_sections_coverage("myproj", sections, dd) == []


# --- fix 2: sections + sitemap work together (no more forced trade) -----------


def test_sections_config_preserves_use_sitemap_setting():
    cfg = {
        "name": "x_com",
        "settings": {"USE_SITEMAP": True},
        "sections": [{"match": ["/blog/.*"], "extract": "auto"}],
    }
    out = expand_sections(cfg)
    assert out["settings"]["USE_SITEMAP"] is True


def test_sections_config_drives_the_sitemap_spider():
    # A sections config with USE_SITEMAP: the sitemap spider consumes the
    # desugared rules+callbacks directly — generic reader + custom fields +
    # sitemap enumeration all at once (the trade the agent thought it had to make).
    cfg = {
        "name": "x_com",
        "source_url": "https://example.com",
        "allowed_domains": ["example.com"],
        "start_urls": ["https://example.com/sitemap.xml"],
        "settings": {"USE_SITEMAP": True},
        "sections": [
            {
                "match": ["/blog/.*"],
                "extract": {"title": "auto", "author": {"css": ".by::text"}},
            },
            {"match": ["/product/.*"], "extract": {"name": {"css": "h1::text"}}},
        ],
    }
    out = expand_sections(cfg)
    SpiderConfigSchema(**out)  # the combined config is valid

    spider = _build_sitemap_spider(out)
    routes = dict(spider.sitemap_rules)
    # blog (auto + author override) routes to the generic article reader (which
    # applies the FIELDS overlay); product (selectors) to its generated callback.
    assert routes["/blog/.*"] == "parse_article"
    assert routes["/product/.*"] == "parse_section_2"
    assert hasattr(spider, "parse_section_2")  # callback registered on the spider
