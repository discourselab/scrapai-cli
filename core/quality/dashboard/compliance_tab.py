"""The Compliance tab — flattens each domain's latest snapshot into plain dicts using the
SAME assessors the MD report uses (compliance_capture.assess_crawl / assess_reuse), and
renders the faceted access/reuse table with its evidence drawers."""

from urllib.parse import urlparse

from core.quality import compliance_capture as cc

from .widgets import COLUMN_DEFS, _esc, _link, _tip

# severity ranks for sorting the compliance columns (worst first)
_CRAWL_SEV = {"🔴": 0, "🟡": 1, "🟢": 2, "❓": 3}
_REUSE_SEV = {"🔴": 0, "🔎": 1, "⚪": 2, "🟡": 3, "🟢": 4, "❓": 5}
_CRAWL_FACET = {"🔴": "dont-fetch", "🟡": "review", "🟢": "open"}
_CRAWL_FACET_LABEL = {
    "dont-fetch": "🔴 don't fetch",
    "review": "🟡 review",
    "open": "🟢 open",
    "not-checked": "❓ not checked",
}


# --------------------------------------------------------------------------- Compliance tab
def _flatten_compliance(project, dom, org, date, rec, failed):
    """One domain's full snapshot → a plain, escapable dict, using the SAME assessors the MD
    uses (assess_crawl / assess_reuse / the cell + licence helpers)."""
    ct, ce, creasons = cc.assess_crawl(rec)
    rt, re_, rreasons = cc.assess_reuse(rec)
    ai = rec.get("ai", {})
    r = rec.get("robots", {})

    clauses = []
    for p in rec.get("legal_pages", []):
        if p.get("prohibits_scraping"):
            clauses.append(
                ("Anti-scraping clause", p.get("url"), p.get("prohibition_snippet"))
            )
        if p.get("prohibits_ai_training"):
            clauses.append(
                ("No-AI-training clause", p.get("url"), p.get("ai_training_snippet"))
            )
        if p.get("bespoke_permission"):
            clauses.append(("Reuse grant", p.get("url"), p.get("permission_snippet")))

    # Concrete AI signals — each a FACT with a link to its source doc, so a reader can verify any
    # AI-reuse/-access note. (The no-AI-training ToS clause is shown via `clauses` below, not here.)
    ai_evidence = []
    robots_url = f"https://{dom}/robots.txt"
    bots = ai.get("ai_bots_blocked") or []
    if not bots:
        sig = ai.get("ai_bot_signals") or {}
        bots = (sig.get("full") or []) + (sig.get("partial") or [])
    if bots:
        ai_evidence.append(
            {
                "label": "AI crawlers disallowed in robots.txt: " + ", ".join(bots),
                "url": robots_url,
            }
        )
    chan = (
        ai.get("channel_blocked")
        or (ai.get("ai_bot_signals") or {}).get("channel")
        or []
    )
    if chan:
        ai_evidence.append(
            {
                "label": "answer-engine crawlers blocked: " + ", ".join(chan),
                "url": robots_url,
            }
        )
    if (ai.get("tdmrep") or {}).get("present"):
        ai_evidence.append(
            {
                "label": "TDMRep reservation file present",
                "url": f"https://{dom}/.well-known/tdmrep.json",
            }
        )
    if (ai.get("ai_txt") or {}).get("present"):
        ai_evidence.append({"label": "ai.txt present", "url": f"https://{dom}/ai.txt"})
    if ai.get("tdm_meta"):
        ai_evidence.append(
            {
                "label": "tdm-reservation meta tag on the home page",
                "url": f"https://{dom}/",
            }
        )
    if ai.get("noai"):
        ai_evidence.append(
            {
                "label": "noai / noimageai in robots-meta or X-Robots-Tag",
                "url": f"https://{dom}/",
            }
        )
    _llms = rec.get("_llms_display") or ai.get("llms") or {}
    if _llms.get("verdict") in ("prohibits", "partial"):
        ai_evidence.append(
            {
                "label": f"llms.txt {_llms.get('verdict')}",
                "url": f"https://{dom}{_llms.get('path') or '/llms.txt'}",
                "quote": (ai.get("llms") or {}).get("quote"),
            }
        )

    src = rec.get("license_source") or ""
    if src.startswith("home"):
        lic_url = f"https://{dom}/"
    else:
        lic_url = src
    llms = rec.get("_llms_display") or {}
    xc = rec.get("_cross_check") or {}
    return {
        "domain": dom,
        "checked": date,
        "failed": failed,
        "source": rec.get("source"),
        "archived_ts": rec.get("archived_timestamp"),
        "crawl_emoji": ce,
        "crawl_reasons": creasons,
        "crawl_sev": _CRAWL_SEV.get(ce, 3),
        "reuse_emoji": re_,
        "reuse_reasons": rreasons,
        "reuse_sev": _REUSE_SEV.get(re_, 5),
        "facet": _CRAWL_FACET.get(ce, "not-checked"),
        "robots_cell": (cc.crawl_robots_cell(rec) or "").replace("*", ""),
        "pdf_cell": cc.crawl_pdf_cell(rec),
        "blocked_paths": [
            urlparse(u).path or u for u in (r.get("target_blocked_sample") or [])
        ],
        "pdf_evidence": r.get("pdf_block_evidence") or [],
        "comments": r.get("comments") or [],
        "notes": cc.crawl_notes(rec),
        "llms": {
            "present": bool(llms.get("present")),
            "verdict": llms.get("verdict"),
            "path": llms.get("path") or "/llms.txt",
        },
        "license": rec.get("license"),
        "license_scope": cc.license_scope(rec),
        "license_url": lic_url,
        "license_quote": rec.get("license_quote"),
        "license_low": (
            rec.get("license_confidence") == "low"
            and cc.license_class(rec.get("license")) in ("permissive", "limited")
        ),
        "license_review": cc.license_review_needed(rec),
        "all_rights_reserved": bool(rec.get("all_rights_reserved")),
        "bespoke": rec.get("bespoke_permission"),
        "copyright": rec.get("copyright"),
        "copyright_holder": rec.get("copyright_holder"),
        "copyright_year": rec.get("copyright_year"),
        "copyright_discrepancy": rec.get("copyright_discrepancy"),
        "ai_evidence": ai_evidence,
        "clauses": clauses,
        "cross_check": xc,
        "robots_present": (r.get("fetch_status") == "ok") or bool(r.get("fetched")),
    }


