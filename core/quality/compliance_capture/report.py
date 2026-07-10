"""The project rollup: build_report_data() (snapshot load + report-time
refinements, split into stage helpers) and write_report() (the markdown report,
split into per-section builders that each return list[str])."""

import glob
import json
import os
import re
from urllib.parse import urlparse

from core.quality._env import DATA_DIR, project_root

from .assess import (
    CRAWL_COLOR_ORDER,
    REUSE_COLOR_ORDER,
    _cell,
    _color_rank,
    assess_crawl,
    assess_reuse,
    crawl_notes,
    crawl_pdf_cell,
    crawl_robots_cell,
    cross_check,
    license_class,
    license_review_needed,
    license_source_link,
    llms_cell,
)
from .fetch import header_tdm_reserved
from .robots import (
    ai_bot_signals,
    ai_scrape_block_from,
    parse_robots,
    robots_blocks_pdfs,
    robots_blocks_targets,
    robots_comment_signals,
    robots_view_from_text,
)
from .signals import (
    ai_training_prohibition,
    classify_llms,
    refine_license,
    scrape_prohibition,
)
from .store import (
    compliance_root,
    latest_crawl_file,
    latest_snapshot,
    project_domains,
    spider_dir_for_domain,
    spider_target_urls,
    spider_user_agent,
)


def crawl_detail_block(project, org, dom, date, rec):
    """Expanded crawl-restriction detail: which of OUR paths robots blocks, AI signals,
    and the directed anti-scraping clause (with snippet)."""
    _, emoji, reasons = assess_crawl(rec)
    r = rec.get("robots", {})
    ai = rec.get("ai", {})
    hdrs = rec.get("http_headers", {})
    out = [f"### {emoji} {dom}", ""]
    if rec.get("source") == "wayback":
        out.append(
            f"- **Source:** 📦 Wayback snapshot @ {rec.get('archived_timestamp') or '?'} "
            "(live site gone — reflects the archived site, not today)"
        )
    out.append("- **Why:** " + ("; ".join(reasons) if reasons else "—"))
    out.append(f"- **Robots vs our crawl:** {crawl_robots_cell(rec)}")
    sample = r.get("target_blocked_sample") or []
    if sample:
        # dedup by displayed path — start_urls that differ only in query string (e.g.
        # /search/all?organisations=…) collapse to the same path and would otherwise repeat
        paths = list(dict.fromkeys(urlparse(u).path or u for u in sample))
        out.append(
            "  - blocked paths we'd crawl: " + ", ".join(f"`{p}`" for p in paths[:8])
        )
    if r.get("pdf_blocked"):
        ev = r.get("pdf_block_evidence") or []
        out.append(
            "- **PDFs disallowed by robots** (we capture article-linked PDFs)"
            + (": " + ", ".join(f"`{e}`" for e in ev[:6]) if ev else "")
        )
    if r.get("crawl_delay"):
        out.append(f"  - crawl-delay: {r['crawl_delay']}s")
    if ai.get("site_wide_ai"):
        bits = []
        if ai.get("tdmrep", {}).get("present"):
            bits.append("TDMRep `/.well-known/tdmrep.json`")
        if ai.get("tdm_meta"):
            bits.append("`<meta tdm-reservation>`")
        if ai.get("robots_meta") and re.search(
            r"noai|noimageai", ai["robots_meta"], re.I
        ):
            bits.append(f"meta: {ai['robots_meta']}")
        if ai.get("ai_txt", {}).get("present"):
            bits.append("ai.txt")
        if any(p.get("prohibits_ai_training") for p in rec.get("legal_pages", [])):
            bits.append("ToS: no AI/ML-training clause")
        if header_tdm_reserved(hdrs):
            bits.append("`Tdm-Reservation` HTTP header")
        if hdrs.get("noai"):
            bits.append(f"`X-Robots-Tag: {hdrs.get('x_robots_tag')}`")
        out.append("- **Site-wide AI/TDM opt-out:** " + (" · ".join(bits) or "yes"))
    if ai.get("per_ai_bot"):
        out.append(
            "- **Per-AI-bot bans:** robots whole-site-disallows named AI/training "
            "crawlers (generic — doesn't apply to our UA, but signals no-AI intent)"
        )
    for p in rec.get("legal_pages", []):
        if p.get("prohibits_ai_training"):
            snip = (p.get("ai_training_snippet") or "").replace("\n", " ").strip()
            out.append(f"- **No-AI-training clause:** {p['url']}")
            if snip:
                out.append(f"  > …{snip}…")
        if p.get("prohibits_scraping"):
            snip = (p.get("prohibition_snippet") or "").replace("\n", " ").strip()
            out.append(f"- **Anti-scraping clause:** {p['url']}")
            if snip:
                out.append(f"  > …{snip}…")
    # llms.txt — independent witness (usually AI-friendly; flagged only if it prohibits)
    llms = ai.get("llms") or {}
    if llms.get("present"):
        if llms.get("verdict") in ("prohibits", "partial"):
            out.append(
                f"- **llms.txt:** ⚠ {llms['verdict']} — "
                f"{_cell(llms.get('quote') or 'restrictive directive')}"
            )
        else:
            out.append(
                "- **llms.txt:** present — AI-friendly curation (a positive signal)"
            )
    # answer-engine bots blocked by name — relevant because our KB feeds them
    chan = ai.get("channel_blocked") or []
    if chan:
        out.append(
            f"- **Answer-engine bots blocked:** {', '.join(chan)} — our KB routes "
            "content to these, so a block on them is directly relevant"
        )
    # robots.txt comment policy/contact lines (parse_robots discards comments)
    if r.get("comments"):
        out.append(
            "- **robots.txt comments:** "
            + " · ".join(f"`{c}`" for c in r["comments"][:4])
        )
    # copyright — full statement + parsed holder/year (de-emphasised: absence ≠ free reuse)
    if rec.get("copyright"):
        extra = " · ".join(
            x
            for x in (
                (
                    f"holder: {rec.get('copyright_holder')}"
                    if rec.get("copyright_holder")
                    else ""
                ),
                (
                    f"year: {rec.get('copyright_year')}"
                    if rec.get("copyright_year")
                    else ""
                ),
            )
            if x
        )
        out.append(
            f"- **Copyright:** {_cell(rec['copyright'])}"
            + (f" ({extra})" if extra else "")
        )
    if rec.get("bespoke_permission"):
        out.append(f"- **Bespoke reuse grant:** “{_cell(rec['bespoke_permission'])}”")
    # header-only signals: an X-Robots-Tag that isn't already shown as the noai opt-out above
    # (e.g. noindex/nofollow) is informational; a blocked probe is flagged so an absence here
    # isn't mistaken for "no reservation".
    if hdrs.get("x_robots_tag") and not hdrs.get("noai"):
        out.append(
            f"- **`X-Robots-Tag`:** `{hdrs['x_robots_tag']}` (header-only directive)"
        )
    if hdrs.get("fetch_status") == "blocked":
        out.append(
            "- **HTTP-header probe blocked** — `X-Robots-Tag` / TDMRep headers couldn't "
            "be verified (the probe has no proxy/CF); absence of a header signal here "
            "proves nothing"
        )
    # repo-relative display path — the report is shareable, so never embed this
    # machine's absolute layout (DATA_DIR is repo-anchored/absolute via _env)
    snap = os.path.join(compliance_root(project), org, date or "")
    try:
        snap = "./" + os.path.relpath(snap, project_root)
    except ValueError:
        pass
    out.append(f"- **Snapshot:** `{snap}`")
    out.append("")
    return "\n".join(out)


def _load_captured(project):
    """Every org's LATEST snapshot: {domain: (org, date, rec)} (Wayback wrapper rows
    with no resolvable original domain are dropped)."""
    captured = {}
    for od in glob.glob(os.path.join(compliance_root(project), "*")):
        if not os.path.isdir(od):
            continue
        org = os.path.basename(od)  # the org slug (e.g. rmi_org)
        date, rec = latest_snapshot(od)
        if rec and rec.get("domain") != "web.archive.org":
            captured[rec.get("domain", org)] = (org, date, rec)
    return captured


