"""
Tests for renaming FIELD_EXTRACT -> FIELDS with a back-compat alias.

Canonical key is FIELDS; FIELD_EXTRACT is still accepted (legacy). When both are
present, FIELDS wins. Covers the three functional surfaces: settings schema,
runtime resolver, and import-time schema coverage validation.
"""

import json
import pytest

from core.schemas import SpiderSettingsSchema
from core.schema_validator import check_schema_coverage
from spiders.base import BaseDBSpiderMixin

pytestmark = pytest.mark.unit


def _spider(settings):
    s = BaseDBSpiderMixin()
    s.custom_settings = settings
    return s


class TestSettingsSchema:
    def test_accepts_fields(self):
        cfg = SpiderSettingsSchema(FIELDS={"title": {"css": "h1", "to_text": True}})
        assert cfg.FIELDS["title"].css == "h1"

    def test_still_accepts_legacy_field_extract(self):
        cfg = SpiderSettingsSchema(FIELD_EXTRACT={"title": {"css": "h1"}})
        assert cfg.FIELD_EXTRACT["title"].css == "h1"


class TestRuntimeResolver:
    def test_reads_fields(self):
        s = _spider({"FIELDS": {"title": {"css": "h1"}}})
        assert s._resolve_field_extract_config() == {"title": {"css": "h1"}}

    def test_falls_back_to_legacy_field_extract(self):
        s = _spider({"FIELD_EXTRACT": {"title": {"css": "h1"}}})
        assert s._resolve_field_extract_config() == {"title": {"css": "h1"}}

    def test_fields_wins_when_both_present(self):
        s = _spider(
            {
                "FIELDS": {"title": {"css": "new"}},
                "FIELD_EXTRACT": {"title": {"css": "old"}},
            }
        )
        assert s._resolve_field_extract_config()["title"]["css"] == "new"


class TestSchemaCoverage:
    def _write_schema(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.json").write_text(
            json.dumps(
                {
                    "schema": {
                        "fields": [{"name": "byline", "required": True, "core": False}]
                    }
                }
            )
        )

    def test_coverage_via_fields(self, tmp_path):
        self._write_schema(tmp_path)
        problems = check_schema_coverage(
            "proj",
            {"EXTRACTOR_ORDER": ["custom"], "FIELDS": {"byline": {"css": "x"}}},
            data_dir=str(tmp_path),
        )
        assert problems == []

    def test_coverage_via_legacy_field_extract(self, tmp_path):
        self._write_schema(tmp_path)
        problems = check_schema_coverage(
            "proj",
            {"EXTRACTOR_ORDER": ["custom"], "FIELD_EXTRACT": {"byline": {"css": "x"}}},
            data_dir=str(tmp_path),
        )
        assert problems == []

    def test_missing_directive_still_flagged(self, tmp_path):
        self._write_schema(tmp_path)
        problems = check_schema_coverage(
            "proj",
            {"EXTRACTOR_ORDER": ["custom"]},
            data_dir=str(tmp_path),
        )
        assert problems  # non-empty: byline uncovered
