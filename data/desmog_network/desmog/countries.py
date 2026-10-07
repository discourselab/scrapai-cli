"""Country tables and helpers shared by every location pass.

All coordinates are (lat, lng); bounding boxes are (lat_min, lat_max,
lng_min, lng_max). This module is the single source of truth for these
tables - previously they were copied in up to three scripts.
"""
import hashlib

# Rough country centroids for the country-level fallback placement.
CENTROID = {
    "United States": (39.8, -98.6), "United Kingdom": (54.0, -2.0),
    "Canada": (56.1, -106.3), "Australia": (-25.3, 133.8), "Germany": (51.2, 10.5),
    "Netherlands": (52.1, 5.3), "New Zealand": (-41.0, 174.0), "Belgium": (50.6, 4.6),
    "France": (46.6, 2.2), "Sweden": (62.0, 15.0), "International": (15.0, -30.0),
    "India": (22.0, 79.0), "Brazil": (-10.0, -55.0), "Norway": (62.0, 10.0),
    "Finland": (64.0, 26.0), "Spain": (40.0, -4.0), "South Africa": (-29.0, 24.0),
    "Hungary": (47.0, 19.5), "Czech Republic": (49.8, 15.5), "Nigeria": (9.0, 8.0),
    "Pakistan": (30.0, 70.0), "Italy": (42.8, 12.8), "Austria": (47.6, 14.5),
    "Denmark": (56.0, 10.0), "Japan": (36.0, 138.0), "Ireland": (53.0, -8.0),
    "Estonia": (59.0, 26.0), "Portugal": (39.5, -8.0),
    "United Arab Emirates": (24.0, 54.0), "Mexico": (23.0, -102.0), "Poland": (52.0, 19.0),
}
# The text-geocode pass treats an unknown country like "International";
# build_dashboard.py deliberately leaves unknown-country nodes unplaced.
UNKNOWN_POINT = (15.0, -30.0)

# Rough bounding boxes to reject name-collision hits that land in the wrong
# country. Unlisted -> accept.
BBOX = {
    "United States": (18, 72, -170, -66), "United Kingdom": (49, 61.5, -9, 2.2),
    "Canada": (41, 84, -142, -52), "Australia": (-44, -9, 112, 154),
    "Germany": (47, 55.5, 5.3, 15.5), "Netherlands": (50.5, 54, 3, 7.5),
    "New Zealand": (-48, -33, 166, 179), "France": (41, 51.6, -5.5, 9.8),
    "Sweden": (55, 69.5, 10.5, 24.5), "Belgium": (49.4, 51.6, 2.4, 6.5),
    "Norway": (57, 71.5, 4, 31.5), "Finland": (59.5, 70.5, 19, 31.8),
    "Spain": (35.5, 44, -9.5, 4.5), "Italy": (36, 47.3, 6.5, 18.6),
    "Ireland": (51.3, 55.5, -11, -5.3), "Denmark": (54.5, 58, 8, 13),
    "Austria": (46.3, 49.1, 9.5, 17.2), "Poland": (49, 55, 14, 24.2),
}

# ISO-ish country hints for structured (postcode) Nominatim searches.
ISO2 = {"United Kingdom": "gb", "Canada": "ca", "United States": "us", "Australia": "au",
        "New Zealand": "nz", "Ireland": "ie"}

# Aliases to validate a free-text Nominatim hit lands in the right country.
COUNTRY_ALIASES = {
    "United States": ["united states", "usa"], "United Kingdom": ["united kingdom", "uk", "england", "scotland", "wales"],
    "Canada": ["canada"], "Australia": ["australia"], "Germany": ["germany", "deutschland"],
    "Netherlands": ["netherlands", "nederland"], "New Zealand": ["new zealand"], "Belgium": ["belgium"],
    "France": ["france"], "Sweden": ["sweden"], "India": ["india"], "Brazil": ["brazil", "brasil"],
    "Norway": ["norway"], "Finland": ["finland"], "Spain": ["spain"], "South Africa": ["south africa"],
    "Hungary": ["hungary"], "Czech Republic": ["czech"], "Nigeria": ["nigeria"], "Pakistan": ["pakistan"],
    "Italy": ["italy", "italia"], "Austria": ["austria"], "Denmark": ["denmark"], "Japan": ["japan"],
    "Ireland": ["ireland"], "Estonia": ["estonia"], "Portugal": ["portugal"],
    "United Arab Emirates": ["emirates", "uae"], "Mexico": ["mexico", "méxico"], "Poland": ["poland"],
}


def primary_country(c):
    return (c or "").split(",")[0].strip() or "Unknown"


def countries_of(e):
    """All useful countries listed on an entity (drops International/Unknown)."""
    return [c.strip() for c in (e.get("country") or "").split(",")
            if c.strip() and c.strip() not in ("International", "Unknown")]


def centroid_of(country):
    """Centroid for the country, or None. 'Unknown' behaves like the old
    text-geocode table (pinned mid-Atlantic)."""
    if country == "Unknown":
        return UNKNOWN_POINT
    return CENTROID.get(country)


def in_bbox(ll, country):
    """True if (lat, lng) is inside the country's box (unlisted -> True)."""
    bb = BBOX.get(country)
    return not bb or (bb[0] <= ll[0] <= bb[1] and bb[2] <= ll[1] <= bb[3])


def in_countries(lat, lng, countries):
    """True if the point is inside ANY of the listed countries' boxes."""
    boxes = [BBOX[c] for c in countries if c in BBOX]
    if not boxes:
        return True
    return any(b[0] <= lat <= b[1] and b[2] <= lng <= b[3] for b in boxes)


def jitter(slug, scale=2.2):
    """Deterministic (dx, lng-offset / dy, lat-offset) pair from the slug, so
    co-located entities always scatter the same way across runs."""
    h = int(hashlib.md5(slug.encode()).hexdigest(), 16)
    dx = ((h & 0xFFFF) / 0xFFFF - 0.5) * 2 * scale
    dy = (((h >> 16) & 0xFFFF) / 0xFFFF - 0.5) * 2 * scale
    return dx, dy
