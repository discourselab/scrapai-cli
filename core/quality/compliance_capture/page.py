"""HTML-derived facts: robots/TDM/copyright meta, rel=license, CC links, JSON-LD,
legal-link discovery, and the cross-page licence pick (detect_license)."""

import json
import re
from urllib.parse import urlparse

from .signals import CC_URL_RE, LICENSE_RE, first, license_sentence, split_license

# Path words that mark a page worth fetching for terms/licence/reuse signals. Broadened
# toward licence/reuse/policy paths (e.g. /content-and-comment-policy carrying a CC grant).
LEGAL_WORDS = (
    "terms",
    "legal",
    "privacy",
    "copyright",
    "cookie",
    "disclaimer",
    "terms-of-use",
    "terms-of-service",
    "terms-and-conditions",
    "tos",
    "user-agreement",
    "acceptable-use",
    "conditions",
    "eula",
    "license",
    "licence",
    "reuse",
    "re-use",
    "republish",
    "republishing",
    "permission",
    "permissions",
    "rights",
    "syndication",
    "usage",
    "policy",
)
# Within the discovered pages, fetch licence/reuse ones first so they survive the cap.
LICENSE_PRIORITY = (
    "license",
    "licence",
    "reuse",
    "re-use",
    "republish",
    "permission",
    "syndicat",
    "copyright",
    "rights",
)
TERMS_PRIORITY = (
    "terms",
    "tos",
    "conditions",
    "use-agreement",
    "user-agreement",
    "acceptable-use",
    "eula",
    "disclaimer",
)


def robots_meta(html):
    """Concatenated content of all <meta name="robots"|"ai"> tags (noai/noindex/…)."""
    vals = []
    for tag in re.findall(r"(?i)<meta\b[^>]*>", html):
        if re.search(r"""(?i)name=["'](robots|ai|googlebot)["']""", tag):
            m = re.search(r"""(?i)content=["']([^"']*)["']""", tag)
            if m:
                vals.append(m.group(1).strip())
    joined = ", ".join(v for v in vals if v)
    return joined or None


def tdm_meta(html):
    """True if the page declares a TDMRep reservation via meta — <meta name="tdm-reservation"
    content="1"> (1 = rights reserved). The HTML delivery of the same site-wide signal as
    /.well-known/tdmrep.json (the HTTP-header form is captured separately by header_signals).
    """
    for tag in re.findall(r"(?i)<meta\b[^>]*>", html or ""):
        if re.search(r"""(?i)name=["']tdm-reservation["']""", tag):
            m = re.search(r"""(?i)content=["']?\s*([0-9])\s*["']?""", tag)
            if m and m.group(1) != "0":
                return True
    return False


def meta_copyright(html):
    m = re.search(r"""(?i)<meta\b[^>]*name=["']copyright["'][^>]*>""", html)
    if m:
        c = re.search(r"""(?i)content=["']([^"']*)["']""", m.group(0))
        return c.group(1).strip() if c else None
    return None


def link_license(html):
    m = re.search(r"""(?i)<link\b[^>]*rel=["']license["'][^>]*>""", html)
    if m:
        h = re.search(r"""(?i)href=["']([^"']+)["']""", m.group(0))
        return h.group(1) if h else None
    return None


def cc_from_html(html):
    """A Creative Commons / public-domain licence inferred from a creativecommons.org
    hyperlink anywhere in the markup. Returns (canonical_name, url) or (None, None)."""
    m = CC_URL_RE.search(html or "")
    if not m:
        return None, None
    kind, path = m.group(1).lower(), m.group(2).strip("/").lower()
    parts = path.split("/")
    code, ver = parts[0], (parts[1] if len(parts) > 1 else "")
    if kind == "publicdomain" or code in ("zero", "mark"):
        name = (
            "CC0 1.0 (public domain dedication)"
            if code == "zero"
            else "Public Domain Mark"
        )
        return name, f"https://creativecommons.org/publicdomain/{path}"
    name = "CC " + code.upper() + (f" {ver}" if ver else "")
    return name, f"https://creativecommons.org/licenses/{path}"


