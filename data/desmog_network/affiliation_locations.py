#!/usr/bin/env python3
"""
Place academics by their university (Option D).

Targets only individuals the dashboard would otherwise pin at a country
centroid: not exactly placed by any OTHER pass (text-geocode, Wikidata
strict/loose, addresses) AND no organisation neighbour with an exact pin to
inherit from - i.e. the same set build_dashboard.py leaves at the centroid.
(Target selection previously ignored the loose Wikidata and address
placements when checking neighbours; it now uses the canonical merge - see
REFACTOR_STATUS.md.)

For each, look ONLY at the opening of the profile's "Background" sentence
(which describes the subject; later text mostly describes other people) and,
if it names the subject, pull "<role> at/of <University|College>". Resolve the
institution via OSM Nominatim by name alone (shared geo_cache.json, keys
"inst:<name>"), accepting only results OSM types as a university/college.

Output: climate-disinformation-database/affiliation_overrides.jsonl
        {slug, lat, lng, source: "affiliation", place}
        merged by build_dashboard.py; delete the file to fully revert.

Usage:
  python3 affiliation_locations.py            # all targets (uses cache)
  python3 affiliation_locations.py --dry-run  # show matches, no geocoding
"""
import argparse, json, re

from desmog import placement
from desmog.countries import jitter, primary_country
from desmog.data import D, load_entities, load_relationships, neighbour_map
from desmog.geo.nominatim import GENERIC, geocode, geocode_institution, load_cache

OUT = D / "affiliation_overrides.jsonl"

WINDOW = 250  # chars after "Background" - the subject's own opening sentence(s)
INST = (r"((?:[A-Z][\w&.'-]*\s+){0,5}(?:University|College|Polytechnic)"
        r"(?: of(?: [A-Z][\w'-]*){1,3})?"
        r"|University of(?: [A-Z][\w'-]*){1,4})")
# "at|of" only - "from" is nearly always a degree ("Ph.D. from the University of X")
INST_RE = re.compile(r"\b(?:at|of) (?:the )?" + INST)
NOT_ACADEMIC = re.compile(r"Physicians|Surgeons|Society|Association")
# profile wording -> the institution's real name (when the wording geocodes elsewhere)
ALIASES = {"University of Carleton": "Carleton University"}  # else Dalhousie's Carleton Campus, Halifax

# trailing words the Title-Case run can swallow ("University of Virginia. He")
TAIL = re.compile(r"\s+(?:He|She|They|In|According|Department|School|The)\b.*$")


def extract_institution(ent):
    c = re.sub(r"\s+", " ", ent.get("content") or "")
    b = re.search(r"\bBackground (.{0,%d})" % WINDOW, c)
    if not b:
        return None
    sent = b.group(1)
    surname = ent["name"].split()[-1].lower()
    if surname not in sent[:120].lower():   # sentence must be about the subject
        return None
    m = INST_RE.search(sent)
    if not m or m.end() >= len(sent) - 1:   # cut off by the window -> unreliable
        return None
    inst = TAIL.sub("", m.group(1)).strip(" .,")
    inst = re.sub(r"^The\s+", "", inst)
    inst = ALIASES.get(inst, inst)
    if NOT_ACADEMIC.search(inst) or not set(inst.split()) - GENERIC:
        return None
    return inst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print matches, don't geocode")
    args = ap.parse_args()

    ents = load_entities()
    neighbours = neighbour_map(load_relationships())

    # Current state of every OTHER pass (own output excluded, so a rerun
    # re-targets what this pass placed before).
    merged = placement.load_merged(exclude=("affiliation_overrides.jsonl",))
    exact = placement.exact(merged)

    targets = [e for s, e in ents.items()
               if e.get("type") == "individual"
               and merged.get(s, (None, None, None))[2] == "country"
               and not any(ents.get(n, {}).get("type") == "organization" and n in exact
                           for n in neighbours[s])]

    cache = load_cache()
    out, matched = [], 0
    for e in targets:
        inst = extract_institution(e)
        if not inst:
            continue
        matched += 1
        if args.dry_run:
            print(f"{e['slug']:30} {inst}")
            continue
        hit = geocode_institution(inst, cache)
        if not hit:
            # fallback: plain name+country lookup, validated to the profile's country
            country = primary_country(e.get("country"))
            ll = geocode(f"{inst}, {country}", cache, country)
            hit = (ll[0], ll[1], f"{country} match") if ll else None
        print(f"{e['name'][:32]:32} -> {inst!r} -> {hit}")
        if hit:
            dx, dy = jitter(e["slug"], 0.05)
            out.append({"slug": e["slug"], "lat": hit[0] + dy, "lng": hit[1] + dx,
                        "source": "affiliation", "place": f"{inst} ({hit[2]})"})

    print(f"\ntargets {len(targets)}, institution found {matched}, placed {len(out)}")
    if not args.dry_run:
        with open(OUT, "w") as f:
            for o in out:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