def _refresh_robots_derived(project, captured):
    # Recompute the DERIVED robots signals (path overlap + PDF block) from each snapshot's
    # stored robots.txt using the current spider config + improved wildcard/UA-aware matcher,
    # so older snapshots benefit from the logic fixes without re-fetching. The robots.txt
    # itself is the captured evidence; only the derived overlap is refreshed here.
    for dom, (org, date, rec) in captured.items():
        refine_license(
            rec
        )  # CC-variant upgrade + subset-confidence, from the stored grant sentence
        rb = rec.setdefault("robots", {})
        if not rb.get("fetched"):
            continue
        rpath = os.path.join(compliance_root(project), org, date or "", "robots.txt")
        if not os.path.exists(rpath):
            continue
        rtxt = open(rpath, encoding="utf-8", errors="replace").read()
        ua = rec.get("user_agent") or spider_user_agent(project, dom)
        checked, tblocked = robots_blocks_targets(
            rtxt, spider_target_urls(project, dom), ua
        )
        rb["target_urls_checked"] = checked
        rb["target_urls_blocked"] = len(tblocked) if checked is not None else None
        rb["target_blocked_sample"] = tblocked[:8]
        pb, pe = robots_blocks_pdfs(rtxt, dom, ua)
        rb["pdf_blocked"], rb["pdf_block_evidence"] = pb, pe[:8]
        # recompute comments + AI-bot signals from the stored robots.txt so the tightened
        # matchers apply to OLD snapshots without re-fetching (robots.txt itself is unchanged).
        rb["comments"] = robots_comment_signals(rtxt)
        rb["ai_bots"] = ai_bot_signals(parse_robots(rtxt)["groups"])


def _rescan_legal_pages(project, captured):
    # Recompute the DIRECTED legal-page prohibitions from the stored legal text, so a regex fix
    # (e.g. the GDPR 'automated processing' false positive) applies to existing snapshots
    # without re-capture. Only the legal-page scans are refreshed — homepage-derived signals
    # (bespoke/copyright/meta) can't be, as the homepage text isn't stored.
    for dom, (org, date, rec) in captured.items():
        snap_dir = os.path.join(compliance_root(project), org, date or "")
        for p in rec.get("legal_pages", []):
            fp = os.path.join(snap_dir, p.get("file") or "")
            if not p.get("file") or not os.path.exists(fp):
                continue
            txt = open(fp, encoding="utf-8", errors="replace").read()
            proh, ait = scrape_prohibition(txt), ai_training_prohibition(txt)
            p["prohibits_scraping"], p["prohibition_snippet"] = bool(proh), proh
            p["prohibits_ai_training"], p["ai_training_snippet"] = bool(ait), ait
        ai = rec.setdefault("ai", {})
        ai["ai_training_clause"] = any(
            p.get("prohibits_ai_training") for p in rec.get("legal_pages", [])
        )
        # Recompute the AI-REUSE aggregate from the (refreshed) concrete signals so a corrected
        # ai_training_clause propagates and a stale legacy `site_wide_ai`/`ai_reuse_reserved` — e.g.
        # one set True at capture by the old training false positive — no longer lingers as a note /
        # false 🔴 reuse. Concrete signals only; nothing invented. A stored derived key is
        # respected; when it is ABSENT (legacy snapshot, pre split-fields) it is re-derived from
        # the concrete evidence the snapshot DOES store — tdmrep/tdm_meta/robots_meta/headers,
        # exactly mirroring capture()'s own derivation — so a genuine legacy reservation is
        # never silently overwritten to False. The derived keys are written back so downstream
        # consumers (the dashboard's AI-evidence drawer) see them on legacy recs too.
        tdm_reserved = ai.get("tdm_reserved")
        if tdm_reserved is None:
            tdm_reserved = bool(
                (ai.get("tdmrep") or {}).get("present")
                or ai.get("tdm_meta")
                or header_tdm_reserved(rec.get("http_headers") or {})
            )
        noai = ai.get("noai")
        if noai is None:
            rmeta = ai.get("robots_meta")
            noai = bool(
                (rmeta and re.search(r"noai|noimageai", rmeta, re.I))
                or (rec.get("http_headers") or {}).get("noai")
            )
        ai["tdm_reserved"], ai["noai"] = bool(tdm_reserved), bool(noai)
        reserved = bool(
            tdm_reserved
            or noai
            or (ai.get("llms") or {}).get("verdict") in ("prohibits", "partial")
            or ai.get("ai_training_clause")
        )
        ai["ai_reuse_reserved"] = reserved
        ai["site_wide_ai"] = reserved