def build_compliance_rows(project, data=None):
    """Flatten every domain's latest snapshot (from cc.build_report_data) into plain dicts for
    the dashboard. Reads snapshots only. Unchecked domains are included as ❓ rows.
    `data` — an already-computed build_report_data() triple (the audit passes its own
    through so the snapshots are loaded + refined once); default: compute here."""
    captured, unchecked, failures = (
        data if data is not None else cc.build_report_data(project)
    )
    failed_domains = {f.get("domain") for f in failures}
    rows = [
        _flatten_compliance(project, dom, org, date, rec, dom in failed_domains)
        for dom, (org, date, rec) in captured.items()
    ]
    for dom in unchecked:
        rows.append(
            {
                "domain": dom,
                "checked": None,
                "failed": False,
                "facet": "not-checked",
                "crawl_emoji": "❓",
                "crawl_sev": 3,
                "crawl_reasons": [],
                "reuse_emoji": "❓",
                "reuse_sev": 5,
                "reuse_reasons": [],
                "unchecked": True,
            }
        )
    rows.sort(
        key=lambda e: (
            e.get("crawl_sev", 3),
            e.get("reuse_sev", 5),
            e.get("domain", ""),
        )
    )
    return rows


def _compliance_detail(e):
    out = []
    if e.get("crawl_reasons"):
        out.append(
            '<div class="why"><b>Crawl:</b> '
            + _esc("; ".join(e["crawl_reasons"]))
            + "</div>"
        )
    if e.get("reuse_reasons"):
        out.append(
            '<div class="why"><b>Reuse:</b> '
            + _esc("; ".join(e["reuse_reasons"]))
            + "</div>"
        )
    if e.get("robots_cell"):
        out.append(
            f'<div class="kv"><b>Robots vs our paths:</b> {_esc(e["robots_cell"])}</div>'
        )
    if e.get("blocked_paths"):
        out.append(
            '<div class="kv"><b>Blocked paths we\'d crawl:</b> '
            + " ".join(f"<code>{_esc(p)}</code>" for p in e["blocked_paths"][:8])
            + "</div>"
        )
    if e.get("pdf_evidence"):
        out.append(
            '<div class="kv"><b>PDFs disallowed:</b> '
            + " ".join(f"<code>{_esc(p)}</code>" for p in e["pdf_evidence"][:6])
            + "</div>"
        )
    ai_ev = e.get("ai_evidence", [])
    if ai_ev:
        out.append('<div class="kv"><b>AI signals:</b></div>')
        for ev in ai_ev:
            line = _link(ev["url"], ev["label"]) if ev.get("url") else _esc(ev["label"])
            out.append(f'<div class="flagline">{line}</div>')
            if ev.get("quote"):
                out.append(f'<blockquote>{_esc(str(ev["quote"]).strip())}</blockquote>')
    for kind, url, snippet in e.get("clauses", []):
        head = f"<b>{_esc(kind)}:</b> " + (
            _link(url, urlparse(url).path or url) if url else ""
        )
        out.append(f'<div class="kv">{head}</div>')
        if snippet:
            out.append(
                f'<blockquote>…{_esc(snippet.replace(chr(10), " ").strip())}…</blockquote>'
            )
    if e.get("license_quote"):
        out.append(
            f'<div class="kv"><b>Licence wording:</b> '
            f'{_link(e["license_url"], e.get("license_scope") or "source")}</div>'
        )
        out.append(f'<blockquote>{_esc(e["license_quote"])}</blockquote>')
    if e.get("bespoke"):
        out.append(
            f'<div class="kv"><b>Bespoke reuse grant:</b> “{_esc(e["bespoke"])}”</div>'
        )
    if e.get("copyright"):
        extra = " · ".join(
            x
            for x in (
                (
                    f'holder: {e.get("copyright_holder")}'
                    if e.get("copyright_holder")
                    else ""
                ),
                f'year: {e.get("copyright_year")}' if e.get("copyright_year") else "",
            )
            if x
        )
        out.append(
            f'<div class="kv"><b>Copyright:</b> {_esc(e["copyright"])}'
            + (f" ({_esc(extra)})" if extra else "")
            + "</div>"
        )
    disc = e.get("copyright_discrepancy")
    if disc:
        claims = " · ".join(
            f'{_esc(c.get("source", ""))}: {_esc(c.get("statement", ""))}'
            for c in disc.get("claims", [])
        )
        out.append(f'<div class="kv"><b>⚠ Copyright discrepancy:</b> {claims}</div>')
    if e.get("comments"):
        out.append(
            '<div class="kv"><b>robots.txt comments:</b> '
            + " ".join(f"<code>{_esc(c)}</code>" for c in e["comments"][:4])
            + "</div>"
        )
    xc = e.get("cross_check") or {}
    if xc.get("conflict_kinds"):
        out.append(
            '<div class="why"><b>⚠ Cross-check conflict:</b> '
            + _esc(", ".join(xc["conflict_kinds"]))
            + " — the spider's crawl-time "
            "capture disagrees with the independent check.</div>"
        )
    missed = (xc.get("legal") or {}).get("missed_substantive") or []
    if missed:
        out.append(
            '<div class="kv"><b>Terms/licence pages the spider missed:</b> '
            + " ".join(_link(u, urlparse(u).path or u) for u in missed[:6])
            + "</div>"
        )
    return "".join(out) or '<div class="kv">No further detail.</div>'


