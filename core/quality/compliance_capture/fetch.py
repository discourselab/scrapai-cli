"""Fetching: the `./scrapai inspect` wrapper, readable-text extraction, and the
best-effort HTTP-header-only probe (X-Robots-Tag / TDMRep headers) the body
fetch cannot see."""

import html as _html
import os
import re
import subprocess
import urllib.error
import urllib.request

from core.quality import _env

from .store import _global_user_agent


def visible_text(html):
    """Readable text from HTML, stdlib-only but robust to modern markup.
    Drops <script>/<style>/<svg>/<noscript>/<head> WITH contents (else JS/CSS/SVG noise
    pollutes the text and triggers false matches); block-level tag ENDS become newlines;
    the tag regex honours '>' inside quoted attributes (class="[&>svg]:w-6"); entities
    unescaped."""
    s = re.sub(r"(?is)<(script|style|noscript|svg|template|head)\b.*?</\1>", " ", html)
    s = re.sub(
        r"(?i)<(?:br|/p|/div|/li|/h[1-6]|/tr|/section|/article)\b[^>]*>", "\n", s
    )
    s = re.sub(r"""(?s)<(?:[^>"']|"[^"]*"|'[^']*')*>""", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def inspect(url, project, outdir, browser, proxy):
    """Fetch `url` via ./scrapai inspect into outdir/page.html; return its text or None."""
    os.makedirs(outdir, exist_ok=True)
    # repo-anchored launcher + pinned cwd + ABS output dir: from any other working
    # directory the old relative "./scrapai" failed silently (OSError → None for
    # every fetch) and a relative DATA_DIR would resolve differently in the child.
    cmd = [
        _env.SCRAPAI,
        "inspect",
        url,
        "--project",
        project,
        "--output-dir",
        os.path.abspath(outdir),
    ]
    if browser:
        cmd.append("--browser")
    if proxy and proxy != "auto":
        cmd += ["--proxy-type", proxy]
    try:
        subprocess.run(
            cmd, capture_output=True, timeout=180, cwd=str(_env.project_root)
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    page = os.path.join(outdir, "page.html")
    if not os.path.exists(page):
        return None
    with open(page, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ---- HTTP-header-only compliance signals -----------------------------------
# `./scrapai inspect` hands back the response BODY only, so two header-delivered signals are
# invisible to the body scans above: X-Robots-Tag (the header twin of <meta name=robots>) and
# the TDMRep HTTP headers (Tdm-Reservation / Tdm-Policy). We recover them with a SEPARATE,
# best-effort stdlib probe — so NO change to inspect/framework is needed. The trade-off: this
# probe has none of inspect's proxy / Cloudflare / TLS-stealth, so on protected sites it gets
# blocked. Hence a tri-state status: a PRESENT header is always a real signal, but an ABSENCE
# means something only when the probe actually succeeded ('ok'), never when 'blocked'.

# response codes that mean the request was refused/challenged rather than answered — under
# these we DON'T trust an absent header (what came back is a block page, not the real site).
HEADER_BLOCK_CODES = {401, 403, 406, 409, 429, 451}


def http_response_headers(url):
    """(status, headers) for `url` via a plain stdlib GET — no proxy/CF/TLS-stealth.
    status: 'ok' the server answered and its headers are trustworthy · 'blocked' the request
    was refused/challenged/errored (a present header is still real; an absent one proves
    nothing). headers: lower-cased name→value map (best-effort; empty on total failure).
    Body is left undownloaded — we only need the headers; some servers 405 a bare HEAD so we
    issue a GET but never read the response body."""
    req = urllib.request.Request(url, headers={"User-Agent": _global_user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code, raw = resp.status, resp.headers
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.headers  # error responses still carry real headers
    except Exception:
        return "blocked", {}
    try:
        headers = {k.lower(): v for k, v in raw.items()}
    except Exception:
        headers = {}
    status = "blocked" if (code in HEADER_BLOCK_CODES or code >= 500) else "ok"
    return status, headers


def header_signals(url):
    """The header-only compliance signals for `url`, ready to embed in the report:
      {fetch_status, x_robots_tag, tdm_reservation, tdm_policy, noai}
    tdm_reservation '1' = TDMRep rights reserved; x_robots_tag may itself carry noai/noimageai
    (the header form of the noai meta). fetch_status 'ok'|'blocked' gates trust in an ABSENCE.
    """
    status, h = http_response_headers(url)
    xr = h.get("x-robots-tag")
    return {
        "fetch_status": status,
        "x_robots_tag": xr,
        "tdm_reservation": h.get(
            "tdm-reservation"
        ),  # "1" = reserved, "0" = not reserved
        "tdm_policy": h.get("tdm-policy"),  # URL of the TDM policy, if provided
        "noai": bool(xr and re.search(r"noai|noimageai", xr, re.I)),
    }


def header_tdm_reserved(hdrs):
    """True if the TDM-Reservation HTTP header asserts a reservation (any non-zero value)."""
    v = (hdrs or {}).get("tdm_reservation")
    return bool(v is not None and str(v).strip() not in ("", "0"))


def looks_html(text):
    return "<html" in text[:300].lower() or "<!doctype html" in text[:300].lower()