def _join_cross_check(project, captured):
    # Report-time cross-check join (crawl-capture vs independent) — stored on each rec for the
    # notes token + the cross-check section, and reused by the audit's compliance_summary so
    # the two outputs can never disagree.
    for dom, (org, date, rec) in captured.items():
        xc = cross_check(project, dom, rec)
        rec["_cross_check"] = xc
        # RESCUE: the independent robots fetch was blocked but the spider's crawl captured the
        # real robots.txt → DISPLAY that (the crawl downloader is authoritative), instead of
        # the misleading "no robots.txt". (Report-time, so it benefits old snapshots too.)
        if xc.get("robots", {}).get("state") == "rescued":
            cr = latest_crawl_file(spider_dir_for_domain(project, dom), "robots")
            if cr:
                ua = rec.get("user_agent") or spider_user_agent(project, dom)
                rec["robots"] = robots_view_from_text(project, dom, cr[1], ua)
                rec["robots"]["crawl_date"] = str(cr[2])
                # the rescued robots may carry AI-bot bans the (blocked) independent capture
                # never saw — refresh the robots-derived AI-scrape signal so the verdict/notes
                # match the displayed robots.
                ai, bots = rec.setdefault("ai", {}), rec["robots"]["ai_bots"]
                ai["ai_bot_signals"] = bots
                ai["channel_blocked"] = bots.get("channel") or []
                ai["ai_scrape_block"] = ai_scrape_block_from(
                    bots, (ai.get("ai_txt") or {}).get("present")
                )
        # llms display (for the dedicated clickable column): present from EITHER witness;
        # verdict from the independent snapshot, else classify the crawl-captured file.
        ai_llms = (rec.get("ai") or {}).get("llms") or {}
        xl = xc.get("llms", {})
        present = bool(ai_llms.get("present")) or bool(xl.get("crawl"))
        verdict = ai_llms.get("verdict")
        if present and not ai_llms.get("present") and xl.get("crawl"):
            cl = latest_crawl_file(spider_dir_for_domain(project, dom), "llms")
            if cl:
                verdict = classify_llms(cl[1])[0]
        # carry the RECORDED path — capture may have found only /.well-known/llms.txt,
        # and a link hardcoded to /llms.txt would 404 (crawl-witness-only case has no
        # recorded path → default /llms.txt, the path the spider captures).
        rec["_llms_display"] = {
            "present": present,
            "verdict": verdict,
            "path": ai_llms.get("path") or "/llms.txt",
        }


def _load_failures(project):
    # Capture-failure markers (unreachable domains) — surfaced prominently every run.
    failures = []
    for mk in sorted(
        glob.glob(os.path.join(compliance_root(project), "*", "_capture_failed.json"))
    ):
        try:
            failures.append(json.load(open(mk)))
        except (OSError, json.JSONDecodeError):
            pass
    return failures


def build_report_data(project):
    """Build + fully process every org's LATEST compliance snapshot for `project` — the SAME
    data write_report() formats into markdown. Returns (captured, unchecked, failures) where
    captured = {domain: (org, date, rec)} and each rec has been refined in place (licence
    refinements, robots path-overlap + PDF re-derivation, legal-page re-scan, cross-check,
    rescued-robots display, llms display). Reads snapshot files only — no writes. Exposed so
    the HTML dashboard can render the full compliance evidence from this one code path instead
    of re-parsing the markdown."""
    captured = _load_captured(project)
    _refresh_robots_derived(project, captured)
    _rescan_legal_pages(project, captured)
    _join_cross_check(project, captured)
    failures = _load_failures(project)

    domains = set(project_domains(project)) | set(captured)
    unchecked = sorted(d for d in domains if d not in captured)
    return captured, unchecked, failures


