"""Fusion (Arc XP) extractor: body lives in JSON, not the DOM."""

import json

from core.extractors import (
    FusionExtractor,
    _json_object_at,
    fusion_body_text,
    fusion_global_content,
)


def _page(payload):
    """A page shaped like Arc XP: body only in the script, not the DOM."""
    return (
        "<html><body><h1>Headline in DOM</h1>"
        "<nav>Home Sports Politics</nav>"
        "<script>window.Fusion=window.Fusion||{};"
        f"Fusion.globalContent={json.dumps(payload)};</script>"
        "</body></html>"
    )


# Invented sample content. The accent and the HTML entities are deliberate:
# they exercise entity decoding and non-ASCII handling.
PAYLOAD = {
    "headlines": {"basic": "Sample Article Headline"},
    "description": {"basic": "Sample description"},
    "content_elements": [
        {
            "type": "text",
            "content": "<p>First <a href='/x'>paragraph</a> of the body.</p>",
        },
        {"type": "image", "content": "ignored"},
        {"type": "text", "content": "<p>Second paragraph &amp; caf&eacute;.</p>"},
        {"type": "text", "content": ""},
    ],
}


def test_brace_scanner_ignores_braces_inside_strings():
    # A non-greedy regex on '};' would truncate here; the scanner must not.
    text = 'x = {"a": "not }; the end", "b": {"c": 1}};'
    raw = _json_object_at(text, text.index("{"))
    assert json.loads(raw) == {"a": "not }; the end", "b": {"c": 1}}


def test_unbalanced_object_returns_none():
    assert _json_object_at('{"a": 1', 0) is None
    assert _json_object_at("no object here", 0) is None


def test_global_content_parsed_from_page():
    data = fusion_global_content(_page(PAYLOAD))
    assert data["headlines"]["basic"] == "Sample Article Headline"


def test_body_text_joins_text_blocks_only():
    body = fusion_body_text(PAYLOAD)
    # Tags stripped, entities decoded, non-text and empty blocks skipped.
    assert body == "First paragraph of the body.\n\nSecond paragraph & café."
    assert "ignored" not in body
    assert "<p>" not in body


def test_extractor_returns_article_with_json_body():
    art = FusionExtractor().extract("https://example.com/a", _page(PAYLOAD))
    assert art is not None
    assert art.source == "fusion"
    assert art.title == "Sample Article Headline"
    assert "First paragraph" in art.content
    # The DOM nav must never leak in as content.
    assert "Sports" not in art.content


def test_returns_none_without_fusion_payload():
    assert fusion_global_content("<html><body><p>plain</p></body></html>") is None
    assert (
        FusionExtractor().extract("u", "<html><body><p>plain</p></body></html>") is None
    )


def test_returns_none_when_payload_has_no_text_blocks():
    payload = {"headlines": {"basic": "T"}, "content_elements": [{"type": "image"}]}
    assert FusionExtractor().extract("u", _page(payload)) is None


def test_stub_payload_does_not_mask_the_real_one():
    """A page may assign Fusion.globalContent twice.

    Some deployments emit `Fusion.globalContent={}` as a stub. Returning that
    first empty object would hide a real payload assigned later on the page.
    """
    html = "Fusion.globalContent={};" + f"Fusion.globalContent={json.dumps(PAYLOAD)};"
    data = fusion_global_content(html)
    assert data and data.get("content_elements")
    assert "First paragraph" in fusion_body_text(data)


def test_global_content_config_is_not_mistaken_for_the_payload():
    """Fusion.globalContentConfig shares a prefix with the real marker."""
    html = (
        'Fusion.globalContentConfig={"source":"x"};'
        f"Fusion.globalContent={json.dumps(PAYLOAD)};"
    )
    assert fusion_global_content(html).get("content_elements")
    # Config alone must never be served up as the article payload.
    assert fusion_global_content('Fusion.globalContentConfig={"source":"x"};') is None


def test_section_page_yields_no_article_but_keeps_metadata():
    """Section fronts (node_type=section) carry no body: decline, don't guess."""
    html = f'Fusion.globalContent={json.dumps({"node_type": "section"})};'
    assert fusion_global_content(html).get("node_type") == "section"
    assert FusionExtractor().extract("u", html) is None


def test_fusion_counts_as_a_generic_extractor_for_schema_coverage(tmp_path):
    """A fusion-only spider must pass schema validation on import.

    fusion fills the core fields by itself, so it belongs in
    GENERIC_EXTRACTORS. While it was missing from that set, `spiders import`
    rejected every fusion spider with a misleading "add a generic extractor"
    error for each core field.
    """
    from core.schema_validator import check_schema_coverage

    project = tmp_path / "proj"
    project.mkdir()
    core_fields = ["title", "content", "author", "published_date", "url"]
    (project / "project.json").write_text(
        json.dumps(
            {
                "schema": {
                    "fields": [
                        {"name": n, "required": True, "core": True} for n in core_fields
                    ]
                }
            }
        )
    )

    problems = check_schema_coverage(
        "proj", {"EXTRACTOR_ORDER": ["fusion"]}, data_dir=str(tmp_path)
    )
    assert problems == [], problems


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
