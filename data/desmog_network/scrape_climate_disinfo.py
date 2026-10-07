#!/usr/bin/env python3
"""
Scrape the DeSmog Climate Disinformation Database.

For every profile (individual or organization) listed at
https://www.desmog.com/climate-disinformation-database/ this captures:
  - name, slug, url, type (individual/organization), body text
  - relationships: every in-text link to ANOTHER DeSmog database entry
    (person or org), with the anchor text and the surrounding paragraph
    (the text of the link = the described relationship).

Outputs (under data/desmog_network/climate-disinformation-database/):
  - entities.jsonl    one row per profile
  - relationships.jsonl   one row per (source -> target) in-text link

Usage:
  python3 scrape_climate_disinfo.py --limit 5      # sample
  python3 scrape_climate_disinfo.py                # full run
"""
import argparse, json, re, sys, time
from pathlib import Path
import requests
from parsel import Selector

BASE = "https://www.desmog.com"
LISTING = f"{BASE}/climate-disinformation-database/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
OUT = Path(__file__).parent / "climate-disinformation-database"

SECTION_DENY = {
    "opinion-analysis", "all-articles", "agribusiness-database",
    "advertising-pr-database", "koch-network-database",
    "air-pollution-lobbying-database", "climate-disinformation-database",
    "maps", "about", "our-team", "contact", "jobs", "databases", "series",
    "donate", "republishing-guidelines", "media-resources", "send-us-tips",
    "privacy-policy-desmog", "privacy-policy-uk", "newsletter", "terms-of-use",
    "entry", "making-a-complaint",
}

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url, tries=3):
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1))
    return None


def entry_slugs():
    """All DeSmog database entry slugs (post type 'entry') from the sitemaps."""
    slugs = set()
    for sm in ("entry-sitemap.xml", "entry-sitemap2.xml"):
        xml = get(f"{BASE}/{sm}")
        if not xml:
            continue
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            p = loc.replace(BASE, "").strip("/")
            if p and "/" not in p and p != "entry":
                slugs.add(p)
    return slugs


def listing_members():
    """Map of slug -> {type, country, continent} from the DB listing cards."""
    html = get(LISTING)
    sel = Selector(text=html)
    info = {}
    for c in sel.css("div.grid-view-entry"):
        href = c.css("a::attr(href)").get() or ""
        m = re.match(r"https://www\.desmog\.com/([^/]+)/?$", href)
        if not m:
            continue
        cls = c.attrib.get("class", "")
        t = re.search(r"\btype-(\w+)", cls)
        cont = re.search(r"entry-continent-([\w-]+)", cls)
        countries = [x.strip() for x in
                     c.css(".grid-view-entry-country::text").getall() if x.strip()]
        info[m.group(1)] = {
            "type": t.group(1) if t else None,
            "country": ", ".join(countries) if countries else None,
            "continent": cont.group(1).replace("-", " ") if cont else None,
        }
    return info


def seg(href):
    m = re.match(r"https://www\.desmog\.com/([^/?#]+)/?$", href or "")
    return m.group(1) if m else None


def scrape_profile(slug, all_entries, listing):
    url = f"{BASE}/{slug}/"
    html = get(url)
    if not html:
        return None, []
    sel = Selector(text=html)

    meta = listing.get(slug, {})
    m = re.search(r"entry-type-([a-z0-9_-]+)", html)
    etype = (m.group(1) if m else None) or meta.get("type")

    title = (sel.css("title::text").get() or "").replace(" - DeSmog", "").strip()

    content_root = sel.css(
        ".elementor-widget-theme-post-content .elementor-widget-container"
    )
    body_text = "\n".join(
        t.strip() for t in content_root.css("::text").getall() if t.strip()
    )

    entity = {
        "slug": slug,
        "url": url,
        "name": title,
        "type": etype,
        "country": meta.get("country"),
        "continent": meta.get("continent"),
        "content": body_text,
    }

    # Relationships: in-text links to OTHER database entries, with context.
    rels = []
    seen = set()
    for p in content_root.css("p, li"):
        ptext = " ".join(t.strip() for t in p.css("::text").getall() if t.strip())
        for a in p.css("a"):
            href = a.attrib.get("href", "")
            tslug = seg(href)
            if not tslug or tslug == slug:
                continue
            if tslug in SECTION_DENY or tslug.isdigit():
                continue
            if tslug not in all_entries:
                continue  # only links to actual people/orgs in the DeSmog DB
            anchor = " ".join(
                t.strip() for t in a.css("::text").getall() if t.strip()
            )
            key = (tslug, ptext)
            if key in seen:
                continue
            seen.add(key)
            tmeta = listing.get(tslug, {})
            rels.append({
                "source_slug": slug,
                "source_name": title,
                "source_type": etype,
                "source_country": meta.get("country"),
                "target_slug": tslug,
                "target_name": anchor,
                "target_url": f"{BASE}/{tslug}/",
                "target_type": tmeta.get("type"),
                "target_country": tmeta.get("country"),
                "anchor_text": anchor,
                "context": ptext,
            })
    return entity, rels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N profiles")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between requests")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    print("Loading DeSmog entry sitemap ...", flush=True)
    all_entries = entry_slugs()
    print(f"  {len(all_entries)} total DeSmog database entries", flush=True)

    print("Loading climate-disinformation-database membership ...", flush=True)
    listing = listing_members()
    members = sorted(set(listing) & all_entries)
    print(f"  {len(members)} climate-disinformation-database profiles", flush=True)

    if args.limit:
        members = members[: args.limit]
        print(f"  (limited to {len(members)})", flush=True)

    ent_f = open(OUT / "entities.jsonl", "w", encoding="utf-8")
    rel_f = open(OUT / "relationships.jsonl", "w", encoding="utf-8")
    n_ent = n_rel = 0
    for i, slug in enumerate(members, 1):
        entity, rels = scrape_profile(slug, all_entries, listing)
        if entity:
            ent_f.write(json.dumps(entity, ensure_ascii=False) + "\n")
            n_ent += 1
            for r in rels:
                rel_f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n_rel += len(rels)
            print(f"[{i}/{len(members)}] {slug} ({entity['type']}) "
                  f"-> {len(rels)} relationships", flush=True)
        else:
            print(f"[{i}/{len(members)}] {slug} FAILED", flush=True)
        ent_f.flush(); rel_f.flush()
        time.sleep(args.delay)
    ent_f.close(); rel_f.close()
    print(f"\nDone: {n_ent} entities, {n_rel} relationships", flush=True)
    print(f"  {OUT/'entities.jsonl'}")
    print(f"  {OUT/'relationships.jsonl'}")


if __name__ == "__main__":
    main()