def _date_cell(date, rec):
    """The `checked` cell: snapshot date, plus the Wayback marker for archived sites."""
    return _cell(date) + (
        f"<br>📦 Wayback {rec.get('archived_timestamp') or ''}"
        if rec.get("source") == "wayback"
        else ""
    )


def _header_lines(project, domains, captured, unchecked):
    """Report title, intro and counts — the lead-in before the two tables."""
    lines = [
        f"# {project} — compliance report\n",
        "Auto-generated **overview** of each domain's robots / licence / AI signals, from "
        "its latest `_audit/compliance/<org>/<date>/` snapshot. The 🔴/🟡/🟢/⚪ flags are an automated "
        "read of the live signals — a quick triage view, not a legal determination.\n",
        "Two **independent** questions, one table each:\n"
        "- **Crawl** — may we *fetch* the pages? (robots for our paths, an AI-bot scraping "
        "ban, anti-scraping ToS, crawl-delay)\n"
        "- **Reuse** — may we *store / republish* the content? (licence, plus AI-*reuse* "
        "reservations — TDMRep / noai / a no-AI-training clause; absent licence = default "
        "copyright, which says nothing about crawling)\n",
        "_Robots overlap is tested against representative paths the spider crawls "
        "(start_urls + one URL per allow-rule), for the UA our crawler actually sends, "
        "using a wildcard/`$`-aware matcher. `X-Robots-Tag` and the TDMRep HTTP headers "
        "(Tdm-Reservation/Policy) are probed best-effort via a separate stdlib request "
        "(no proxy/CF — a blocked probe is flagged, never read as 'open'). Licence "
        "detection covers the home page + linked legal pages only; ⚠ on a licence = "
        "low-confidence (bare CC link, no grant wording)._\n",
        f"**Domains:** {len(domains)}  ·  checked: {len(captured)}  ·  "
        f"not checked: {len(unchecked)}\n",
    ]
    return lines


def _failure_banner(failures):
    lines = []
    # ---- capture-failure banner (unreachable domains) — prominent, every run ----
    if failures:
        lines.append("> ‼️ **Compliance capture failed — needs investigation**\n>")
        for f in failures:
            lines.append(
                f">  - **{f.get('domain', '?')}** — {f.get('reason', 'unreachable')} "
                f"(first failed {f.get('first_failed', '?')}, last tried "
                f"{f.get('last_attempt', '?')})"
            )
        lines.append(
            ">\n> These are **skipped** on future audits until fixed — rerun "
            "`./scrapai audit --refresh` to retry.\n"
        )
    return lines


