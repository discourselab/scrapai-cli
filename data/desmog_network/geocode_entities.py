#!/usr/bin/env python3
"""
Improve node placement for the DeSmog network map (Options A + C).

A) Geocode from the already-scraped profile text: pull a city / place phrase
   out of each entity's `content` ("... located in Westminster, London ...")
   and resolve it to lat/lng via OSM Nominatim (free, no key). Results are
   cached to geo_cache.json so this only hits the network once per place.

C) Richer fallbacks: a broad country-centroid table for every country present,
   and individuals (who rarely state a location) INHERIT the coordinates of
   their most-connected organisation. Anything still unresolved falls back
   to its country centroid with a small deterministic jitter.

Output: climate-disinformation-database/locations.jsonl
        one row per slug -> {slug, lat, lng, source, place}
        source in {geocode, inherited, country, none}

Usage:
  python3 geocode_entities.py            # full run (uses cache)
  python3 geocode_entities.py --limit 20 # sample (geocode at most 20 new places)
"""
import argparse, json, re
from collections import Counter

from desmog import placement
from desmog.countries import centroid_of, jitter, primary_country
from desmog.data import D, degree_map, load_entities, load_relationships, neighbour_map
from desmog.geo.nominatim import geocode, load_cache

OUT = D / "locations.jsonl"

_PLACE = (r"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,2}"
          r"(?:,\s*[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,2})?)")
# "located/based/headquartered/situated in X", "with headquarters in X"
PLACE_RE = re.compile(
    r"(?:located|based|headquartered|situated|offices?\s+in|head\s*office\s+in|with\s+headquarters)\s+in\s+"
    + _PLACE)
# "a Washington, D.C.-based think tank"  /  "the London-based group"
BASED_RE = re.compile(_PLACE + r"-based\b")
# "headquartered in" already caught above; also "headquarters in/at X"
HQ_RE = re.compile(r"headquarters\s+(?:in|at|are\s+in|is\s+in|located\s+in)\s+" + _PLACE)
# things that are not places even if Title-Cased
STOP = {"The", "A", "An", "This", "It", "Its", "He", "She", "They", "In", "For", "And",
        "According", "DeSmog", "Archived", "Accessed", "Where", "While", "Although", "However"}


def extract_place(content):
    """Pull a candidate place phrase from profile text, or None."""
    if not content:
        return None
    content = re.sub(r"\s+", " ", content)  # flatten newlines so "Washington,\nD.C" stays intact
    snippet = content[:1500]
    matches = list(PLACE_RE.finditer(snippet)) + list(HQ_RE.finditer(snippet)) \
        + list(BASED_RE.finditer(snippet))
    for m in matches:
        cand = m.group(1).strip(" .,")
        cand = re.split(r"\.\s", cand)[0].strip(" .,")  # cut at sentence end ("Oregon. Its" -> "Oregon")
        cand = re.sub(r"\s+(is|was|and|the)\b.*$", "", cand, flags=re.I).strip(" .,")
        # drop trailing non-place tokens ("Irvine, California According" -> "Irvine, California")
        parts = []
        for p in cand.split(","):
            toks = [t for t in p.split() if t not in STOP]
            while toks and toks[-1] in STOP:
                toks.pop()
            if toks:
                parts.append(" ".join(toks))
        cand = ", ".join(parts[:2])
        if not cand or cand.split()[0] in STOP:
            continue
        if 2 <= len(cand) <= 60:
            return cand
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max NEW places to geocode this run")
    args = ap.parse_args()

    ents = load_entities()
    rels = load_relationships()
    cache = load_cache()

    # degree / neighbours for "most-connected org" inheritance
    deg = degree_map(rels)
    neighbours = neighbour_map(rels)

    loc = {}        # slug -> (lat, lng, source, place)
    new_geocodes = 0

    # ---- pass 1: geocode anything with an extractable place ----
    for e in ents.values():
        slug = e["slug"]
        country = primary_country(e.get("country"))
        place = extract_place(e.get("content"))
        if not place:
            continue
        # don't append the country if the place already ends with it ("Ottawa, Canada")
        pl = place.strip()
        if country in ("International", "Unknown") or pl.lower().endswith(country.lower()):
            query = pl
        else:
            query = f"{pl}, {country}"
        already = query in cache
        if not already and args.limit and new_geocodes >= args.limit:
            continue
        ll = geocode(query, cache, country)
        if not already:
            new_geocodes += 1
            print(f"[{new_geocodes}] {e['name'][:40]:40} -> {query!r} -> {ll}")
        if ll:
            dx, dy = jitter(slug, 0.08)  # tiny, so co-located orgs don't perfectly stack
            loc[slug] = (ll[0] + dy, ll[1] + dx, "geocode", place)

    # ---- pass 2: individuals inherit most-connected located organisation ----
    placement.inherit_from_orgs(
        loc, ents, deg, neighbours, sources=None, jitter_scale=0.35, slugs=ents,
        place_via=lambda best, ents_: f"via {ents_[best]['name']}")

    # ---- pass 3: country-centroid fallback for everyone else ----
    for e in ents.values():
        slug = e["slug"]
        if slug in loc:
            continue
        country = primary_country(e.get("country"))
        cen = centroid_of(country)
        if cen:
            dx, dy = jitter(slug, 2.2)
            loc[slug] = (cen[0] + dy, cen[1] + dx, "country", country)
        else:
            loc[slug] = (None, None, "none", country)

    with open(OUT, "w") as f:
        for slug, (lat, lng, src, place) in loc.items():
            f.write(json.dumps({"slug": slug, "lat": lat, "lng": lng,
                                "source": src, "place": place}, ensure_ascii=False) + "\n")

    srcs = Counter(v[2] for v in loc.values())
    print(f"\nwrote {OUT}")
    print("placement sources:", dict(srcs))
    print(f"new geocodes this run: {new_geocodes} (cache: {len(cache)} entries)")


if __name__ == "__main__":
    main()
