#!/usr/bin/env python3
"""
Option B-lite: pinpoint organisation locations via Wikidata (free, no key).

For every organisation still placed at a country centroid (source == "country"
in locations.jsonl), look it up on Wikidata and read its headquarters
coordinates:
  1. wbsearchentities  name -> candidate Q-id
  2. wbgetentities     Q    -> P625 (coords on the org) OR P159 (HQ item)
  3. if P159           Qhq  -> P625 coords
  4. validate the coordinate falls inside the expected country's bounding box
  5. write hits to location_overrides.jsonl  (merged on top of locations.jsonl
     by build_dashboard.py; delete the file to fully revert)

Results are cached to wikidata_cache.json so reruns are instant.

Usage:
  python3 wikidata_locations.py            # all country-level orgs
  python3 wikidata_locations.py --limit 20 # sample
  python3 wikidata_locations.py --all-orgs # also re-check orgs we geocoded
"""
import argparse, json, re

from desmog.countries import in_bbox, primary_country
from desmog.data import D, degree_map, load_entities, load_jsonl, load_relationships
from desmog.geo import wikidata as wd

ENTS = D / "entities.jsonl"
RELS = D / "relationships.jsonl"
LOCS = D / "locations.jsonl"
CACHE = D / "wikidata_cache.json"
OUT = D / "location_overrides.jsonl"


def clean_name(name):
    n = re.sub(r"\(formerly[^)]*\)", "", name)
    n = re.sub(r"\([^)]*\)", "", n)          # drop "(CFACT)", "(deceased)"
    return re.sub(r"\s+", " ", n).strip()


def looks_like_org(desc):
    d = (desc or "").lower()
    return any(w in d for w in ("organization", "organisation", "institute", "foundation",
               "think tank", "group", "association", "lobby", "nonprofit", "non-profit",
               "company", "party", "coalition", "network", "society", "council",
               "centre", "center", "charity", "advocacy", "campaign"))


def get_claims(qid, url_cache=None):
    return wd.get_entities([qid], url_cache, props="claims|labels|descriptions").get(qid, {})


def resolve(name, country, cache, url_cache=None):
    key = f"{name}|{country}"
    if key in cache:
        return cache[key]
    # transient HTTP errors propagate to the caller (NOT cached, so they retry);
    # only a completed search with no usable hit is cached as a genuine negative.
    result = None
    cands = wd.search_entity(name, url_cache)
    cands.sort(key=lambda c: 0 if looks_like_org(c.get("description")) else 1)
    for c in cands[:3]:
        qid = c["id"]
        cl = get_claims(qid, url_cache)
        claims = cl.get("claims", {})
        coord = wd.coord(claims)
        label = cl.get("labels", {}).get("en", {}).get("value", name)
        if not coord:
            hq = wd.hq_item(claims)
            if hq:
                hqent = get_claims(hq, url_cache)
                coord = wd.coord(hqent.get("claims", {}))
                hlab = hqent.get("labels", {}).get("en", {}).get("value")
                if hlab:
                    label = f"{label} HQ: {hlab}"
        if coord and in_bbox(coord, country):
            result = {"qid": qid, "lat": coord[0], "lng": coord[1], "place": label}
            break
    cache[key] = result
    CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all-orgs", action="store_true",
                    help="also re-check orgs we already geocoded from text")
    args = ap.parse_args()

    ents = load_entities()
    loc = {r["slug"]: r for r in load_jsonl(LOCS)} if LOCS.exists() else {}
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    deg = degree_map(load_relationships())

    targets = [e for e in ents.values() if e.get("type") == "organization"
               and (args.all_orgs or loc.get(e["slug"], {}).get("source") == "country")]
    targets.sort(key=lambda e: deg[e["slug"]], reverse=True)  # high-degree first
    if args.limit:
        targets = targets[:args.limit]

    print(f"resolving {len(targets)} organisations via Wikidata...\n")
    overrides, done, hits = [], 0, 0
    for e in targets:
        country = primary_country(e.get("country"))
        try:
            res = resolve(clean_name(e["name"]), country, cache)
        except Exception as ex:
            print(f"  ! skipped {e['name']!r} (transient: {ex}) - will retry next run")
            continue
        done += 1
        if res:
            hits += 1
            overrides.append({"slug": e["slug"], "lat": res["lat"], "lng": res["lng"],
                              "source": "wikidata", "place": res["place"]})
            print(f"[{hits:3}] {e['name'][:42]:42} -> {res['place'][:45]} ({res['lat']:.2f},{res['lng']:.2f})")
        if done % 25 == 0:
            print(f"   ...{done}/{len(targets)} processed, {hits} hits")

    with open(OUT, "w") as f:
        for o in overrides:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    print(f"\nwrote {OUT}")
    print(f"resolved {hits}/{len(targets)} organisations ({hits*100//max(1,len(targets))}%)")


if __name__ == "__main__":
    main()