def _crawl_table(captured, unchecked, domains):
    """The Crawl table; also returns crawl_sorted (reused by the cross-check section)
    and crawl_flagged (the 🔴/🟡 rows the details section expands)."""
    # ---- CRAWL table ----
    crawl_sorted = sorted(
        (d for d in domains if d in captured),
        key=lambda d: (
            _color_rank(CRAWL_COLOR_ORDER, assess_crawl(captured[d][2])[1]),
            d,
        ),
    )
    lines = [
        "## Crawl — may we fetch the pages?\n",
        "**Verdict** (1st column): 🔴 **don't fetch** — robots blocks all the paths we'd "
        "crawl, or the ToS directly prohibits scraping · 🟡 **review** — robots blocks "
        "*some* paths, **an AI-bot scraping ban** (our UA isn't the blocked bot, but the "
        "site signals no-AI intent), disallows the PDFs we capture, or the overlap "
        "couldn't be tested · 🟢 **open** — nothing blocks our crawl.\n",
        "**Columns:**\n"
        "- **robots vs our paths** — of the representative URLs we'd actually crawl, how "
        "many robots.txt disallows for *our* user-agent. `✓ 0/7 blocked` = none of 7 "
        "tested are blocked; `⛔ 3/7 … blocked` = 3 are. (Domain links to its live robots.txt.)\n"
        "- **PDFs** — does robots disallow the article-linked PDFs we capture (`ok` / `⛔ blocked`).\n"
        "- **llms** — does the org publish an `/llms.txt` (an AI-friendly content-curation "
        "file). `✓` = present (click it to open the file), `⚠✗` = present but it *prohibits*, "
        "`—` = none.\n"
        "- **notes** — extra signals, shown **only when present** (blank = nothing notable):\n"
        "    - `AI-scrape blocked` — robots / ai.txt disallows AI crawlers\n"
        "    - `blocks PerplexityBot (your channel)` — blocks a bot our KB actually feeds\n"
        "    - `AI-reuse reserved (machine-readable)` — TDMRep / `noai` restricts AI *reuse*\n"
        "    - `no-AI-training (ToS, legal-only)` — a terms clause bars AI/ML training (not machine-readable)\n"
        "    - `crawl-delay Ns` — robots asks crawlers to wait N seconds between requests\n"
        "    - `robots-comment` — a robots.txt comment states a real **policy/contact** (an AI "
        "mention, an email, or a directed prohibition — not generic boilerplate; see the detail block)\n"
        "    - `ToS: /path` — that terms page directly prohibits scraping\n"
        "    - `*(via crawl)*` on the robots cell — the independent fetch was blocked, so the "
        "robots shown is the spider's own crawl-time capture (authoritative)\n"
        "    - `⚠ cross-check: robots/llms` — the spider's own crawl-time capture **disagrees** "
        "with this independent check (see the Cross-check section)\n",
        "_Every 🔴/🟡 row is expanded under **Crawl details** below with the exact wording._\n",
        "| | domain | checked | robots vs our paths | PDFs | llms | notes |",
        "|---|---|---|---|---|---|---|",
    ]
    crawl_flagged = []
    for dom in crawl_sorted:
        org, date, rec = captured[dom]
        tier, emoji, _ = assess_crawl(rec)
        # domain links to its robots.txt — the source behind the "robots vs our paths" cell
        lines.append(
            f"| {emoji} | [{dom}](https://{dom}/robots.txt) | {_date_cell(date, rec)} | "
            f"{crawl_robots_cell(rec)} | {crawl_pdf_cell(rec)} | {llms_cell(rec, dom)} | "
            f"{_cell(crawl_notes(rec))} |"
        )
        if tier >= 2:
            crawl_flagged.append((tier, org, dom, date, rec))
    for dom in unchecked:
        lines.append(
            f"| ❓ | [{dom}](https://{dom}/robots.txt) | **NOT CHECKED** | — | — | — | — |"
        )
    return lines, crawl_sorted, crawl_flagged


def _reuse_table(captured, unchecked, domains):
    """The Reuse table; also returns reuse_sorted (reused by the grants / bespoke /
    discrepancy sections)."""
    # ---- REUSE table ----
    reuse_sorted = sorted(
        (d for d in domains if d in captured),
        key=lambda d: (
            _color_rank(REUSE_COLOR_ORDER, assess_reuse(captured[d][2])[1]),
            d,
        ),
    )
    lines = [
        "\n## Reuse — may we store / republish the content?\n",
        "Rows run least-permissive → most-permissive. 🔎 **needs human review** — no "
        "licence found AND the site blocked our probe, so a licence may have been missed "
        "· ⚪ no explicit grant (default ©, permission needed) · 🟡 licence with conditions "
        "(NC/ND/SA), **or** a permissive licence found only on a sub-page (verify it "
        "covers the content you scrape, not just that page) · 🟢 permissive licence found "
        "on the home page.\n",
        "_The **© ARR** column flags an 'all rights reserved' notice — this is its own "
        "signal, NOT the licence: it's near-ubiquitous footer boilerplate and can sit "
        "alongside a CC grant, so it never decides the licence column._\n",
        "| | domain | checked | licence | found on | © ARR |",
        "|---|---|---|---|---|---|",
    ]
    for dom in reuse_sorted:
        org, date, rec = captured[dom]
        _, emoji, _ = assess_reuse(rec)
        # licence is PLAIN text; the clickable link is the SOURCE (the page it was read
        # from), so a reviewer can jump straight to the wording in context. A low-confidence
        # detection (bare CC link, no grant wording) gets a ⚠ marker.
        lic_cell = _cell(rec.get("license"))
        # ⚠ only on an actual GRANT (permissive/limited) detected with low confidence — not on
        # "all rights reserved"/unknown, where it's already ⚪ and the marker just adds noise.
        if rec.get("license_confidence") == "low" and license_class(
            rec.get("license")
        ) in ("permissive", "limited"):
            lic_cell += " ⚠"
        # no named licence but a bespoke (informal) grant — surface it, don't show a bare "—"
        elif rec.get("license") in (None, "unknown", "") and rec.get(
            "bespoke_permission"
        ):
            lic_cell = "bespoke grant"
        # for a 🔎 review row the licence/source cells are empty — say WHY in the source column
        found = (
            "🔎 **review** — probe blocked, licence unverified"
            if license_review_needed(rec)
            else license_source_link(rec, dom)
        )
        arr = "✓" if rec.get("all_rights_reserved") else "—"
        lines.append(
            f"| {emoji} | {dom} | {_date_cell(date, rec)} | {lic_cell} | {found} | {arr} |"
        )
    for dom in unchecked:
        lines.append(f"| ❓ | {dom} | **NOT CHECKED** | — | — | — |")
    return lines, reuse_sorted


