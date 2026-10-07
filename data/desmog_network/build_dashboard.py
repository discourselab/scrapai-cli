#!/usr/bin/env python3
"""
Build a self-contained interactive dashboard for the DeSmog network:
  - Network view (vis-network): directed edges, node size = degree,
    color/filter by actor type / relationship type, click a node -> attributes.
  - Map view (Leaflet): nodes placed by precise location or country, size = degree.
  - Shared control panel + info panel + descriptive stats.

Output: climate-disinformation-database/dashboard.html  (open in a browser)
The page markup/CSS/JS live in dashboard_template.html (placeholder __DATA__);
this script only computes the DATA payload.

Node coordinate priority and the merge come from desmog/placement.py.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from desmog import placement
from desmog.countries import CENTROID, jitter, primary_country
from desmog.data import D, load_entities, load_jsonl
from desmog.reltypes import RGROUPS, group_of

OUT = D / "dashboard.html"
TEMPLATE = Path(__file__).parent / "dashboard_template.html"


def main():
    ents = load_entities()
    typed = load_jsonl(D / "relationships_typed.jsonl")

    # Precise node coordinates, merged by placement priority (later file wins):
    # profile/manual address > strict Wikidata > loose Wikidata > affiliation >
    # text-geocode + inheritance > country centroid fallback (below).
    LOC = placement.load_merged()

    # ---- aggregate unique directed edges ----
    pair_types = defaultdict(list)
    for r in typed:
        pair_types[(r["source_slug"], r["target_slug"])].append(r["primary_type"])

    edges = []
    deg = defaultdict(int); indeg = defaultdict(int); outdeg = defaultdict(int)
    for (s, t), types in pair_types.items():
        # representative type: most common non-"Mention/unclear" if any
        informative = [x for x in types if x != "Mention/unclear"]
        rep = Counter(informative or types).most_common(1)[0][0]
        w = len(types)
        edges.append({"from": s, "to": t, "rtype": rep, "rgroup": group_of(rep),
                      "weight": w, "allTypes": sorted(set(types))})
        deg[s] += 1; deg[t] += 1
        outdeg[s] += 1; indeg[t] += 1

    # ---- re-run inheritance so individuals benefit from Wikidata/address-placed
    # orgs (text-geocode inheritance ran before those passes; refresh it here
    # against the merged LOC). Shared with geocode_entities.py (pass 2). ----
    neighbours = defaultdict(set)
    for e in edges:
        neighbours[e["from"]].add(e["to"])
        neighbours[e["to"]].add(e["from"])
    placement.inherit_from_orgs(LOC, ents, deg, neighbours,
                                sources=placement.EXACT_SOURCES, jitter_scale=0.35)

    # ---- nodes (only those appearing in >=1 edge are placed; all kept for lookup) ----
    nodes = []
    for slug in set(deg):
        e = ents.get(slug, {})
        pc = primary_country(e.get("country"))
        geosrc = "country"
        if slug in LOC:
            lat, lng, geosrc = LOC[slug]
        else:
            cen = CENTROID.get(pc)
            dx, dy = jitter(slug)
            lat = cen[0] + dy if cen else None
            lng = cen[1] + dx if cen else None
        nodes.append({
            "id": slug,
            "name": e.get("name", slug),
            "atype": e.get("type") or "unknown",
            "country": e.get("country") or "?",
            "pcountry": pc,
            "continent": e.get("continent") or "?",
            "degree": deg[slug], "indeg": indeg[slug], "outdeg": outdeg[slug],
            "url": e.get("url", f"https://www.desmog.com/{slug}/"),
            "preview": (e.get("content") or "")[:280].replace("\n", " "),
            "lat": lat, "lng": lng, "geosrc": geosrc,
        })

    rtypes = sorted({e["rtype"] for e in edges})
    print(f"nodes: {len(nodes)}  edges: {len(edges)}  rel-types: {len(rtypes)} "
          f"({len(RGROUPS)} groups)")

    # ---- minimal attributes for ALL entities (not just networked) for stats ----
    all_nodes = [{
        "atype": e.get("type") or "unknown",
        "pcountry": primary_country(e.get("country")),
        "continent": e.get("continent") or "?",
    } for e in ents.values()]

    DATA = {"nodes": nodes, "edges": edges, "rtypes": rtypes, "rgroups": RGROUPS,
            "allNodes": all_nodes}

    OUT.write_text(TEMPLATE.read_text().replace("__DATA__", json.dumps(DATA, ensure_ascii=False)))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
