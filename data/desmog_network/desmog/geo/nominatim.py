"""The single OSM Nominatim client for the whole pipeline.

Three search modes, one rate limit (<= 1 request/second), one shared cache
file (geo_cache.json, written back after every new entry):

  geocode(query, cache, country)            free text; hit must name the country
  geocode_postcode(pc, countries, cache)     structured postcode; bbox-checked
  geocode_institution(name, cache)           name-only; accepted only as a
                                            university/college with a matching name

Transient network errors are NOT cached (caching them would persist false
negatives); a completed search with no valid hit IS cached as a negative.
"""
import json
import re
import time
import unicodedata
import urllib.request
import urllib.parse

from ..countries import BBOX, COUNTRY_ALIASES, ISO2
from ..data import D

UA = "desmog-network-dashboard/1.0 (research; contact: local)"
CACHE = D / "geo_cache.json"

# Nominatim result types accepted for institution searches
ACADEMIC_TYPES = {"university", "college"}
# words too generic to identify an institution by name overlap
GENERIC = {"University", "College", "Polytechnic", "of", "Technical", "Applied", "Sciences",
           "State", "Science", "And", "the"}


def load_cache(path=None):
    p = path or CACHE
    return json.loads(p.read_text()) if p.exists() else {}


def save_cache(cache, path=None):
    (path or CACHE).write_text(json.dumps(cache, ensure_ascii=False, indent=0))


def _search(params, desc):
    """One polite Nominatim search. Returns parsed JSON, or None on a
    transient error (caller must not cache None)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        res = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        print(f"  ! geocode error for {desc!r}: {e}")
        return None
    finally:
        time.sleep(1.1)  # Nominatim policy: <= 1 req/sec
    return res


def geocode(query, cache, country):
    """Free-text search; keep a hit only if its display_name matches the
    country (or an alias of it). country=None means no country info:
    keep any hit (manual addresses of entities with no listed country).
    cached by query string (namespaced with "no-country|" when no country is
    given, so validation under one country never shadows another)."""
    key = query if country is not None else f"no-country|{query}"
    if key in cache:
        v = cache[key]
        return (v["lat"], v["lng"]) if v else None
    res = _search({"q": query, "format": "json", "limit": 1, "addressdetails": 1}, query)
    hit = None
    if res:
        if country is None:  # no country info: keep any hit
            hit = {"lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])}
        else:
            disp = res[0].get("display_name", "").lower()
            aliases = COUNTRY_ALIASES.get(country, [country.lower()])
            if any(a in disp for a in aliases):
                hit = {"lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])}
    cache[key] = hit
    save_cache(cache)
    return (hit["lat"], hit["lng"]) if hit else None


def geocode_postcode(pc, countries, cache):
    """Structured postcode search restricted to the country code, checked
    against the country's bounding box. (Free-text "T2H 1Z3, Canada" matched
    Canada, Kentucky.)"""
    code = re.sub(r"^(?:[A-Z]{2,3}|[A-Z][a-z]+(?: [A-Z][a-z]+)?),?\s+(?=\d{4,5}$)", "", pc)
    for country in countries:
        cc = ISO2.get(country)
        if not cc:
            continue
        key = f"pc:{cc}:{code}"
        if key not in cache:
            res = _search({"postalcode": code, "countrycodes": cc, "format": "json", "limit": 1}, code)
            if res is None:
                continue  # transient error: not cached, try the next country
            cache[key] = {"lat": float(res[0]["lat"]), "lng": float(res[0]["lon"])} if res else None
            save_cache(cache)
        v = cache[key]
        bb = BBOX.get(country)
        if v and (not bb or (bb[0] <= v["lat"] <= bb[1] and bb[2] <= v["lng"] <= bb[3])):
            return v["lat"], v["lng"]
    return None


def _fold(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def same_institution(inst, osm_name):
    """True if the OSM result's own name shares a distinctive word (5-char
    prefix, accent-folded) with the institution - "Helsinki" ~ "Helsingin
    yliopisto", but not "University of Carleton" ~ "Faculty of Dentistry"."""
    name = _fold(osm_name)
    return any(_fold(w)[:5] in name for w in re.findall(r"[\w'-]+", inst)
               if w not in GENERIC and len(w) >= 4)


def geocode_institution(name, cache):
    """Nominatim lookup by institution NAME ALONE (no country: profile
    country is often nationality, not workplace), accepting only a result
    whose OSM type is a university/college - this rejects same-named streets
    and towns. Returns (lat, lng, osm_name) or None."""
    key = "inst:" + name
    if key in cache:
        v = cache[key]
        return (v["lat"], v["lng"], v["name"]) if v else None
    res = _search({"q": name, "format": "json", "limit": 5}, name)
    if res is None:
        return None  # transient - not cached
    hit = None
    for r in res:
        if r.get("type") in ACADEMIC_TYPES and \
                same_institution(name, r.get("display_name", "").split(",")[0]):
            hit = {"lat": float(r["lat"]), "lng": float(r["lon"]),
                  "name": r.get("display_name", "").split(",")[0]}
            break
    cache[key] = hit
    save_cache(cache)
    return (hit["lat"], hit["lng"], hit["name"]) if hit else None
