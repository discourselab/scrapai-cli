"""Report-side assessors: the crawl/reuse verdicts, the table cells and notes,
the crawl-capture-vs-independent cross-check, and the colour sort orders the
report tables use."""

import re
from urllib.parse import urlparse

from .robots import blocks_whole_site, parse_robots
from .signals import LIMITED_LICENSE_RE, classify_llms
from .store import (
    TARGET_CAP,
    crawl_captured_legal_urls,
    latest_crawl_file,
    spider_dir_for_domain,
)

# ---- report helpers: distil the scraping-relevant signals ----------------


def license_class(lic):
    """permissive | limited | restricted | unknown — for sorting/flagging."""
    low = (lic or "").lower()
    if not low or low == "unknown":
        return "unknown"
    if "all rights reserved" in low:
        return "restricted"
    if "public domain" in low or "cc0" in low:
        return "permissive"
    if "open government" in low:
        return "permissive"
    if (
        "creative commons" in low
        or low.startswith("cc ")
        or "cc-by" in low
        or "cc by" in low
    ):
        return "limited" if LIMITED_LICENSE_RE.search(low) else "permissive"
    return "unknown"


def crawl_robots_cell(rec):
    """What robots.txt means for OUR crawler: whether it blocks the paths we crawl."""
    r = rec.get("robots", {})
    # when the displayed robots came from the spider's crawl-capture (independent fetch was
    # blocked), say so — otherwise a real robots would look like it was fetched here.
    via = " *(via crawl)*" if r.get("source") == "crawl-capture" else ""
    if not r.get("fetched"):
        # a fetch that returned NOTHING (blocked) is not a confirmed absence — don't call it open
        return (
            "couldn't fetch robots"
            if r.get("fetch_status") == "failed"
            else "no robots.txt"
        )
    if blocks_whole_site(r.get("disallow")):
        return "✋ blocks all (/)" + via
    blocked, checked = r.get("target_urls_blocked"), r.get("target_urls_checked")
    cap = (
        " (capped)" if checked and checked >= TARGET_CAP else ""
    )  # more paths than we tested
    if blocked:
        return f"⛔ {blocked}/{checked}{cap} of our paths blocked" + via
    if checked:
        return f"✓ 0/{checked}{cap} blocked" + via  # none of our paths disallowed
    if r.get("disallow"):
        return f"{len(r['disallow'])} rule(s), overlap untested" + via
    return "open" + via


def crawl_pdf_cell(rec):
    """Whether robots forbids the article-linked PDFs we capture. No robots.txt → nothing
    blocks them ('ok')."""
    r = rec.get("robots", {})
    if not r.get("fetched"):
        return "ok"
    return "⛔ blocked" if r.get("pdf_blocked") else "ok"


def llms_cell(rec, domain):
    """The dedicated `/llms.txt` column: a CLICKABLE link to the live file when the org has one
    (from either witness) — `✓` for AI-friendly curation, `⚠✗` when it prohibits — else `—`.
    """
    d = rec.get("_llms_display") or {}
    if not d.get("present"):
        return "—"
    mark = "⚠✗" if d.get("verdict") in ("prohibits", "partial") else "✓"
    return f"[{mark}](https://{domain}{d.get('path') or '/llms.txt'})"


def ai_scrape_flag(ai):
    """The AI-SCRAPING (access) signal, new field or legacy fallback (old snapshots only had
    per_ai_bot for whole-site AI-bot bans on the access axis)."""
    v = ai.get("ai_scrape_block")
    return ai.get("per_ai_bot") if v is None else v


def ai_reuse_flag(ai):
    """The AI-REUSE (machine-readable reservation) signal, new field or legacy fallback."""
    v = ai.get("ai_reuse_reserved")
    return ai.get("site_wide_ai") if v is None else v


