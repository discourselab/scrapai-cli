"""Generic building blocks shared by BOTH dashboards (audit + overview): escaping, the
styled tooltip, status chips, meters, flag cells, safe links, and the shared UI microcopy
(GLOSSARY, COLUMN_DEFS). Each helper keeps its legacy underscore name (the compat surface
the facade re-exports) and gains a clean public alias (`esc`, `tip`, `meter`, ...)."""

import html
import re

from core.quality.crawl_audit import LEGEND

_esc = html.escape

# --------------------------------------------------------------------------- grammar
# status → chip css class (the visual grammar: colour + glyph + label, never colour alone)
_STATUS_CLASS = {
    "extraction broken": "s-broken",
    "too few pages": "s-few",
    "incomplete": "s-incomplete",
    "manual review": "s-review",
    "ok": "s-ok",
    "discarded": "s-discarded",
}

# flag token (matched as a substring) → hover explanation. Concise UI microcopy; the
# exhaustive prose stays in the markdown (the backup / reference).
GLOSSARY = [
    (
        "pdf-only",
        "no HTML articles, but the crawl harvested PDF links — a "
        "document-repository site, not a dead spider; confirm and record a review note",
    ),
    (
        "found → try sitemap",
        "A usable sitemap was auto-discovered though USE_SITEMAP is off — switching would give verifiable coverage.",
    ),
    (
        "found sitemap empty",
        "A sitemap was discovered but yielded 0 usable URLs (malformed, index-only, or all-taxonomy) — not usable "
        "as-is. Confirm and record the reason in audit_sitemap_skip.json.",
    ),
    (
        "never-ran",
        "No production crawl yet (no crawl-stats). --limit test crawls write DB-only.",
    ),
    (
        "ran-empty",
        "It ran (crawl-stats present) but produced 0 output — investigate; re-running won't help.",
    ),
    (
        "small/partial",
        "A small or stalled production run — confirm it isn't just a small site.",
    ),
    (
        "deltafetch-stale",
        "DeltaFetch cache holds far more than the output → output lost; re-crawl with --reset-deltafetch.",
    ),
    (
        "liveness",
        "The sitemap lists many dead URLs (shown only when the live fraction is low).",
    ),
    (
        "thin?",
        "Median page is very short — possibly over-broad rules pulling in non-article junk.",
    ),
    (
        "sitemap-drift",
        "Scraped URLs barely intersect the sitemap — the denominator is unreliable.",
    ),
    ("sitemap-empty", "A configured USE_SITEMAP matched 0 of the spider's rule URLs."),
    (
        "sitemap-cap-hit",
        "Sitemap fetch hit the global cap → the denominator is truncated.",
    ),
    ("no-sitemap", "No sitemap exists to verify completeness against."),
    (
        "✓ reviewed",
        "A human marked this ok in audit_notes.json; replaces the auto-flags.",
    ),
    (
        "⚠ reviewed-stale",
        "A reviewed-ok note exists but extraction is broken — recheck it.",
    ),
    ("🗑 discard", "A human deliberately dropped this source in audit_notes.json."),
]

COLUMN_DEFS = {
    "pdf": "PDF documents harvested as URL-only rows (never downloaded under the "
    "default links_only mode). (N ext) = hosts outside the spider's own "
    "domains — external repositories/citations. Details on the PDFs tab.",
    "status": "Solution family — the single action this spider needs. Hover the chip for its meaning.",
    "sitemap": "Coverage-denominator source: yes (USE_SITEMAP) · found (auto-discovered) · ignored · no.",
    "coverage": "scraped ÷ eligible — the fraction of the pages it should have that it actually got.",
    "content": "Share of scraped pages with non-empty content (extraction success; independent of coverage).",
    "dupes": "Rows with the same URL AND identical content (re-run artifacts). Dedupe removes these.",
    "flags": "The one attention column; a clean row is empty. Hover a token for what it means.",
    "access": "May we FETCH the pages? robots for our paths / anti-scraping ToS / AI-bot bans.",
    "reuse": "May we STORE / republish? licence + AI-reuse reservations. Absent licence = default ©.",
    "licence": "The reuse licence detected on the home page or a linked legal page.",
    "links": "Count of external-PDF links to this host (sort to surface an org's own repository).",
    "robots": "robots.txt — ✓ links to the live file when the site serves one.",
    "llms": "llms.txt — ✓ (⚠✗ when it prohibits AI use) links to the live file when present.",
}