def jsonld(html):
    """license / copyrightHolder / copyrightYear from JSON-LD (incl. @graph)."""
    out = {"license": None, "copyright_holder": None, "copyright_year": None}
    for block in re.findall(
        r"(?is)<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        html,
    ):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for top in objs:
            if isinstance(top, dict) and isinstance(top.get("@graph"), list):
                objs = objs + top["@graph"]
        for o in objs:
            if not isinstance(o, dict):
                continue
            if not out["license"] and o.get("license"):
                lic = o["license"]
                out["license"] = (
                    lic if isinstance(lic, str) else json.dumps(lic, ensure_ascii=False)
                )
            ch = o.get("copyrightHolder")
            if not out["copyright_holder"] and ch:
                out["copyright_holder"] = (
                    ch.get("name")
                    if isinstance(ch, dict)
                    else (
                        ch
                        if isinstance(ch, str)
                        else json.dumps(ch, ensure_ascii=False)
                    )
                )
            if not out["copyright_year"] and o.get("copyrightYear"):
                out["copyright_year"] = str(o["copyrightYear"])
    return out


def detect_license(pages, jl):
    """Pick the licence across [(src, html, text), ...]. An EXPLICIT grant (CC link,
    JSON-LD, rel=license, CC/PD/OGL prose) outranks a generic footer 'all rights
    reserved', so a CC notice on a sub-page is not masked by the homepage footer.
    Returns {license, license_url, license_source, license_quote} — license_quote is the
    full grant sentence read from the winning source page (None if not in readable text).
    """
    src_text = {src: text for src, _, text in pages}

    def quote_for(src):
        """Grant sentence from the source page's readable text (JSON-LD maps to home)."""
        t = src_text.get(src) or (
            src_text.get("home") if src and src.startswith("home") else None
        )
        return license_sentence(t)

    cc = rel = prose = fallback = None
    cc_url = rel_src = prose_src = fallback_src = None
    for src, html, text in pages:
        if not cc:
            n, u = cc_from_html(html)
            if n:
                cc, cc_url, cc_src = n, u, src
        if not rel:
            r = link_license(html)
            if r:
                rel, rel_src = r, src
        if not prose:
            p = split_license(text)
            if p:
                prose, prose_src = p, src
        if not fallback:
            f = first(LICENSE_RE, text)
            # a bare 'all rights reserved' is footer boilerplate, NOT a reuse licence — it's
            # surfaced in its own column (all_rights_reserved), never as the licence value, so
            # "no grant found" isn't mis-shown as "reuse forbidden" (it can coexist with a CC grant)
            if f and "all rights reserved" not in f.lower():
                fallback, fallback_src = f, src
    # confidence: "high" when a grant SENTENCE backs it (or it's a structured rel/JSON-LD
    # declaration); "low" when it's only a bare creativecommons.org link / stray phrase with
    # no surrounding grant wording — i.e. could be a footer badge or third-party widget.
    if cc:
        q = quote_for(cc_src)
        return {
            "license": cc,
            "license_url": cc_url,
            "license_source": cc_src,
            "license_quote": q,
            "license_confidence": "high" if q else "low",
        }
    if jl.get("license"):
        return {
            "license": jl["license"],
            "license_url": None,
            "license_source": "home (JSON-LD)",
            "license_quote": quote_for("home (JSON-LD)"),
            "license_confidence": "high",
        }
    if rel:
        return {
            "license": "declared (rel=license)",
            "license_url": rel,
            "license_source": rel_src,
            "license_quote": quote_for(rel_src),
            "license_confidence": "high",
        }
    if prose:
        return {
            "license": prose,
            "license_url": None,
            "license_source": prose_src,
            "license_quote": quote_for(prose_src),
            "license_confidence": "high",
        }
    if fallback:
        return {
            "license": fallback,
            "license_url": None,
            "license_source": fallback_src,
            "license_quote": quote_for(fallback_src),
            "license_confidence": "low",
        }
    return {
        "license": "unknown",
        "license_url": None,
        "license_source": None,
        "license_quote": None,
        "license_confidence": None,
    }


def legal_links(html, domain):
    """Same-host links whose path mentions a LEGAL_WORD, licence/reuse pages first."""
    found = {}
    for href in re.findall(r"""href=["']([^"']+)["']""", html, re.I):
        p = urlparse(href)
        host = (p.netloc or domain).lower().removeprefix("www.")
        if host and host != domain:
            continue
        segs = [s for s in p.path.lower().split("/") if s]
        if any(any(w in seg for w in LEGAL_WORDS) for seg in segs):
            url = href if p.netloc else f"https://{domain}{p.path}"
            found[url.split("?")[0].rstrip("/")] = True

    def rank(u):
        ul = u.lower()
        if any(w in ul for w in LICENSE_PRIORITY):
            return 0
        if any(w in ul for w in TERMS_PRIORITY):
            return 1
        return 2

    return sorted(found, key=lambda u: (rank(u), u))