def _compliance_table(rows):
    checked = [e for e in rows if e.get("checked") is not None or e.get("failed")]
    unchecked = [
        e for e in rows if not (e.get("checked") is not None or e.get("failed"))
    ]
    if not checked and not unchecked:
        return (
            '<p class="empty">No compliance snapshots yet. Run '
            "<code>./scrapai audit --project &lt;p&gt;</code> (captures new domains) "
            "or re-run with <code>--refresh</code>.</p>"
        )
    body = []
    for i, e in enumerate(rows):
        rid = f"m{i}"
        dom = e.get("domain", "")
        if e.get("unchecked"):
            # all nine cells, each with a data-key matching the checked-row scheme —
            # a colspan here misaligned the sorter's column indexes, and keyless cells
            # sorted on the string "null"
            body.append(
                f'<tr class="fx-row" data-id="{rid}" data-name="{_esc(dom)}" '
                f'data-facet="not-checked" data-attention="0">'
                f'<td data-key="3">❓</td>'
                f'<td class="mono" data-key="{_esc(dom.lower())}">{_esc(dom)}</td>'
                f'<td class="r" data-key="-1"><span class="na">—</span></td>'
                f'<td class="r" data-key="-1"><span class="na">—</span></td>'
                f'<td data-key=""><b>NOT CHECKED</b></td>'
                f'<td data-key="3">❓</td><td data-key="5">❓</td>'
                f'<td data-key="">—</td>'
                f'<td class="flags">—</td></tr>'
                f'<tr class="fx-detail" data-id="{rid}" hidden><td colspan="9">'
                "Not yet captured. Run the audit (default captures new domains) or "
                "<code>--refresh</code>.</td></tr>"
            )
            continue
        lead = (
            "‼️"
            if e.get("failed")
            else min(
                [x for x in (e.get("crawl_emoji"), e.get("reuse_emoji")) if x],
                key=lambda x: _CRAWL_SEV.get(x, _REUSE_SEV.get(x, 9)),
                default="❓",
            )
        )
        checked_cell = (
            "‼️ failed" if e.get("failed") else _esc(str(e.get("checked") or "—"))
        )
        if e.get("source") == "wayback":
            checked_cell += (
                f' <span class="sub">📦 {_esc(str(e.get("archived_ts") or ""))}</span>'
            )
        # plain licence name FIRST (it is the sort key); decorations are display-only —
        # appending the ⚠ span before keying used to inject its quotes into data-key="…"
        # and break the <td> markup on every low-confidence row
        lic_plain = str(e.get("license") or "—")
        if e.get("license") in (None, "unknown", "") and e.get("bespoke"):
            lic_plain = "bespoke grant"
        lic = _esc(lic_plain)
        if e.get("license_low"):
            tip_low = _tip(
                "Low confidence — a bare Creative-Commons link/badge with no grant "
                "wording; verify it actually licenses the content."
            )
            lic += f' <span class="warn" {tip_low}>⚠</span>'
        arr = (
            f' <span class="sub" {_tip("An all-rights-reserved notice was found — this is NOT a reuse licence.")}>© '
            f"ARR</span>"
            if e.get("all_rights_reserved")
            else ""
        )
        att = (
            "0" if (e.get("crawl_sev", 3) >= 2 and e.get("reuse_sev", 5) >= 4) else "1"
        )
        rob = (
            _link(f"https://{dom}/robots.txt", "✓")
            if e.get("robots_present")
            else '<span class="na">—</span>'
        )
        _llms = e.get("llms") or {}
        if _llms.get("present"):
            mark = "⚠✗" if _llms.get("verdict") in ("prohibits", "partial") else "✓"
            llm = _link(f"https://{dom}{_llms.get('path') or '/llms.txt'}", mark)
        else:
            llm = '<span class="na">—</span>'
        tip_crawl = _tip(
            "; ".join(e.get("crawl_reasons") or []) or "nothing blocks fetching"
        )
        body.append(
            f'<tr class="fx-row" data-id="{rid}" data-name="{_esc(dom)}" '
            f'data-facet="{_esc(e.get("facet", "not-checked"))}" data-attention="{att}">'
            f'<td data-key="{e.get("crawl_sev", 3)}">{lead}</td>'
            f'<td class="mono" data-key="{_esc(dom.lower())}">{_esc(dom)} '
            f'<span class="caret">▸</span></td>'
            f'<td class="r" data-key="{1 if e.get("robots_present") else 0}">{rob}</td>'
            f'<td class="r" data-key="{1 if _llms.get("present") else 0}">{llm}</td>'
            f'<td data-key="{_esc(str(e.get("checked") or ""))}">{checked_cell}</td>'
            f'<td data-key="{e.get("crawl_sev", 3)}" {tip_crawl}>{e.get("crawl_emoji", "❓")}</td>'
            f'<td data-key="{e.get("reuse_sev", 5)}" '
            f'{_tip("; ".join(e.get("reuse_reasons") or []) or "reuse not assessed")}>{e.get("reuse_emoji", "❓")}</td>'
            f'<td data-key="{_esc(lic_plain.lower())}">{lic}{arr}</td>'
            f'<td class="flags">{_esc(e.get("notes") or "") or "—"}</td>'
            f"</tr>"
            f'<tr class="fx-detail" data-id="{rid}" hidden><td colspan="9">{_compliance_detail(e)}</td></tr>'
        )
    facets = "".join(
        f'<button class="facet" type="button" data-facet="{k}">{_CRAWL_FACET_LABEL[k]}</button>'
        for k in ("dont-fetch", "review", "open", "not-checked")
    )
    head = (
        f'<tr><th {_tip("Overall verdict — the worse of access and reuse.")}>＝</th>'
        '<th data-key="domain" data-type="str">domain</th>'
        f'<th class="r" data-key="robots" data-type="num" {_tip(COLUMN_DEFS["robots"])}>robots</th>'
        f'<th class="r" data-key="llms" data-type="num" {_tip(COLUMN_DEFS["llms"])}>llms</th>'
        '<th data-key="checked" data-type="str">checked</th>'
        f'<th data-key="access" data-type="num" {_tip(COLUMN_DEFS["access"])}>access</th>'
        f'<th data-key="reuse" data-type="num" {_tip(COLUMN_DEFS["reuse"])}>reuse</th>'
        f'<th data-key="licence" data-type="str" {_tip(COLUMN_DEFS["licence"])}>licence</th>'
        '<th data-key="notes" data-type="str">notes</th></tr>'
    )
    facetbar = (
        f'<div class="fx-facets" data-for="compliance">{facets}'
        '<label class="att"><input type="checkbox" class="fx-att"> needs attention</label>'
        '<input class="fx-search" placeholder="filter domain…" aria-label="filter">'
        '<button class="clear" type="button">clear</button></div>'
    )
    intro = (
        '<p class="tabintro">For each site: may we legally <b>fetch</b> its pages (<b>access</b>) '
        "and <b>reuse</b> the content (<b>reuse</b>)? Click a row for the evidence.</p>"
    )
    legend = (
        '<p class="hint">🔴 don’t fetch / can’t reuse · 🟡 needs a human check · '
        "🟢 open / permissive · ⚪ no reuse grant (default copyright) · 🔎 couldn’t verify · "
        "❓ not checked · ‼️ capture failed. "
        "Full evidence: <code>compliance_&lt;project&gt;.md</code>.</p>"
    )
    return (
        intro
        + legend
        + facetbar
        + f'<table class="fx-table" data-tab="compliance"><thead>{head}</thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )
