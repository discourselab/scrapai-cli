#!/usr/bin/env python3
"""
Option B-loose: a second, looser Wikidata pass for organisations the strict pass
(wikidata_locations.py) left at a country centroid.

Looser than the strict pass in three ways:
  1. NAME VARIANTS - the full name, the "(formerly X)" name (not acronyms:
     "AEA" matched the United States item),
     the part before a comma / "|" / " & " / " on ", and without a leading
     "The" or a trailing Inc/LLC/Ltd. Slug-only nodes (linked from profiles but
     with no DB profile, e.g. bayer) are searched by their link text.
  2. MORE LOCATION PROPERTIES, in order: P625 coords; P159 HQ (statement-level
     P625 qualifier, then the HQ item's P625, then the HQ item's P131 city);
     P276 location; P131 located-in; P6375 street address (geocoded via OSM).
  3. ANY LISTED COUNTRY - "Canada, United States" accepts a hit inside either.

Guards against the looser search matching the wrong thing:
  - the matched label/alias must share >= 75% of the variant's distinctive
    words (and vice versa for short names), so "Atlantic Bridge" won't take a
    longer unrelated title;
  - candidates that are humans, scholarly articles, creative works, or
    geographic features/structures are skipped;
  - place items that are a whole country are ignored (no better than centroid);
  - nodes with no known country only accept an exact label/alias match whose
    Wikidata description reads as an organisation/company.

Output: climate-disinformation-database/wikidata_loose_overrides.jsonl
        {slug, lat, lng, source: "wikidata-loose", place, qid, via}
        merged by build_dashboard.py; delete the file to fully revert.
Cache:  wikidata_loose_cache.json (search + entity JSON, one entry written
        to disk per API response), so reruns are instant.

Usage:
  python3 wikidata_loose_locations.py            # all targets
  python3 wikidata_loose_locations.py --limit 10 # sample (highest-degree first)
"""
import argparse, json, re, unicodedata

from desmog.countries import countries_of, in_countries, jitter
from desmog.data import D, degree_map, load_entities, load_jsonl, load_relationships
from desmog.geo import wikidata as wd
from desmog.geo.nominatim import geocode, load_cache as load_geo_cache

ENTS = D / "entities.jsonl"
RELS = D / "relationships.jsonl"
LOCS = D / "locations.jsonl"
STRICT = D / "location_overrides.jsonl"
CACHE = D / "wikidata_loose_cache.json"
OUT = D / "wikidata_loose_overrides.jsonl"

# P31 values that are never the organisation itself
BAD_P31 = {"Q5",          # human
           "Q13442814",   # scholarly article
           "Q11424",      # film
           "Q482994",     # album
           "Q7366",       # song
           "Q571",        # book
           "Q12280",      # bridge
           "Q4022",       # river
           "Q486972",     # human settlement
           "Q515",        # city
           "Q41176",      # building
           "Q101352",     # family name
           "Q4167410",    # disambiguation page
           "Q6256",       # country
           "Q3624078",    # sovereign state
           "Q484170",     # commune of France
           "Q3957",       # town
           "Q532",        # village
           "Q9842"}       # primary school
# a place item that is only a country is no better than the centroid
COUNTRY_P31 = {"Q6256", "Q3624078"}
# with no country to check against, the candidate must at least describe itself as an org
ORG_DESC = re.compile(r"compan|corporat|organi[sz]ation|association|council|institute|"
                     r"foundation|agency|group|firm|business|manufactur|producer|"
                     r"multinational|conglomerate|lobby|nonprofit|non-profit|charity", re.I)
BAD_DESC = re.compile(r"scholarly article|^film|album|song|novel|bridge|river|village|"
                     r"family name|surname|disambiguation|species|episode|television", re.I)
STOP = {"the", "of", "for", "and", "a", "an", "in", "on", "to", "inc", "llc", "ltd",
        "limited", "plc", "co", "&"}

# slug-only nodes whose name is too ambiguous to search without a country
# ("jbs" = JBS S.A., but matches the John Birch Society / John Burroughs School)
SKIP = {"jbs"}


class PersistedCache(dict):
    """URL -> response cache, written back to disk after every entry (so an
    interrupted run keeps everything it resolved so far)."""

    def __init__(self, path):
        super().__init__(json.loads(path.read_text()) if path.exists() else {})
        self.path = path

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.path.write_text(json.dumps(self, ensure_ascii=False))


