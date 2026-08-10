"""Regression pins for the legal-text / licence signal batteries in compliance_capture.
The restructure moves these regexes VERBATIM; these tests lock their behaviour first.
(ai_training_prohibition already has pins in test_audit.py — kept there.)
"""

import pytest

from core.quality.compliance_capture import (
    bespoke_permission,
    classify_llms,
    copyright_statement,
    refine_license,
    scrape_prohibition,
)

pytestmark = pytest.mark.unit


def test_scrape_prohibition_positive():
    assert scrape_prohibition(
        "You may not scrape, crawl, or harvest content from this website."
    )
    assert scrape_prohibition(
        "The use of automated systems such as robots or spiders to access "
        "the site is prohibited."
    )


def test_scrape_prohibition_gdpr_negative():
    # GDPR boilerplate about 'automated processing' of PERSONAL DATA is not an
    # anti-scraping clause
    assert not scrape_prohibition(
        "You have the right not to be subject to a decision based solely on "
        "automated processing of your personal data."
    )


def test_scrape_prohibition_plain_text_negative():
    assert not scrape_prohibition(
        "Our researchers crawl through decades of climate data to build models."
    )


def test_bespoke_permission():
    assert bespoke_permission(
        "You may reproduce this material free of charge in any format for "
        "non-commercial purposes."
    )
    assert not bespoke_permission("All rights reserved.")


def test_classify_llms():
    assert classify_llms("LLMs are welcome to use this documentation.\n")[0] == "allows"
    verdict, quote = classify_llms("Do not train on this content.\n")
    assert verdict == "prohibits" and quote
    # a `## Disallow` section with listed paths is a partial prohibition
    assert classify_llms("## Disallow\n- /private/\n")[0] == "partial"
    assert classify_llms("# docs\n- /reports: summaries\n")[0] == "present-unclear"
    assert classify_llms("")[0] == "not-found"


def test_refine_license_upgrades_bare_cc():
    lic = {
        "license": "Creative Commons",
        "license_quote": "licensed under CC BY-NC-SA 2.0",
    }
    refine_license(lic)
    assert lic["license"].startswith("CC ")
    assert "NC" in lic["license"] and "SA" in lic["license"]


def test_refine_license_subset_drops_confidence():
    lic = {
        "license": "CC BY 4.0",
        "license_quote": "Our geospatial data is available under CC BY 4.0.",
    }
    refine_license(lic)
    assert lic["license_confidence"] == "low"


def test_copyright_statement():
    full, years, holder = copyright_statement(
        "© 2024 Rocky Mountain Institute. All rights reserved."
    )
    assert full and "2024" in full
    assert years == "2024"
    assert holder and "Rocky Mountain" in holder
    assert copyright_statement("no notice here") == (None, None, None)
    # a lone "(c)" enumeration marker with no year is NOT a copyright symbol
    assert copyright_statement("(c) personal data from a known child") == (
        None,
        None,
        None,
    )
