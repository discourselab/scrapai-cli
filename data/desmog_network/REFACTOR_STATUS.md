# desmog_network refactor — progress ledger

Protocol against interrupted/truncated sessions:
1. This file is the source of truth. Tool-written files persist even when a
   response is cut off.
2. One bounded phase per session: write files -> verify -> update this file.
3. If interrupted, the next session resumes at NEXT below.

Plan = the 7-step refactor agreed with the user:
  1 placement.py (priority list, one merge)
  2 data.py (loaders, degree/neighbours)
  3 countries.py (centroid/bbox/aliases/jitter)
  4 unified Nominatim + Wikidata clients
  5 delete build_graph.py (superseded)
  6 cli.py + Makefile-style orchestration
  7 tests for the pure extraction functions

## Phases

- [x] Phase 1 — created desmog/ package: data, countries, geo/nominatim,
      geo/wikidata, placement. Deleted build_graph.py and __pycache__.
      VERIFIED: entities 980; degree map equal to old inline; merged LOC equal
      to build_dashboard inline merge (985 placed / 343 exact); Nominatim
      cache-hits equal; helpers OK.
- [x] Phase 2 — rewired type_relationships.py and geocode_entities.py onto
      desmog/ (data loaders, countries, nominatim, placement.inherit_from_orgs
      with slugs=ents + place_via for the "via <name>" field).
      geocode_entities keeps transitional re-exports (CACHE/UA/load_cache/
      geocode/jitter/primary_country, D/ENTS/RELS/OUT) for the three scripts
      not yet rewired.
      VERIFIED: relationships_typed.jsonl byte-identical (diff vs /tmp/rt_before.jsonl);
      CSV rows == JSONL rows (4731); locations.jsonl byte-identical, 0 new geocodes
      (all cache hits); address_locations --dry-run (105 targets) and
      affiliation_locations --dry-run (307 targets, 61 found) work via the
      re-exports; wikidata scripts import OK.
- [x] Phase 3 — rewired wikidata_locations.py (strict) and
      wikidata_loose_locations.py (loose) onto desmog/: shared Wikidata client
      (api_get/search_entity/get_entities/coord/claim_ids/label/hq_item),
      countries (in_bbox/in_countries/countries_of), data loaders.
      Loose pass got a PersistedCache class (URL-cache written to disk after
      every entry, as before). wikidata_locations re-exports BBOX for
      address_locations.py until phase 4.
      VERIFIED: target lists equal old logic (282 strict / 181 loose);
      strict resolve() identical on all 282 cached keys (no network); loose
      URL construction byte-compatible with wikidata_loose_cache.json (all
      154 variant-search URLs cached); full strict run -> location_overrides
      .jsonl byte-identical, cache unchanged; full loose run ->
      wikidata_loose_overrides.jsonl byte-identical, caches unchanged;
      all six pipeline scripts import OK.
- [x] Phase 4 — rewired affiliation_locations.py and address_locations.py onto
      desmog/ (placement.load_merged(exclude=own-output), countries, nominatim).
      Added placement.load_merged(exclude=...) so a pass excludes only its own
      output. Dropped all transitional re-exports; geocode_entities.py and
      wikidata_locations.py no longer export anything, and no script imports
      from another script (grep clean).
      DRIFT FIX: affiliation target selection now uses the canonical merge, so
      an individual is skipped when it has an exact org neighbour via ANY pass
      (previously only geocode/strict-wikidata were considered). This matches
      build_dashboard's inheritance (_EXACT).
      VERIFIED: address targets identical (105); address_overrides.jsonl
      byte-identical. affiliation targets 307 -> 296; all 11 dropped are
      justified (exact org neighbour / exact placement); affiliation_overrides
      .jsonl diff = exactly 2 rows removed (bob-carter, don-easterbrook) which
      now inherit from an exactly-placed org neighbour. geo cache unchanged;
      all six scripts import OK.
      EXPECTED in Phase 5: dashboard.html will differ from /tmp/dashboard_before
      .html for bob-carter and don-easterbrook only (now "inherited" instead of
      "affiliation"); this is the intended drift fix, NOT a regression.
