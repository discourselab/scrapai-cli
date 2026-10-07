#!/usr/bin/env python3
"""Unit tests for the pure (no-network, no-file) functions of the pipeline.

Run with pytest:   pytest test_desmog.py
or standalone:      python3 test_desmog.py
Both work; the __main__ block is a tiny runner for when pytest is absent.

These guard the regex-heavy extraction logic, which is where the real
complexity (and brittleness) lives.
"""
from desmog import countries, placement
from desmog.geo import nominatim

import geocode_entities as geo
import type_relationships as typ
import wikidata_loose_locations as loose
import affiliation_locations as aff
import address_locations as addr


# ---- desmog.countries -------------------------------------------------------
def test_primary_country():
    assert countries.primary_country("Canada, United States") == "Canada"
    assert countries.primary_country("") == "Unknown"
    assert countries.primary_country(None) == "Unknown"


def test_countries_of_drops_filler():
    assert countries.countries_of({"country": "United Kingdom, International"}) == ["United Kingdom"]
    assert countries.countries_of({"country": "International"}) == []
    assert countries.countries_of({}) == []


def test_in_bbox():
    assert countries.in_bbox((51.5, -0.1), "United Kingdom") is True
    assert countries.in_bbox((51.5, -0.1), "Italy") is False
    assert countries.in_bbox((0, 0), "Narnia") is True  # unknown box -> accept


def test_jitter_is_deterministic_and_bounded():
    assert countries.jitter("acme", 0.35) == countries.jitter("acme", 0.35)
    assert countries.jitter("acme", 0.35) != countries.jitter("other", 0.35)
    dx, dy = countries.jitter("acme", 0.35)
    assert abs(dx) <= 0.35 and abs(dy) <= 0.35


def test_centroid_of_unknown():
    assert countries.centroid_of("Unknown") == countries.UNKNOWN_POINT
    assert countries.centroid_of("United Kingdom") == countries.CENTROID["United Kingdom"]
    assert countries.centroid_of("Narnia") is None
    assert "Unknown" not in countries.CENTROID  # kept out so the dashboard leaves them unplaced


# ---- geocode_entities.extract_place ----------------------------------------
def test_extract_place():
    assert geo.extract_place("The group is headquartered in Westminster, London.") == "Westminster, London"
    assert geo.extract_place("A Washington, D.C.-based think tank that denies climate science.") \
        == "Washington, D.C"   # trailing period stripped by the cleanup
    assert geo.extract_place("No location is stated in this profile at all.") is None
    assert geo.extract_place("") is None


# ---- type_relationships.window / classify ----------------------------------
def test_window_returns_the_anchor_sentence():
    ctx = "First sentence. He is a director of the Heartland Institute. Third sentence."
    assert typ.window(ctx, "Heartland Institute") == "He is a director of the Heartland Institute."


def test_classify():
    assert "Leadership" in typ.classify("he is the director of")
    assert "Funder/donor" in typ.classify("the group donated $50,000 to")
    assert typ.classify("merely appears next to") == ["Mention/unclear"]


# ---- wikidata_loose name matching ------------------------------------------
def test_name_variants():
    v = loose.name_variants("The Heartland Institute (formerly Something) Inc.")
    assert "Heartland Institute" in v           # leading "The" + trailing Inc dropped
    assert "Something" in v                      # formerly name
    assert all(len(x) >= 3 for x in v)


def test_similar():
    assert loose.similar("Heartland Institute", "Heartland Institute", exact_only=False)
    assert not loose.similar("Atlantic Bridge", "Atlantic Bridge Education Research Trust", exact_only=False)
    # a leading "The" is a stopword, so it still counts as an exact word-set match
    assert loose.similar("Heartland Institute", "The Heartland Institute", exact_only=True) is True
    # a genuine extra word fails exact mode
    assert loose.similar("Heartland Institute", "Heartland Institute Foundation", exact_only=True) is False
    assert loose.words("the Inc of A") == set()  # all stopwords


# ---- nominatim.same_institution --------------------------------------------
def test_same_institution():
    assert nominatim.same_institution("University of Helsinki", "Helsingin yliopisto")
    assert not nominatim.same_institution("University of Carleton", "Faculty of Dentistry")


# ---- affiliation.extract_institution ---------------------------------------
def test_extract_institution():
    ent = {"name": "Jane Smith",
           "content": "Background Smith is a professor of geology at the University of Oregon. "
                      "She has written many papers."}
    assert aff.extract_institution(ent) == "University of Oregon"
    # sentence not about the subject -> no match
    ent2 = {"name": "Jane Smith",
            "content": "Background The institute was founded by John Doe of Harvard University."}
    assert aff.extract_institution(ent2) is None


# ---- address extraction -----------------------------------------------------
def test_street_and_postcode_regex():
    assert addr.STREET_RE.search("found at 83 Victoria Street, London")
    assert addr.POSTCODE_RE.search("London SW1H 0HW").group(0) == "SW1H 0HW"
    assert addr.POSTCODE_RE.search("Calgary, AB T2H 2P6").group(0) == "T2H 2P6"


def test_from_contact_and_tail():
    text = "Contact & Address 83 Victoria Street, London SW1H 0HW Social Media twitter"
    addr_str, pc = addr.from_contact(text)
    assert addr_str.startswith("83 Victoria Street") and pc == "SW1H 0HW"


def test_subject_names():
    names = addr.subject_names({"name": "Global Warming Policy Foundation (GWPF)"})
    assert "gwpf" in names and "the group" in names


# ---- relationship-type taxonomy --------------------------------------------
def test_reltypes_mapping_complete():
    from desmog import reltypes
    # every type the classifier can emit is grouped
    for t, _ in typ.RULES:
        assert t in reltypes.GROUPS, f"fine type not grouped: {t}"
    # every group is in the canonical order and every mapped group exists
    assert set(reltypes.GROUPS.values()) == set(reltypes.RGROUPS)
    assert len(reltypes.RGROUPS) == len(set(reltypes.RGROUPS))
    assert reltypes.group_of("Nonsense type") == "Unclear"
    assert reltypes.group_of("Leadership") == "Affiliation"


# ---- placement merge priority ----------------------------------------------
def test_placement_merge_priority(tmp_path):
    import json
    (tmp_path / "locations.jsonl").write_text(
        json.dumps({"slug": "x", "lat": 1.0, "lng": 1.0, "source": "country"}) + "\n")
    (tmp_path / "address_overrides.jsonl").write_text(
        json.dumps({"slug": "x", "lat": 9.0, "lng": 9.0, "source": "address"}) + "\n")
    merged = placement.load_merged(d=tmp_path)
    assert merged["x"] == (9.0, 9.0, "address")          # later file wins
    merged2 = placement.load_merged(d=tmp_path, exclude=("address_overrides.jsonl",))
    assert merged2["x"] == (1.0, 1.0, "country")          # own-file exclusion
    assert placement.exact(merged) == {"x": (9.0, 9.0)}   # address is exact
    assert placement.exact(merged2) == {}                 # country is not exact


# ---- standalone runner (when pytest is not installed) ----------------------
if __name__ == "__main__":
    import tempfile
    import traceback
    from pathlib import Path

    fns = {k: v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)}
    passed = failed = 0
    for name, fn in fns.items():
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception:
            print(f"  FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
