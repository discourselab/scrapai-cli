#!/usr/bin/env python3
"""
Option E: place organisations from addresses stated in their own DeSmog profile.

Targets organisations the dashboard would otherwise pin at a country centroid:
not exactly placed by any other pass (text-geocode, Wikidata strict/loose,
university affiliation). Target selection uses the canonical placement merge
(desmog/placement.py), so it can no longer drift from the dashboard's merge
order. In priority order:

  1. CONTACT & ADDRESS section - the profile's own address block (current
     address). The first street address in it that is not marked as former
     ("initial", "formerly", "prior", "until", "previous") is used.
  2. "based at / located at / offices at <street address>" elsewhere in the
     text, ONLY when the sentence's subject is the organisation itself (its
     name, acronym, or "the group/organisation/it") - "The TaxPayers' Alliance
     is based at 55 Tufton Street" in another org's profile is ignored, as is
     the vague "based in and around".
  0. MANUAL - hand-supplied addresses in manual_addresses.jsonl always win
     (placed even if another pass already placed the org).
  3. "shares an office / the same address with X" - inherit X's coordinates
     when X is an already-placed entity.

Addresses resolve via OSM Nominatim (shared geo_cache.json), validated to any
of the org's listed countries; if the full address fails, the postcode alone
is tried (UK / Canadian / US ZIP / Australian postcode), then the city.

Output: climate-disinformation-database/address_overrides.jsonl
        {slug, lat, lng, source: "address", place, via}
        merged by build_dashboard.py; delete the file to fully revert.

Usage:
  python3 address_locations.py            # all targets
  python3 address_locations.py --dry-run  # show extracted addresses only
"""
import argparse, json, re

from desmog import placement
from desmog.countries import countries_of, in_bbox, jitter
from desmog.data import D, load_entities, load_relationships
from desmog.geo.nominatim import geocode, geocode_postcode, load_cache

OUT = D / "address_overrides.jsonl"
# hand-supplied addresses: {slug, address, postcode?, city?, precision?, note}; always win.
# precision "city" (address is just a city) -> source "address-city", labelled approx.
MANUAL = D / "manual_addresses.jsonl"

STREET = (r"\d{1,5}[A-Za-z]?(?:-\d{1,5})?\s+(?:[NSEW]\.?\s+)?(?:[A-Z][\w'.-]+\s+){1,4}"
          r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Square|Place|Lane|Drive|Boulevard|Blvd\.?"
          r"|Way|Parkway|Court|Terrace|Gardens|Row|Walk|Hill)\b")
STREET_RE = re.compile(STREET)
POSTCODE_RE = re.compile(
    r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b"     # UK
    r"|\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b"             # Canada
    r"|\b(?:[A-Z]{2}|VIC|NSW|QLD|ACT|TAS|WA|SA|NT)\s+\d{4,5}\b"  # US state+ZIP / AU state+postcode
    r"|\b[A-Z][a-z]+(?: [A-Z][a-z]+)?,?\s+\d{5}\b")              # "Florida 34994", "Texas 78701"
FORMER = re.compile(r"initial|formerly|former|prior|until|previous|moved from|originally", re.I)
CONTACT_RE = re.compile(r"Contact (?:&|and) Address(.{0,600}?)(?=Social Media|Resources|$)")
BASED_RE = re.compile(r"(?:is|are|was)\s+(?:currently\s+|now\s+)?(?:based|located|headquartered|housed)"
                      r"\s+at\s+(" + STREET + ")")
SHARE_RE = re.compile(r"(?:shares?|sharing)\s+(?:an?\s+|the\s+same\s+)?(?:address|office|offices|building|premises)"
                      r"\s+with\s+(?:the\s+)?([A-Z][^.,;(]{2,60})"
                      r"|same\s+(?:address|office|offices|building)\s+as\s+(?:the\s+)?([A-Z][^.,;(]{2,60})")


def subject_names(e):
    """Ways a profile refers to its own organisation."""
    name = e["name"]
    names = {re.sub(r"\([^)]*\)", "", name).strip(), "the group", "the organisation",
             "the organization", "the company", "the firm", "the party", "it"}
    names |= set(re.findall(r"\(([A-Z][A-Za-z0-9&]{1,10})\)", name))  # (CBP)
    initials = "".join(w[0] for w in re.findall(r"[A-Z][a-z]+", name))
    if len(initials) >= 2:
        names.add(initials)
    return {n.lower() for n in names if n}


def address_with_tail(text, m):
    """Street address plus the city/postcode that follows it (up to the postcode
    or ~70 chars), e.g. '83 Victoria Street, London SW1H 0HW'."""
    tail = text[m.end():m.end() + 80]
    pc = POSTCODE_RE.search(tail)
    if pc:
        tail = tail[:pc.end()]
    else:
        tail = re.split(r"\s(?:Email|Tel|Phone|Contact|Note|\+|\d{3,}[\s-]\d)", tail)[0][:60]
    street = re.sub(r"^\d+-(?=\d)", "", m.group(0))   # "265-438 Victoria Ave" -> "438 Victoria Ave"
    # drop unit tokens only ("Suite 2600", "#240-3088", "4th floor") - never the city after them
    tail = re.sub(r"(?:\b(?:Suite|Ste\.?|Unit)\s*[\w-]+|#\s*[\w-]+|\b\d+(?:st|nd|rd|th)\s+floor\b)",
                  "", tail, flags=re.I)
    addr = re.sub(r"\s+", " ", f"{street} {tail}").strip(" ,.")
    return addr, (pc.group(0) if pc else None)


