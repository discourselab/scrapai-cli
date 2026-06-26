"""Validate spider configs against project schemas.

A `project.json` schema declares the required output contract. A spider must
either let a generic extractor populate each required core field, or supply
a `FIELDS` directive (legacy `FIELD_EXTRACT` / `CUSTOM_SELECTORS` also accepted)
for each required field. This module is the single source of truth for that check; it
is reused by `spiders import` (pre-commit validation) and `health` (post-hoc
coverage audit).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

CORE_FIELDS = {"title", "content", "author", "published_date", "url"}
GENERIC_EXTRACTORS = {"newspaper", "trafilatura", "playwright"}


def load_project_schema(project: str, data_dir: str) -> Optional[dict]:
    """Load `data_dir/<project>/project.json`. Returns None if missing or invalid."""
    path = Path(data_dir) / project / "project.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


ARTICLE_CORE_FIELDS = {"title", "content", "author", "published_date"}


def check_sections_coverage(
    project: str,
    sections: List[dict],
    data_dir: str = "./data",
) -> List[str]:
    """Coverage check for the `sections` authoring format.

    A required schema field must be provided by at least one section: listed in
    some section's `extract`, or covered by an `extract: "auto"` section (which
    yields the core article fields). `url` is always populated automatically.

    Empty list = full coverage (or no `project.json` to enforce).
    """
    schema = load_project_schema(project, data_dir)
    if not schema:
        return []

    provided = set()
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        extract = section.get("extract")
        if extract == "auto":
            provided |= ARTICLE_CORE_FIELDS
        elif isinstance(extract, dict):
            provided |= set(extract.keys())

    problems: List[str] = []
    for f in schema.get("schema", {}).get("fields", []):
        if not f.get("required"):
            continue
        name = f.get("name")
        if name == "url":
            continue
        if name not in provided:
            problems.append(
                f"required field '{name}' has no source in any section — "
                "add it to a section's extract"
            )
    return problems


def check_schema_coverage(
    project: str,
    settings: Dict,
    callbacks_config: Optional[Dict] = None,
    data_dir: str = "./data",
) -> List[str]:
    """Return human-readable diagnostics for missing required-field coverage.

    Empty list = full coverage (or no schema to validate against).

    Skips when:
    - The project has no `project.json` (nothing to enforce).
    - The spider uses named callbacks (the callback's own `extract` config is
      the contract; schema enforcement is the agent's responsibility there).
    """
    schema = load_project_schema(project, data_dir)
    if not schema:
        return []

    if callbacks_config:
        return []

    fields = schema.get("schema", {}).get("fields", [])
    extractor_order = settings.get("EXTRACTOR_ORDER") or []
    field_extract = settings.get("FIELDS") or settings.get("FIELD_EXTRACT") or {}
    custom_selectors = settings.get("CUSTOM_SELECTORS") or {}

    has_generic = any(e in GENERIC_EXTRACTORS for e in extractor_order)

    problems: List[str] = []
    for f in fields:
        if not f.get("required"):
            continue
        name = f["name"]

        # `url` is always populated automatically from the response.
        if name == "url":
            continue

        covered_by_directive = name in field_extract or name in custom_selectors

        if name in CORE_FIELDS:
            if not has_generic and not covered_by_directive:
                problems.append(
                    f"required field '{name}' (core) has no source — "
                    "add a generic extractor to EXTRACTOR_ORDER "
                    "(newspaper/trafilatura) or a FIELDS directive"
                )
        else:
            if not covered_by_directive:
                problems.append(
                    f"required field '{name}' (non-core) has no FIELDS " "directive"
                )

    # If the schema declares any non-core field (required or optional), the
    # spider must run in pure-CSS mode (`EXTRACTOR_ORDER: ["custom"]`). Generic
    # extractors only know about core fields — mixing them with a schema that
    # asks for anything beyond core means using two extraction mechanisms in
    # the same spider, which is incoherent. Once the user has declared they
    # want more than the canonical article shape, the framework commits to
    # custom extraction for everything.
    non_core_fields = [
        f["name"] for f in fields if not f.get("core") and f["name"] not in CORE_FIELDS
    ]
    if non_core_fields and has_generic:
        problems.append(
            f"schema declares non-core fields ({', '.join(non_core_fields)}) "
            f"— generic extractors (newspaper/trafilatura) in EXTRACTOR_ORDER "
            f'are not allowed alongside them. Use EXTRACTOR_ORDER: ["custom"] '
            f"(pure-CSS mode) with FIELDS directives for every schema "
            f"field."
        )

    return problems