def fold(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def words(t):
    return {w for w in re.findall(r"[a-z0-9]+", fold(t)) if w not in STOP}


def name_variants(name):
    v = [name]
    m = re.search(r"\((?:formerly|previously)\s+([^)]*)\)", name, re.I)
    if m:
        v.append(m.group(1))
    base = re.sub(r"\([^)]*\)", "", name).strip()
    v.append(base)
    for sep in (",", "|", " & ", " on "):
        if sep in base:
            v.append(base.split(sep)[0])
    v += [re.sub(r"^(?:the)\s+", "", x, flags=re.I) for x in list(v)]
    v += [re.sub(r"\s+(?:Inc\.?|LLC|Ltd\.?|Limited|PLC)$", "", x, flags=re.I) for x in list(v)]
    seen, out = set(), []
    for x in v:
        x = re.sub(r"\s+", " ", x).strip(" .,")
        if len(x) >= 3 and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def similar(variant, text, exact_only):
    a, b = words(variant), words(text)
    if not a or not b:
        return False
    if exact_only:
        return a == b
    inter = len(a & b)
    return inter / len(a) >= 0.75 and inter / len(b) >= 0.75


def locate(ent, countries, geo_cache, url_cache):
    """Return (lat, lng, place, via) from the most precise property available."""
    cl = ent.get("claims", {})
    c = wd.coord(cl)
    if c:
        return (*c, wd.label(ent), "P625")
    # P159 HQ: statement-level coordinate qualifier first
    for s in cl.get("P159", []):
        q = s.get("qualifiers", {}).get("P625")
        if q:
            try:
                v = q[0]["datavalue"]["value"]
                return float(v["latitude"]), float(v["longitude"]), "HQ", "P159/P625-qualifier"
            except Exception:
                pass
    # address string -> OSM (most precise when present)
    for s in cl.get("P6375", []):
        try:
            addr = s["mainsnak"]["datavalue"]["value"]["text"]
        except Exception:
            continue
        for country in countries or ["Unknown"]:
            ll = geocode(addr, geo_cache, country)
            if ll:
                return ll[0], ll[1], addr, "P6375-address"
    # HQ / location / located-in items -> their coords, else their P131
    place_items = wd.claim_ids(cl, "P159") + wd.claim_ids(cl, "P276") + wd.claim_ids(cl, "P131")
    if place_items:
        places = wd.get_entities(place_items, url_cache)
        place_items = [pid for pid in place_items
                       if not set(wd.claim_ids(places.get(pid, {}).get("claims", {}), "P31")) & COUNTRY_P31]
        for pid in place_items:
            p = places.get(pid, {})
            c = wd.coord(p.get("claims", {}))
            if c:
                return (*c, wd.label(p, pid), "P159/P276/P131")
        parents = [x for pid in place_items for x in wd.claim_ids(places.get(pid, {}).get("claims", {}), "P131")]
        if parents:
            pp = wd.get_entities(parents, url_cache)
            for pid in parents:
                c = wd.coord(pp.get(pid, {}).get("claims", {}))
                if c:
                    return (*c, wd.label(pp[pid], pid), "HQ-item/P131")
    return None


def resolve(name, countries, geo_cache, url_cache):
    exact_only = not countries
    for var in name_variants(name):
        cands = [c for c in wd.search_entity(var, url_cache, limit=7)
                 if similar(var, c.get("match", {}).get("text") or c.get("label", ""), exact_only)
                 and not BAD_DESC.search(c.get("description") or "")
                 and (not exact_only or ORG_DESC.search(c.get("description") or ""))]
        if not cands:
            continue
        ents = wd.get_entities([c["id"] for c in cands], url_cache)
        for c in cands:
            ent = ents.get(c["id"], {})
            if set(wd.claim_ids(ent.get("claims", {}), "P31")) & BAD_P31:
                continue
            hit = locate(ent, countries, geo_cache, url_cache)
            if hit and in_countries(hit[0], hit[1], countries):
                return {"qid": c["id"], "lat": hit[0], "lng": hit[1], "via": hit[3],
                        "place": f"{wd.label(ent, var)}: {hit[2]}", "variant": var}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    url_cache = PersistedCache(CACHE)
    geo_cache = load_geo_cache()

    ents = load_entities()
    loc = {r["slug"]: r for r in load_jsonl(LOCS)}
    placed = {s for s, r in loc.items() if r.get("source") == "geocode"}
    placed |= {r["slug"] for r in load_jsonl(STRICT)} if STRICT.exists() else set()

    rels = load_relationships()
    deg = degree_map(rels)
    link_name = {}
    for r in rels:
        link_name.setdefault(r["target_slug"], r.get("target_name") or r["target_slug"])

    targets = []
    for slug in deg:
        if slug in placed or slug in SKIP:
            continue
        e = ents.get(slug)
        if e is None:   # slug-only node: search by its link text, country unknown
            name = re.sub(r"^the\s+", "", link_name.get(slug, slug), flags=re.I)
            targets.append((slug, name, []))
        elif e.get("type") == "organization":
            targets.append((slug, e["name"], countries_of(e)))
    targets.sort(key=lambda t: -deg[t[0]])
    if args.limit:
        targets = targets[:args.limit]

    print(f"resolving {len(targets)} organisations via Wikidata (loose)...\n")
    out = []
    for i, (slug, name, countries) in enumerate(targets, 1):
        try:
            res = resolve(name, countries, geo_cache, url_cache)
        except Exception as ex:
            print(f"  ! skipped {name!r} (transient: {ex}) - will retry next run")
            continue
        if res:
            dx, dy = jitter(slug, 0.03)
            out.append({"slug": slug, "lat": res["lat"] + dy, "lng": res["lng"] + dx,
                        "source": "wikidata-loose", "place": res["place"],
                        "qid": res["qid"], "via": res["via"]})
            print(f"[{len(out):3}] {name[:40]:40} ~ {res['variant'][:25]:25} {res['qid']:10} "
                  f"{res['via']:20} {res['place'][:45]}")
        else:
            print(f"      {name[:40]:40} -")

    with open(OUT, "w") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT}")
    print(f"resolved {len(out)}/{len(targets)} ({len(out) * 100 // max(1, len(targets))}%)")


if __name__ == "__main__":
    main()
