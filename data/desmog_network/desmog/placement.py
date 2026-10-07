"""Canonical entity-placement merge for the dashboard and every location pass.

The merge order (a LATER FILE ALWAYS WINS) is defined once, here:

    locations.jsonl                 text-geocode + inheritance + centroid
    affiliation_overrides.jsonl     university affiliation
    wikidata_loose_overrides.jsonl  loose Wikidata pass
    location_overrides.jsonl        strict Wikidata pass
    address_overrides.jsonl         profile/manual addresses (incl. manual)

Every pass asks this module what is already placed, so the passes can no
longer drift from the merge order (the address pass used to ignore
affiliation placements, the affiliation pass ignored the loose Wikidata
pass, and so on).
"""
from .countries import jitter
from .data import D, load_jsonl

PLACEMENT_PRIORITY = (
    "locations.jsonl",
    "affiliation_overrides.jsonl",
    "wikidata_loose_overrides.jsonl",
    "location_overrides.jsonl",
    "address_overrides.jsonl",
)

# location sources that count as an exact pin (anything else is approximate)
EXACT_SOURCES = {"geocode", "wikidata", "wikidata-loose", "address", "address-city",
                 "affiliation"}


def load_merged(d=None, exclude=()):
    """slug -> (lat, lng, source); later files in PLACEMENT_PRIORITY win.

    `exclude` = filenames to skip. A pass excludes its own output file so a
    rerun re-targets what it placed before (its previous rows must not
    shrink the target set, or a rerun would empty its output).
    """
    d = d or D
    loc = {}
    for fname in PLACEMENT_PRIORITY:
        if fname in exclude:
            continue
        fp = d / fname
        if not fp.exists():
            continue
        for r in load_jsonl(fp):
            if r.get("lat") is not None:
                loc[r["slug"]] = (r["lat"], r["lng"], r.get("source"))
    return loc


def is_exact(rec):
    return rec is not None and rec[2] in EXACT_SOURCES


def exact(merged):
    """slug -> (lat, lng) for exactly-placed entities only."""
    return {s: (r[0], r[1]) for s, r in merged.items() if is_exact(r)}


def inherit_from_orgs(loc, ents, deg, neighbours, sources=None, jitter_scale=0.7,
                         place_via=None, slugs=None):
    """Individuals without an exact pin inherit the coordinates of their
    most-connected located organisation (with deterministic jitter).

    sources       which location sources count as located (None = any entry
                  already in loc). The dashboard passes EXACT_SOURCES (merge
                  view); the text-geocode pass passes None (its loc dict
                  holds only its own pass-1 geocodes at that point).
    jitter_scale  spread around the parent organisation.
    place_via     optional callable(org_slug, ents) -> label stored as a 4th
                  tuple element (the text-geocode pass stores "via <name>";
                  the dashboard keeps plain 3-tuples).
    slugs         iteration order (default: set(deg), the dashboard's old
                  behaviour; the text-geocode pass passes its entity order
                  so the output file order is unchanged).
    Mutates and returns loc.
    """
    for slug in (slugs if slugs is not None else set(deg)):
        if ents.get(slug, {}).get("type") != "individual":
            continue
        cur = loc.get(slug)
        if cur is not None and (sources is None or cur[2] in sources):
            continue  # already placed well enough
        cand = [(deg[n], n) for n in neighbours.get(slug, ())
                if ents.get(n, {}).get("type") == "organization" and n in loc
                and (sources is None or loc[n][2] in sources)]
        if cand:
            _, best = max(cand)
            blat, blng = loc[best][0], loc[best][1]
            dx, dy = jitter(slug, jitter_scale)
            if place_via is not None:
                loc[slug] = (blat + dy, blng + dx, "inherited", place_via(best, ents))
            else:
                loc[slug] = (blat + dy, blng + dx, "inherited")
    return loc