def crawl_notes(rec):
    """All compact secondary signals folded into ONE cell (no extra columns) — shown only when
    present. Blank for a clean row. AI signals are labelled machine-readable vs legal-text.
    """
    r, ai = rec.get("robots", {}), rec.get("ai", {})
    llms = ai.get("llms") or {}
    notes = []
    # ACCESS: AI-scraping bans (machine-readable)
    if ai_scrape_flag(ai):
        chan = (
            ai.get("channel_blocked")
            or (ai.get("ai_bot_signals") or {}).get("channel")
            or []
        )
        notes.append(
            f"blocks {', '.join(chan)} (your channel)"
            if chan
            else "AI-scrape blocked (robots/ai.txt)"
        )
    # REUSE: AI reservations — machine-readable vs legal-text
    if (
        ai.get("tdm_reserved")
        or ai.get("noai")
        or llms.get("verdict") in ("prohibits", "partial")
    ):
        notes.append("AI-reuse reserved (machine-readable)")
    elif ai.get("ai_reuse_reserved") is None and ai.get("site_wide_ai"):
        notes.append("site-wide AI/TDM opt-out")  # old snapshot, no split fields
    if ai.get("ai_training_clause"):
        notes.append("no-AI-training (ToS, legal-only)")
    # (llms.txt is shown in its own dedicated clickable column, not here)
    tos = next(
        (p["url"] for p in rec.get("legal_pages", []) if p.get("prohibits_scraping")),
        None,
    )
    if tos:
        notes.append(f"ToS: {urlparse(tos).path}")
    if r.get("crawl_delay"):
        notes.append(f"crawl-delay {r['crawl_delay']}s")
    if r.get("comments"):
        notes.append("robots-comment")
    # cross-check conflict (crawl-capture vs independent) — one compact token
    cc = rec.get("_cross_check")
    if cc and cc.get("conflict_kinds"):
        notes.append("⚠ cross-check: " + ", ".join(cc["conflict_kinds"]))
    return " · ".join(notes)


def license_scope(rec):
    """Where the licence was found — site-wide (home/meta) vs a specific sub-page, so a
    page-scoped grant (e.g. a content-reuse policy) isn't read as covering everything.
    """
    src = rec.get("license_source")
    if not src:
        return "—"
    if src.startswith("home"):
        return "home"
    return urlparse(src).path or src


def license_source_link(rec, domain):
    """The 'where the licence was found' cell, made CLICKABLE: the scope label linked to
    the actual page it was read from (or the homepage for a site-wide grant). The licence
    itself is shown as plain text — the useful link is the source, not creativecommons.org.
    """
    src = rec.get("license_source")
    if not src:
        return "—"
    label = license_scope(rec).replace("|", "\\|")
    if src.startswith("home"):
        return f"[{label}](https://{domain}/)"
    return f"[{label}]({src})"


def assess_crawl(rec):
    """(tier, emoji, reasons) for the ACCESS question — may we fetch/crawl the pages?
    🔴 robots blocks ALL our paths (or whole-site) / ToS directly prohibits scraping ; 🟡 SOME
    paths blocked / an AI-bot scraping ban (our UA isn't the blocked bot, but the site signals
    no-AI intent — review) / robots disallows PDFs / robots unfetchable / untestable overlap ;
    🟢 open. (crawl-delay and a genuine "no robots.txt" are notes.)"""
    r = rec.get("robots", {})
    ai = rec.get("ai", {})
    blocks_all = blocks_whole_site(r.get("disallow"))
    blocked = r.get("target_urls_blocked") or 0
    checked = r.get("target_urls_checked")
    delay = r.get("crawl_delay")
    has_rules = bool(r.get("disallow"))
    prohibits = [p for p in rec.get("legal_pages", []) if p.get("prohibits_scraping")]
    # ACCESS axis uses the AI-SCRAPING signal only (robots AI-bot bans + ai.txt) — the
    # AI-REUSE reservations (TDMRep/noai/training) live on the reuse axis now.
    ai_scrape = ai_scrape_flag(ai)
    channel = (
        ai.get("channel_blocked")
        or (ai.get("ai_bot_signals") or {}).get("channel")
        or []
    )
    pdf_blocked = r.get("pdf_blocked")
    pdf_ev = r.get("pdf_block_evidence") or []
    fetch_failed = r.get("fetch_status") == "failed"

    # all of our tested paths blocked (or whole-site) is a hard 🔴; a PARTIAL block (some
    # paths blocked, others open — e.g. robots bars /search but allows /government content)
    # is a 🟡 to review, not a full block.
    full_block = blocks_all or (blocked and checked and blocked >= checked)
    partial_block = blocked and not full_block

    reasons = []
    if blocks_all:
        reasons.append("robots `Disallow: /` — blocks the whole site")
    elif blocked:
        reasons.append(
            f"robots blocks {blocked}/{checked} of the paths we crawl"
            + ("" if full_block else " (others open — check which)")
        )
    if ai_scrape:
        if channel:
            reasons.append(
                f"robots blocks {', '.join(channel)} (AI / answer-engine crawlers)"
            )
        else:
            reasons.append("AI crawlers disallowed (robots / ai.txt)")
    if prohibits:
        reasons.append("ToS prohibits automated access / scraping")
    if pdf_blocked:
        reasons.append(
            "robots disallows PDFs — we capture article-linked PDFs"
            + (f" (e.g. `{pdf_ev[0]}`)" if pdf_ev else "")
        )
    if delay:
        reasons.append(f"crawl-delay {delay}s — allowed but must throttle")
    if fetch_failed:
        reasons.append(
            "robots.txt couldn't be fetched (even via browser) — not verified open"
        )

    # 🔴 only for a HARD block: robots bars all the paths we crawl, or the ToS directly
    # prohibits scraping. An AI-bot ban is NOT a hard block (our UA isn't that bot) — it's a
    # 🟡 review (the site signals no-AI intent, worth a human call for an AI KB).
    if full_block or prohibits:
        return 3, "🔴", reasons
    # AI-bot ban / partial path block / PDFs-blocked / unfetchable robots / untestable overlap
    # → review. A crawl-delay is just "throttle" (not a permission block), so it's a note.
    # Genuine "no robots.txt" = open (not flagged); a FAILED fetch is flagged.
    if (
        ai_scrape
        or partial_block
        or pdf_blocked
        or fetch_failed
        or (r.get("fetched") and has_rules and checked is None)
    ):
        if checked is None and has_rules:
            reasons.append(
                "disallow rules present but no spider paths to test — review overlap"
            )
        return 2, "🟡", reasons
    return 0, "🟢", reasons or ["nothing blocks our crawl"]


def assess_reuse(rec):
    """(tier, emoji, reasons) for the REUSE question — may we store/republish the content?
    🟢 permissive licence found SITE-WIDE ; 🟡 licence with conditions (NC/ND/SA), OR a
    permissive licence found only on a sub-page (scope unconfirmed — a CC link on a
    /terms page is not proof the article corpus is CC) ; 🔎 no licence found AND we were
    blocked reading the site (couldn't verify — human review) ; ⚪ no explicit grant (default
    copyright — permission needed). Independent of whether we may crawl."""
    ai = rec.get("ai", {})
    lc = license_class(rec.get("license"))
    lic = rec.get("license")
    src = rec.get("license_source") or ""
    conf = rec.get("license_confidence")
    bespoke = rec.get("bespoke_permission")
    # AI-reuse signals, classified: a BROAD machine-readable reservation (TDMRep / noai /
    # prohibiting llms.txt) likely binds RAG/indexing; a TRAINING-ONLY ToS clause may not.
    broad_reservation = bool(
        ai.get("tdm_reserved")
        or ai.get("noai")
        or (ai.get("llms") or {}).get("verdict") in ("prohibits", "partial")
        or (ai.get("ai_reuse_reserved") is None and ai.get("site_wide_ai"))
    )
    training_only = bool(ai.get("ai_training_clause")) and not broad_reservation
    # site-wide = found on the homepage / its meta / JSON-LD; otherwise a sub-page grant whose
    # scope we can't trust to cover the content we actually scrape.
    page_scoped = bool(src) and not src.startswith("home")

    # PRECEDENCE: a broad AI/TDM reservation demotes reuse to 🔴 *for an AI KB* — the licence is
    # still shown, never silently overridden (classify, don't collapse).
    if broad_reservation:
        kinds = []
        if ai.get("tdm_reserved"):
            kinds.append("TDMRep reservation")
        if ai.get("noai"):
            kinds.append("noai")
        if (ai.get("llms") or {}).get("verdict") in ("prohibits", "partial"):
            kinds.append("llms.txt prohibits")
        why = (
            "machine-readable AI/TDM reservation ("
            + ", ".join(kinds or ["AI reservation"])
            + ")"
        )
        if lic and lc != "unknown":
            why += f"; licence: {lic}"
        return 3, "🔴", [why]

    # base reuse verdict from the licence / a bespoke grant
    if lc == "permissive":
        if conf == "low":  # bare CC link/badge, no grant wording — could be a widget
            tier, emoji, why = (
                2,
                "🟡",
                [
                    f"permissive licence ({lic}) but only a bare CC link/"
                    "badge with no grant wording — verify it actually licenses the content"
                ],
            )
        elif page_scoped:
            tier, emoji, why = (
                2,
                "🟡",
                [
                    f"permissive licence ({lic}) but found only on "
                    f"{license_scope(rec)}, not the home page — confirm it covers the article content"
                ],
            )
        else:
            tier, emoji, why = (
                0,
                "🟢",
                [f"permissive licence ({lic}) — reuse allowed within its terms"],
            )
    elif lc == "limited":
        w = f"licence restricts reuse ({lic}) — respect NC/ND/SA conditions"
        if page_scoped:
            w += f"; and only on {license_scope(rec)}, not the home page"
        tier, emoji, why = 2, "🟡", [w]
    elif bespoke:
        # a directed non-named grant ("may be reproduced for non-commercial use") — a real
        # reuse signal, but informal: verify the scope before relying on it.
        tier, emoji, why = (
            2,
            "🟡",
            [
                f"bespoke reuse permission (not a named licence) — “{bespoke}”; "
                "verify it covers the content you scrape"
            ],
        )
    elif license_review_needed(rec):
        tier, emoji, why = (
            2,
            "🔎",
            [
                "no licence found AND the site blocked our probe — couldn't "
                "verify a licence/reservation wasn't present; check the terms/licence manually"
            ],
        )
    else:
        tier, emoji, why = (
            1,
            "⚪",
            [
                "no reuse grant FOUND (may be undeclared, or missed — "
                "detection covers the home page + linked legal pages only); default ©, permission needed"
            ],
        )

    # a TRAINING-ONLY clause is a SOFT caveat: it may not bind retrieval/RAG, so it downgrades a
    # clean 🟢 to 🟡 (review the wording) but never overrides a stronger verdict.
    if training_only:
        caveat = "ToS bars AI/ML training (legal-text clause)"
        if emoji == "🟢":
            return 2, "🟡", why + [caveat]
        return tier, emoji, why + [caveat]
    return tier, emoji, why


def header_probe_blocked(rec):
    """True if the HTTP-header probe was refused for this site (Cloudflare/TLS/etc.). 'skipped'
    (Wayback) and 'ok' are NOT blocked; a missing block (old snapshot) reads as not-blocked.
    """
    return (rec.get("http_headers") or {}).get("fetch_status") == "blocked"


def license_review_needed(rec):
    """A no-licence row we couldn't fully verify: no reuse grant found (not permissive/limited)
    AND the header probe was blocked, so a licence/reservation may have been there but unread.
    These get a 🔎 human-review mark in the reuse table instead of a clean ⚪."""
    return license_class(rec.get("license")) not in (
        "permissive",
        "limited",
    ) and header_probe_blocked(rec)


# Whole-TOKEN legal indicators for the cross-check gap — matched against the URL path's
# tokens (split on non-alphanumerics), NOT as substrings, so "rights" can't match
# "donorbillofrights" and "tos" can't match "datos". Bare "rights" is deliberately ABSENT (a
# donor bill of rights / human rights page is not a reuse-terms page). A few common non-English
# tokens are included; full language-aware legal-page handling is a separate TODO.
SUBSTANTIVE_LEGAL_TOKENS = {
    "terms",
    "tos",
    "conditions",
    "condition",
    "eula",
    "disclaimer",
    "copyright",
    "copyrights",
    "license",
    "licence",
    "licensing",
    "reuse",
    "republish",
    "republishing",
    "permission",
    "permissions",
    "privacy",
    "legal",
    "acceptable",
    "agreement",
    "usage",
    # common non-English equivalents (partial)
    "terminos",
    "condiciones",
    "privacidad",
    "proteccion",
    "datenschutz",
    "impressum",
    "mentions",
    "legales",
    "aviso",
    "rgpd",
    "gdpr",
}