- [x] Phase 5 — rewired build_dashboard.py onto desmog/ (placement.load_merged,
      placement.inherit_from_orgs with sources=EXACT_SOURCES, countries.CENTROID
      /jitter/primary_country, data loaders). Extracted the page markup/CSS/JS
      verbatim into dashboard_template.html (placeholder __DATA__); the script
      now only computes the DATA payload.
      VERIFIED (with PYTHONHASHSEED=0 so set(deg) node order is comparable):
      new build_dashboard output is BYTE-IDENTICAL to the old code on the same
      data; DATA payload semantically equal. The only phase-4 effect on the
      dashboard is bob-carter and don-easterbrook moving affiliation->inherited
      (nothing else changed), as predicted.
      NOTE: node array order still uses set(deg) (matches old code; order is
      hash-seed dependent across unseeded runs). Could switch to sorted(deg)
      in phase 6 for stable diffs.
- [x] Phase 6 — added main()+__main__ guards to type_relationships.py and
      build_dashboard.py (importing them is now side-effect-free). Added
      cli.py (scrape | type | locate | build | all) that chains the stages
      via subprocess in the canonical order. Added test_desmog.py: 16 tests
      for the pure functions (extract_place, window, classify, name_variants,
      similar, same_institution, extract_institution, STREET/POSTCODE regexes,
      from_contact, subject_names, countries helpers, placement merge).
      Runs under pytest OR standalone (python3 test_desmog.py).
      VERIFIED: 16/16 tests pass; imports side-effect-free; full pipeline via
      `PYTHONHASHSEED=0 python3 cli.py all` -> dashboard.html BYTE-IDENTICAL to
      the golden reference (all stages cache-served, no network).

## DONE

All six phases complete and verified. The 9 original standalone scripts (~2100
lines, build_graph.py deleted) are now a desmog/ package + thin stage scripts +
cli.py + tests. Every stage reproduces its original outputs byte-for-byte; the
only intentional change is the affiliation drift fix (bob-carter,
don-easterbrook now inherit instead of being pinned to a university).

To fully re-run from scratch: `python3 cli.py all` (add `python3 cli.py scrape`
first to refresh the scraped data). Reference backups live in /tmp (p3_*, p4_*,
golden.html) and can be deleted.

Optional future work (not needed for correctness):
  - build_dashboard: sorted(deg) instead of set(deg) for stable node order.
  - type_relationships: still writes relationships_typed via main(); fine.
  - move the package out of scrapai-cli/data/ if desired (keep project.json).

## DONE 2026-10-07 — closure pass (13 unknown nodes fixed)

Problem: climate-DB profiles link to DeSmog entries from OTHER databases
(agribusiness-database, chamber of commerce, ...). Those slugs appeared in
the network as relationship targets without being climate-listing members,
so they had no entity row: the dashboard showed them as "unknown" type
(13 of 720 nodes: Bayer, BASF, Syngenta, Monsanto, JBS, ...), 8 of them
without any map placement.

Fix: scrape_climate_disinfo.py gained a closure pass — after the member loop,
linked-but-unprofiled targets get a bare entity row (type from the page's
entry-type class; country/continent stay unset — they are listing-card
metadata — so the locate passes place them via Wikidata). Their own
outbound links are NOT harvested: the edge set stays links-from-climate-
profiles only. The same 13 rows were appended to the current entities.jsonl
(same code path, same order) so the existing data benefits without a full
re-scrape; a future full re-scrape reproduces the same output.

Result (after re-running type/locate/build): 720 nodes, 0 unknown-type,
0 unplaced; 7 of the 13 placed precisely via Wikidata, 6 in the deliberate
"Unknown" ocean cluster. 16/16 tests pass. relationships.jsonl unchanged.

Operational note: while running this, Wikidata's query service was lagged, so
API calls with maxlag=5 all failed with maxlag errors and the client's
backoff (up to ~8 min per lookup) made the strict pass appear to hang; the
API answers instantly without the maxlag parameter, so the stages were run
equivalently via a temporary monkey-patched client (no committed change).

## DONE 2026-10-07 — better countries / locations (ocean cluster emptied)

Problem: 8 nodes sat in the deliberate mid-Atlantic "Unknown" cluster — the
6 closure entities that Wikidata could not pin (Fair Fuel UK, AmCham EU,
GRSB, JBS, Public Notice, USFRA) plus 2 pre-existing members whose listing
cards carry no country (Petroleum Communication Foundation, Conservative
Climate Foundation).

Fix (code + data):

- scrape_climate_disinfo.py: listing metadata now comes from ALL DeSmog
  databases (listing_meta() merges agribusiness/advertising-pr/koch/
  air-pollution listing cards; the climate listing wins on conflicts).
  Membership is still climate-only; the merged map feeds entity
  country/continent for closure entities and target metadata in
  relationships. The 13 closure entity rows were surgically updated to the
  same values a full re-scrape would produce (12 gained country/continent;
  GRSB's card carries none).
- address_locations.py: manual and Contact & Address entries for entities
  with NO listed country now geocode the query as-is (country=None) instead
  of failing against "Unknown"; the Contact & Address block cap was raised
  600→900 chars (long footnote citations, e.g. Conservative Climate
  Foundation). This also placed 6 more orgs that already had addresses in
  their profiles (SecondStreet.org, Group SJR, ...).
- desmog/geo/nominatim.py: geocode() accepts country=None (keep any hit);
  no-country lookups are cached under "no-country|<query>" so validation
  under one country can never shadow another. A stale miss for
  "Brussels, Belgium" (poisoned by the text pass under a different
  country's validation) was purged from geo_cache.json.
- desmog/countries.py: Belgium aliases now include "belgique", "belgië",
  "bruxelles-capitale" — Nominatim's top hit for Brussels is the bilingual
  region boundary whose display_name never contains "Belgium".

Manual addresses added (manual_addresses.jsonl): JBS → São Paulo (profile),
Public Notice → 2200 Wilson Blvd Arlington VA (SGC4 Trust filing quoted in
profile), Fair Fuel UK → Kent (profile), AmCham EU → Brussels, GRSB →
13560 Roller Coaster Rd Colorado Springs (IRS Form 990 via ProPublica;
no Wikidata item), PCF → Calgary (profile; street address lost in page
formatting). USFRA has no verifiable address (site unreachable, no Wikidata
item) — placed at the US country centroid.

Result: ocean cluster EMPTY (0 nodes at the mid-Atlantic fallback, was 8);
unknown-country nodes 15 → 3 (GRSB, PCF, CCF: DeSmog's listing cards carry
no country; all three are placed precisely via addresses). 7 other closure
entities keep their Wikidata pins and now display proper countries.
720 nodes, 3054 edges; 16/16 tests pass. relationships.jsonl unchanged.

## DONE 2026-10-07 — relationship-type groups (dashboard UX)

Problem: 16 fine relationship types in a flat legend — noisy, and the
secondary PALETTE has only 15 colours (Trustee collided with
Accused/criticised). Worse, the fine types are harder to browse than to
analyse: Leadership/Founder/Board/Employee/Advisor/Trustee are really one
question ("who runs whom") and counted separately.

Two-level taxonomy, new module `desmog/reltypes.py` (single source of truth):

    Affiliation             Leadership, Founder, Board/member, Employee/role,
                            Advisor, Trustee                  (1141 edges)
    Unclear                  Mention/unclear                    (742)
    Content & discourse      Published/authored, Cited/linked-to (382)
    Funding                  Funder/donor                      (358)
    Collaboration & events  Spoke at/attended, Partnered/event (262)
    Conflict & campaigns     Opposed/campaigned, Accused/criticised (84)
    Denial framing           Climate-denial framing            (64)
    Location                 Co-located/based                   (21)

Design decisions:
- Rules untouched: `type_relationships.py` still emits the 16 fine types;
  it now also writes `primary_group` (derived via reltypes). Fine types stay
  in the data (relationship_types, primary_type, allTypes) — grouping is a
  presentation/aggregation layer, not a re-classification.
- Denial framing stays its own small group rather than folding into
  discourse: it co-occurs with everything (it is a qualifier, not a tie
  kind) and is analytically central to this KB.
- "Conflict & campaigns" name reflects the rule's actual span: the
  keywords match advocacy FOR things ("support the", "promot", "pushed
  for") as well as opposition.
- Dashboard: `rgroup` on every edge, `rgroups` in DATA. Edges/network and
  map are coloured BY GROUP (8 ≤ 15 palette colours, no collisions);
  tooltips show `group · fine type (weight)`. Sidebar filter is two-level:
  group chips as the broad toggle (partial groups render at 0.7 opacity,
  empty at 0.35), each expands (▸) to its fine-type chips for drill-down;
  all/none master buttons kept. Stats: relationship-type card now groups,
  new detail card lists the 16 fine types coloured by their group.
- State model unchanged: `state.rtypeOn` remains a set of FINE types; group
  chips just toggle all their members.

Tests: taxonomy completeness test (every RULES type grouped, groups ==
RGROUPS order, unknown -> Unclear); 17/17 pass. Dashboard rebuilt:
720 nodes / 3054 edges / 16 fine types / 8 groups.
