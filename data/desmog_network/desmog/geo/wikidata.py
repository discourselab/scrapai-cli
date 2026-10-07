"""The single Wikidata API client for the whole pipeline.

api_get():      GET with exponential backoff on 429/503/maxlag and a polite
                pause after each request; an optional URL-keyed response
                cache (the loose pass persists one to wikidata_loose_cache.json).
get_entities(): batched wbgetentities (<= 50 ids per call).
Helpers:        coord, claim_ids, label, hq_item read the entity JSON.
"""
import json
import time
import urllib.error
import urllib.request
import urllib.parse

API = "https://www.wikidata.org/w/api.php"
UA = "desmog-network-dashboard/1.0 (research; contact: local)"


def api_get(params, url_cache=None):
    """Wikidata GET with exponential backoff on 429/503 (incl. maxlag
    errors) and a polite pause after each request."""
    params = {**params, "format": "json", "maxlag": 5}
    url = API + "?" + urllib.parse.urlencode(params)
    if url_cache is not None and url in url_cache:
        return url_cache[url]
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    delay = 5.0
    for attempt in range(8):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read())
            time.sleep(1.0)  # be polite / stay under the rate limit
            if data.get("error", {}).get("code") == "maxlag":
                raise urllib.error.HTTPError(url, 503, "maxlag", None, None)
            if url_cache is not None:
                url_cache[url] = data
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(delay)
                delay = min(delay * 2, 120)
                continue
            raise
    raise RuntimeError("exhausted retries")


def search_entity(name, url_cache=None, limit=5):
    r = api_get({"action": "wbsearchentities", "search": name,
                 "language": "en", "type": "item", "limit": limit}, url_cache)
    return r.get("search", [])


def get_entities(qids, url_cache=None, props="claims|labels|descriptions|aliases"):
    """Batched wbgetentities (<= 50 ids per call)."""
    out = {}
    qids = [q for q in dict.fromkeys(qids) if q]
    for i in range(0, len(qids), 50):
        r = api_get({"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                     "props": props, "languages": "en"}, url_cache)
        out.update(r.get("entities", {}))
    return out


def coord(claims):
    """(lat, lng) from P625, else None."""
    for s in claims.get("P625", []):
        try:
            v = s["mainsnak"]["datavalue"]["value"]
            return float(v["latitude"]), float(v["longitude"])
        except Exception:
            pass
    return None


def claim_ids(claims, prop):
    """All item-ids used by a property's statements."""
    out = []
    for s in claims.get(prop, []):
        try:
            out.append(s["mainsnak"]["datavalue"]["value"]["id"])
        except Exception:
            pass
    return out


def label(ent, default=""):
    return ent.get("labels", {}).get("en", {}).get("value", default)


def hq_item(claims):
    """Q-id of P159 (headquarters location), else None."""
    ids = claim_ids(claims, "P159")
    return ids[0] if ids else None