def from_contact(text):
    m = CONTACT_RE.search(text)
    if not m:
        return None
    block = m.group(1)
    for s in STREET_RE.finditer(block):
        if FORMER.search(block[max(0, s.start() - 90):s.start()]):
            continue
        return address_with_tail(block, s)
    return None


def from_based_at(text, e):
    names = subject_names(e)
    for m in BASED_RE.finditer(text):
        sent_start = max(text.rfind(". ", 0, m.start()) + 2, m.start() - 160)
        subject = text[sent_start:m.start()].strip().lower()
        if FORMER.search(subject) or "in and around" in subject:
            continue
        if any(subject.startswith(n) or subject.endswith(n) or f"{n} " in subject[:len(n) + 15]
               for n in names):
            s = STREET_RE.search(text, m.start(1))
            return address_with_tail(text, s)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ents = load_entities()
    # exactly-placed by the other passes (own output excluded so a rerun
    # re-targets what this pass placed before)
    merged = placement.load_merged(exclude=("address_overrides.jsonl",))
    loc = placement.exact(merged)   # slug -> (lat, lng)
    by_name = {re.sub(r"\([^)]*\)", "", e["name"]).strip().lower(): s for s, e in ents.items()}

    linked = set()
    for r in load_relationships():
        linked |= {r["source_slug"], r["target_slug"]}

    manual = [json.loads(l) for l in open(MANUAL) if l.strip()] if MANUAL.exists() else []
    manual_slugs = {m["slug"] for m in manual}
    targets = [e for s, e in ents.items()
               if e.get("type") == "organization" and s not in loc and s in linked
               and s not in manual_slugs]
    cache = load_cache()
    out = []

    # ---- hand-supplied addresses: address -> postcode -> city, country-box checked ----
    for m in manual:
        countries = countries_of(ents.get(m["slug"], {})) or ["Unknown"]
        ll, via = None, "manual"
        for country in countries:
            for query, v in ((m["address"], "manual"), (m.get("city"), "manual/city")):
                if not query:
                    continue
                q = query if country.lower() in query.lower() else f"{query}, {country}"
                ll = geocode(q, cache, country)
                if ll and in_bbox(ll, country):
                    via = v
                    break
                ll = None
                if v == "manual" and m.get("postcode"):
                    ll = geocode_postcode(m["postcode"], [country], cache)
                    if ll:
                        via = "manual/postcode"
                        break
            if ll:
                break
        if ll:
            dx, dy = jitter(m["slug"], 0.004)
            city_only = m.get("precision") == "city" or via == "manual/city"
            out.append({"slug": m["slug"], "lat": ll[0] + dy, "lng": ll[1] + dx,
                        "source": "address-city" if city_only else "address",
                        "place": m["address"], "via": via})
            print(f"{m['slug'][:40]:40} {via:16} {m['address'][:60]}")
        else:
            print(f"  ! could not geocode manual address for {m['slug']}: {m['address']!r}")
    for e in targets:
        text = re.sub(r"\s+", " ", e.get("content") or "")
        countries = countries_of(e)
        hit = None
        for via, found in (("contact", from_contact(text)), ("based-at", from_based_at(text, e))):
            if not found:
                continue
            addr, pc = found
            if args.dry_run:
                print(f"{e['slug']:40} {via:9} {addr}   [pc={pc}]")
                hit = True
                break
            ll = None
            for country in countries or ["Unknown"]:
                ll = geocode(addr if not countries or country.lower() in addr.lower()
                             else f"{addr}, {country}", cache, country)
                if ll and in_bbox(ll, country):
                    break
                ll = None
            if not ll and pc:
                ll, via = geocode_postcode(pc, countries, cache), via + "/postcode"
            if not ll:
                # city-level: the words after the street, minus postcode and unit noise
                city = addr[len(STREET_RE.match(addr).group(0)) if STREET_RE.match(addr) else 0:]
                city = (city.replace(pc, "") if pc else city)
                city = re.sub(r"^\W*(?:[NSEW]{1,2}\b)?[\s,.]*|\b(?:CANADA|USA|United (?:States|Kingdom))\b",
                              "", city).strip(" ,.")
                for country in countries:
                    if len(city) >= 3:
                        ll = geocode(f"{city}, {country}", cache, country)
                        if ll and in_bbox(ll, country):
                            via = via.split("/")[0] + "/city"
                            break
                        ll = None
            if ll:
                hit = (ll[0], ll[1], addr, via)
                break
        if not hit:
            for m in SHARE_RE.finditer(text):
                other = (m.group(1) or m.group(2)).strip().lower()
                other = re.sub(r"\s+(?:and|as well|in|at|on)\b.*$", "", other)
                slug = by_name.get(other)
                if slug and slug != e["slug"] and slug in loc:
                    if args.dry_run:
                        print(f"{e['slug']:40} shares    with {ents[slug]['name']}")
                        hit = True
                        break
                    hit = (*loc[slug], f"shares office with {ents[slug]['name']}", "shared-office")
                    break
        if hit and not args.dry_run:
            dx, dy = jitter(e["slug"], 0.004)  # ~300 m: same-building orgs stay distinguishable
            out.append({"slug": e["slug"], "lat": hit[0] + dy, "lng": hit[1] + dx,
                        "source": "address", "place": hit[2], "via": hit[3]})
            print(f"{e['name'][:40]:40} {hit[3]:16} {hit[2][:60]}")

    if not args.dry_run:
        with open(OUT, "w") as f:
            for o in out:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"\nwrote {OUT}")
    print(f"targets {len(targets)}, placed {len(out) if not args.dry_run else '(dry run)'}")


if __name__ == "__main__":
    main()