def _grants_section(captured, reuse_sorted):
    lines = []
    # ---- licence grants: the exact wording behind each ACTUAL reuse grant (permissive or
    #      conditional). Excludes "all rights reserved" — that's not a grant. ----
    grants = [
        (d, captured[d][2])
        for d in reuse_sorted
        if captured[d][2].get("license_quote")
        and license_class(captured[d][2].get("license")) in ("permissive", "limited")
    ]
    if grants:
        lines.append("\n## Licence grants — the wording found\n")
        lines.append(
            "The sentence each licence was read from, in context. Confirm the grant "
            "covers the content you actually scrape (a CC link on a `/terms` page is "
            "not automatically a site-wide grant).\n"
        )
        for dom, rec in grants:
            lines.append(
                f"- **{dom}** — {_cell(rec.get('license'))} · "
                f"{license_source_link(rec, dom)}"
            )
            lines.append(f"  > {rec['license_quote']}")
    return lines


def _bespoke_section(captured, reuse_sorted):
    lines = []
    # ---- bespoke (non-named) reuse permissions ----
    bespoke_rows = [
        (d, captured[d][2])
        for d in reuse_sorted
        if captured[d][2].get("bespoke_permission")
        and license_class(captured[d][2].get("license"))
        not in ("permissive", "limited")
    ]
    if bespoke_rows:
        lines.append("\n## Bespoke reuse permissions — non-licence grants\n")
        lines.append(
            "Directed permission wording that is NOT a named CC/OGL licence (e.g. "
            "'may be reproduced for non-commercial use with attribution'). Verify it "
            "covers the content you actually scrape.\n"
        )
        for dom, rec in bespoke_rows:
            lines.append(f"- **{dom}** — “{_cell(rec['bespoke_permission'])}”")
    return lines


def _discrepancies_section(captured, reuse_sorted):
    lines = []
    # ---- copyright discrepancies (homepage vs a legal page disagree on the holder) ----
    disc_rows = [
        (d, captured[d][2])
        for d in reuse_sorted
        if captured[d][2].get("copyright_discrepancy")
    ]
    if disc_rows:
        lines.append("\n## Copyright discrepancies — pages disagree\n")
        lines.append(
            "The homepage and a legal page name different rights-holders. Record both.\n"
        )
        for dom, rec in disc_rows:
            lines.append(f"- **{dom}**:")
            for c in rec["copyright_discrepancy"].get("claims", []):
                lines.append(
                    f"  - _{_cell(c.get('source'))}_: {_cell(c.get('statement'))}"
                )
    return lines