# Asset file types that are never a legal PAGE (a plugin's gdpr-cookie CSS, a sprite, etc.).
# .pdf is NOT here — real terms/privacy docs are often PDFs.
_ASSET_EXT = re.compile(
    r"\.(?:css|js|mjs|json|xml|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|"
    r"eot|map|scss|less)$",
    re.I,
)


def _is_substantive_legal(u):
    """True if a URL's path has a TOKEN that marks a real terms/licence/privacy page (whole-
    token match — avoids 'rights'⊂'donorbillofrights' and 'tos'⊂'datos' false positives) and
    isn't an asset file (a gdpr-cookie plugin's .css, etc.)."""
    path = urlparse(u or "").path.lower()
    if not path or _ASSET_EXT.search(path):
        return False
    return bool(set(re.split(r"[^a-z0-9]+", path)) & SUBSTANTIVE_LEGAL_TOKENS)


def _norm_legal(u):
    """Normalise a legal-page URL for witness set-comparison (drop scheme/www/slash/query)."""
    try:
        p = urlparse(u or "")
    except Exception:
        return (u or "").lower().rstrip("/")
    host = (p.netloc or "").lower().removeprefix("www.")
    return host + (p.path.rstrip("/") or "/")


def cross_check(project, domain, rec):
    """REPORT-TIME join of the two witnesses — the spider's CRAWL-CAPTURE (crawls/robots_*.txt,
    llms_*.txt, legal-page rows) vs this independent snapshot. Returns
      {robots, llms, legal, conflict_kinds}
    States per signal: agree | conflict | rescued | independent-only | none. Wayback domains
    are skipped (crawl-capture is against archive.org, not the original). The conflict is
    FLAGGED, never auto-resolved; `rescued` (independent blocked, crawl filled the gap) is NOT
    a conflict. Used by both the report and the audit summary (one source of truth)."""
    out = {
        "robots": {"state": "none"},
        "llms": {"state": "none"},
        "legal": {"spider_only": [], "independent_only": []},
        "conflict_kinds": [],
    }
    if rec.get("source") == "wayback":
        return out
    spider_dir = spider_dir_for_domain(project, domain)
    if not spider_dir:
        return out

    # robots — compare the `*`-group directive SETS (the snapshot stores the `*` group), so
    # whitespace/comment/reorder differences are ignored; only real rule changes show.
    crawl_robots = latest_crawl_file(spider_dir, "robots")
    rb = rec.get("robots", {})
    indep_ok = rb.get("fetched")
    if crawl_robots:
        cg = parse_robots(crawl_robots[1])["groups"].get(
            "*", {"disallow": [], "allow": []}
        )
        if not indep_ok:
            out["robots"] = {
                "state": "rescued",
                "detail": "independent robots fetch failed/blocked — the crawl captured it (authoritative)",
                "crawl_date": str(crawl_robots[2]),
            }
        elif set(cg.get("disallow", [])) == set(rb.get("disallow", [])) and set(
            cg.get("allow", [])
        ) == set(rb.get("allow", [])):
            out["robots"] = {"state": "agree"}
        else:
            out["robots"] = {
                "state": "conflict",
                "crawl_date": str(crawl_robots[2]),
                "crawl_only": sorted(
                    set(cg.get("disallow", [])) - set(rb.get("disallow", []))
                )[:6],
                "independent_only": sorted(
                    set(rb.get("disallow", [])) - set(cg.get("disallow", []))
                )[:6],
            }
            out["conflict_kinds"].append("robots")
    elif indep_ok:
        out["robots"] = {"state": "independent-only"}

    # llms — a CONFLICT only when the scrape MISSED an llms the probe found, or the two
    # directly CONTRADICT (one prohibits, the other doesn't). The reverse — the crawl captured
    # it but the probe was blocked — is NOT a problem (the crawl is authoritative). Presence
    # from either side is still recorded so the dedicated llms column can show it.
    crawl_llms = latest_crawl_file(spider_dir, "llms")
    indep_llms = (rec.get("ai") or {}).get("llms") or {}
    c_present, i_present = bool(crawl_llms), bool(indep_llms.get("present"))
    state = (
        "agree"
        if (c_present and i_present)
        else "crawl-only" if c_present else "independent-only" if i_present else "none"
    )
    out["llms"] = {"crawl": c_present, "independent": i_present, "state": state}
    if i_present and not c_present:  # probe has it, crawl doesn't
        # …but only a real MISS if the spider's compliance extension demonstrably RAN (it
        # captured robots). With no compliance capture at all (old crawl / extension never
        # ran), this isn't a 'miss' — same as we don't flag robots 'independent-only'.
        if crawl_robots:
            out["conflict_kinds"].append("llms")
            out["llms"]["reason"] = "probe found /llms.txt the crawl didn't capture"
    elif c_present and i_present:  # both have it — contradiction?

        def prohibit(v):
            return v in ("prohibits", "partial")

        cv, iv = classify_llms(crawl_llms[1])[0], indep_llms.get("verdict")
        if iv and prohibit(cv) != prohibit(iv):
            out["conflict_kinds"].append("llms")
            out["llms"].update(
                state="conflict",
                crawl_verdict=cv,
                independent_verdict=iv,
                reason="crawl and probe disagree on whether llms.txt prohibits",
            )

    # legal/terms pages — list BOTH directions for the human, but the legal gap is
    # INFORMATIONAL (cross-check section only): it does NOT raise the inline ⚠ token, because
    # the independent mini-crawl routinely finds generic policy pages (privacy/cookie/
    # accessibility) the spider legitimately doesn't store as content — that would be noise.
    # Only ROBOTS / LLMS conflicts (rare, high-signal) drive the token. `gap` marks when the
    # spider DID capture legal pages yet missed a SUBSTANTIVE terms/licence one.
    sp_legal, _pdfs = crawl_captured_legal_urls(spider_dir)
    indep_legal = {p["url"] for p in rec.get("legal_pages", []) if p.get("url")}
    sp_norm = {_norm_legal(u): u for u in sp_legal}
    in_norm = {_norm_legal(u): u for u in indep_legal}
    spider_only = sorted(u for k, u in sp_norm.items() if k not in in_norm)
    independent_only = sorted(u for k, u in in_norm.items() if k not in sp_norm)
    subst = [u for u in independent_only if _is_substantive_legal(u)]
    out["legal"] = {
        "spider_only": spider_only[:8],
        "independent_only": independent_only[:8],
        "missed_substantive": subst[:8],
        "gap": bool(sp_legal and subst),
    }
    return out


def _cell(x):
    """Markdown-table-safe cell (escape pipes); '—' for empty. Module-level twin of the
    closure used inside write_report, so detail-block helpers can use it too."""
    return "—" if x in (None, "", "unknown") else str(x).replace("|", "\\|")


# Fixed display order so each colour forms ONE contiguous block, most-attention-needed first,
# all-clear last. We sort on the EMOJI (the colour), not the assessment tier — the tiers
# collide (🟡 and 🔎 both = 2), which is what scattered the rows.
CRAWL_COLOR_ORDER = {"🔴": 0, "🟡": 1, "🟢": 2}
# ascending reuse-permissiveness: 🔴 reserved (AI/TDM — hard block) → 🔎 unknown/blocked → ⚪ no
# grant → 🟡 conditional grant → 🟢 permissive. A 🟡 row HAS a licence (just with conditions) so
# it's MORE permissive than a ⚪ row with no grant at all — it belongs below ⚪, not above it.
REUSE_COLOR_ORDER = {"🔴": 0, "🔎": 1, "⚪": 2, "🟡": 3, "🟢": 4}


def _color_rank(order, emoji):
    """Sort index for `emoji` in a colour order (unknown emoji sort last, before NOT-CHECKED)."""
    return order.get(emoji, len(order))