# --------------------------------------------------------------------------- cells
def _tip(text):
    """Attributes that attach the styled hover/focus tooltip (see _JS). `data-tip` drives the
    popover; `title` is kept as the no-JS / screen-reader fallback (the script stashes it on hover
    so the native tooltip never doubles up). Route every definition/explanation through this.
    """
    t = _esc(_md_strip(str(text or "")).strip(), quote=True)
    return f'data-tip="{t}" title="{t}"'


def _chip(status):
    cls = _STATUS_CLASS.get(status, "s-other")
    meaning = next((d for (l, d) in LEGEND if l == status), "")
    return f'<span class="chip {cls}" {_tip(meaning)}>{_esc(str(status))}</span>'


def _meter(pct, tip=None, invert=False):
    """A ratio as a coloured bar with its number. `tip` (e.g. the raw fraction) makes the % concrete
    on hover; defaults to the % itself. `invert=True` for lower-is-better metrics (null-date %,
    thin %): the bar width and label still show `pct`, but the colour judges 100-pct — without it
    a 95% null-date rate rendered a GREEN bar."""
    if pct is None or pct == "":
        return '<span class="na">n/a</span>'
    try:
        p = max(0, min(100, int(pct)))
    except (TypeError, ValueError):
        return '<span class="na">n/a</span>'
    good = 100 - p if invert else p
    band = "red" if good < 50 else "amber" if good < 90 else "green"
    return (
        f'<span class="meter" {_tip(tip or f"{p}%")}><span class="bar {band}" style="width:{p}%"></span>'
        f'<span class="mlabel">{p}%</span></span>'
    )


def _flag_title(token):
    for key, meaning in GLOSSARY:
        if key in token:
            return meaning
    return ""


def _flags_cell(flags):
    """Each ` · `-separated flag token becomes its own hover-tooltip (the glossary)."""
    flags = (flags or "").strip()
    if not flags:
        return "—"
    out = []
    for tok in flags.split(" · "):
        t = tok.strip()
        if not t:
            continue
        title = _flag_title(t)
        out.append(
            f'<span class="tok" {_tip(title)}>{_esc(t)}</span>'
            if title
            else f'<span class="tok">{_esc(t)}</span>'
        )
    return " ".join(out)


def _copy_btn(cmd):
    c = _esc(cmd)
    return f'<code>{c}</code> <button class="copy" type="button" data-cmd="{c}">copy</button>'


def _md_strip(s):
    """Strip the tiny markdown our shared source text carries (**bold**, `code`) so it reads
    cleanly inside a plain-text tooltip / banner."""
    return (s or "").replace("**", "").replace("`", "")


def _link(url, label):
    """An <a> for an http(s) URL; anything else (a hostile `javascript:` captured from a
    site's legal page, a relative path) renders as escaped plain text — HTML-escaping alone
    does not neutralise a javascript: href. Mirrors the JS-side guard in the popover code.
    """
    if not re.match(r"^https?://", str(url or ""), re.I):
        return _esc(str(label))
    return f'<a href="{_esc(url, quote=True)}" target="_blank" rel="noopener">{_esc(label)}</a>'


# --------------------------------------------------------------------------- public names
# Clean aliases for new consumers (overview_dashboard imports these); the underscore
# originals above remain the compat surface re-exported by the package facade.
STATUS_CLASS = _STATUS_CLASS
chip = _chip
copy_btn = _copy_btn
esc = _esc
flag_title = _flag_title
flags_cell = _flags_cell
link = _link
md_strip = _md_strip
meter = _meter
tip = _tip
