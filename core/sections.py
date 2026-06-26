"""Desugar the `sections` authoring format into the existing
rules + callbacks + settings shape, at import time.

A `section` is one {match, extract?, follow?, ...} record — the single
repeating concept an author writes. The runtime spiders keep consuming
rules + callbacks + settings unchanged; this translation is the only seam.

    extract absent            -> follow-only rule (callback=None)
    extract == "auto"         -> the built-in article path (callback=parse_article)
    extract == {field: ...}   -> per-field selectors; each field is "auto"
                                 (core fields only) or a {css/xpath/...} directive
"""

from typing import Any, Dict

from core.schemas import SectionSchema

# Fields the built-in article extractor can populate on its own — the only
# fields that may be set to "auto" in a section's extract.
CORE_FIELDS = {"title", "content", "author", "published_date"}

# Per-rule LinkExtractor knobs a section carries straight onto its rule.
_RULE_PASSTHROUGH = ("deny", "restrict_xpaths", "restrict_css", "tags")


def expand_sections(config: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a config's top-level `sections` into rules/callbacks/settings.

    No-op (returns the config unchanged) when `sections` is absent, so legacy
    rules+callbacks+FIELDS configs pass through untouched.
    """
    if "sections" not in config:
        return config

    sections = config["sections"] or []

    out = {k: v for k, v in config.items() if k != "sections"}
    rules = list(out.get("rules") or [])
    callbacks = dict(out.get("callbacks") or {})
    settings = dict(out.get("settings") or {})

    # The "auto + selector override" path writes a single, spider-wide FIELDS
    # dict, so at most one section may own it.
    fields_owner_seen = False

    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError(
                f"Each section must be an object; got {type(section).__name__}"
            )
        SectionSchema(**section)  # shape validation (unknown keys, wrong types)

        rule: Dict[str, Any] = {"allow": section.get("match")}
        rule["follow"] = section.get("follow", True)
        if "priority" in section:
            rule["priority"] = section["priority"]
        for key in _RULE_PASSTHROUGH:
            if key in section:
                rule[key] = section[key]

        extract = section.get("extract")

        if extract is None:
            rule["callback"] = None

        elif extract == "auto":
            rule["callback"] = "parse_article"

        elif isinstance(extract, dict):
            auto_fields = [f for f, v in extract.items() if v == "auto"]
            selector_fields = {f: v for f, v in extract.items() if v != "auto"}

            bad = [f for f in auto_fields if f not in CORE_FIELDS]
            if bad:
                raise ValueError(
                    f"'auto' is only valid for core fields {sorted(CORE_FIELDS)}; "
                    f"got 'auto' on non-core field(s): {bad}. Give them a selector."
                )

            if auto_fields:
                # The article extractor fills the "auto" fields; any selector
                # fields override specific ones via the global FIELDS dict.
                rule["callback"] = "parse_article"
                if selector_fields:
                    if fields_owner_seen:
                        raise ValueError(
                            "Only one section may mix 'auto' with selector "
                            "overrides: that override path (global FIELDS + the "
                            "single article extractor) is spider-wide. Give other "
                            "sections explicit selectors for every field instead."
                        )
                    fields_owner_seen = True
                    fields = dict(settings.get("FIELDS") or {})
                    fields.update(selector_fields)
                    settings["FIELDS"] = fields
            else:
                # All selectors: a self-contained per-section parser.
                name = f"parse_section_{index}"
                callbacks[name] = {"extract": selector_fields}
                rule["callback"] = name
        else:
            raise ValueError(
                "section.extract must be 'auto', a selector dict, or absent; "
                f"got {type(extract).__name__}"
            )

        rules.append(rule)

    out["rules"] = rules
    if callbacks:
        out["callbacks"] = callbacks
    if settings:
        out["settings"] = settings
    return out