def _cross_check_section(captured, crawl_sorted):
    lines = []

    # ---- cross-check: crawl-capture vs independent ----
    def _xc(d):
        return captured[d][2].get("_cross_check") or {}

    xc_rows = [
        (d, captured[d][2])
        for d in crawl_sorted
        if _xc(d).get("conflict_kinds") or _xc(d).get("legal", {}).get("gap")
    ]
    rescued = [
        (d, captured[d][2])
        for d in crawl_sorted
        if _xc(d).get("robots", {}).get("state") == "rescued"
    ]
    if xc_rows or rescued:
        lines.append("\n## Cross-check — crawl-time vs independent\n")
        lines.append(
            "The spider's crawl-time capture is the authoritative witness. A ⚠ "
            "conflict is raised **only** when the scrape **missed** something the "
            "independent probe found, or the two **directly contradict** — the reverse "
            "(the crawl captured a file the probe couldn't reach) is *not* a problem "
            "and isn't flagged. A legal-page gap is informational. `✓ rescued` = the "
            "probe was blocked but the crawl captured the file, so the crawl value is used.\n"
        )
        for dom, rec in xc_rows:
            xc = rec["_cross_check"]
            lg = xc.get("legal", {})
            kinds = list(xc.get("conflict_kinds", []))
            if lg.get("gap"):
                kinds.append("legal-gap")
            lines.append(
                f"- **{dom}** — {'⚠ ' if xc.get('conflict_kinds') else ''}"
                + ", ".join(kinds)
            )
            rbx = xc.get("robots", {})
            if rbx.get("state") == "conflict":
                if rbx.get("crawl_only"):
                    lines.append(
                        f"  - robots — only in CRAWL capture ({rbx.get('crawl_date', '?')}): "
                        + ", ".join(f"`{x}`" for x in rbx["crawl_only"])
                    )
                if rbx.get("independent_only"):
                    lines.append(
                        "  - robots — only in INDEPENDENT check: "
                        + ", ".join(f"`{x}`" for x in rbx["independent_only"])
                    )
            if "llms" in xc.get("conflict_kinds", []):
                lines.append(
                    "  - llms.txt — "
                    + (xc.get("llms", {}).get("reason") or "crawl/probe mismatch")
                )
            if lg.get("missed_substantive"):
                lines.append(
                    "  - terms/licence page(s) the INDEPENDENT check found but the "
                    "spider MISSED: " + ", ".join(lg["missed_substantive"])
                )
        for dom, rec in rescued:
            rbx = rec["_cross_check"]["robots"]
            lines.append(
                f"- **{dom}** — ✓ rescued: independent robots fetch blocked; using the "
                f"crawl-captured robots ({rbx.get('crawl_date', '?')})."
            )
    return lines


def _crawl_details_section(project, crawl_flagged):
    lines = []
    # ---- crawl detail blocks ----
    if crawl_flagged:
        lines.append("\n## Crawl details — rows needing review\n")
        lines.append(
            "Expanded for every 🔴/🟡 crawl row: which of *our* paths robots blocks, "
            "AI signals, and any directed anti-scraping clause.\n"
        )
        for _, org, dom, date, rec in sorted(
            crawl_flagged, key=lambda x: (-x[0], x[2])
        ):
            lines.append(crawl_detail_block(project, org, dom, date, rec))
    return lines


def write_report(project, data=None):
    """Project-level rollup of every org's LATEST compliance snapshot → a standalone file
    in the audit FOLDER. Two independent axes: a CRAWL table (may we fetch?) and a REUSE
    table (may we republish?), each sorted most-restrictive-first.

    `data` — an already-computed build_report_data() triple, so a caller that also
    builds the dashboard (the audit) loads + refines the snapshots ONCE instead of
    once per consumer. Default: compute here."""
    out_dir = os.path.join(DATA_DIR, project, "_audit")
    os.makedirs(out_dir, exist_ok=True)
    captured, unchecked, failures = (
        data if data is not None else build_report_data(project)
    )
    domains = set(captured) | set(unchecked)  # all in-scope domains
    lines = _header_lines(project, domains, captured, unchecked)
    lines += _failure_banner(failures)
    crawl_lines, crawl_sorted, crawl_flagged = _crawl_table(
        captured, unchecked, domains
    )
    lines += crawl_lines
    reuse_lines, reuse_sorted = _reuse_table(captured, unchecked, domains)
    lines += reuse_lines
    lines += _grants_section(captured, reuse_sorted)
    lines += _bespoke_section(captured, reuse_sorted)
    lines += _discrepancies_section(captured, reuse_sorted)
    lines += _cross_check_section(captured, crawl_sorted)
    lines += _crawl_details_section(project, crawl_flagged)

    path = os.path.join(out_dir, f"compliance_{project}.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return path
