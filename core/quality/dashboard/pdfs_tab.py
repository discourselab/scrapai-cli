"""The PDFs tab — external-PDF hosts grouped by organisation, the ☁ storage-host signal,
seeded URL sampling, and the per-project host-exclusion feature (pdf_exclude.json — a
read-only projection; the markdown report and crawl data are never touched)."""

import glob
import json
import os
import random
import re

from core.quality._env import DATA_DIR

from .widgets import COLUMN_DEFS, _esc, _tip

# --------------------------------------------------------------------------- PDFs tab
_PDF_URL_SAMPLE = (
    5  # URLs kept per host — a SEEDED (reproducible) random sample. The `links`
)
#                         count is the triage signal; the URLs just let you eyeball the kind of PDF.
_PDF_SHARE_FLOOR = (
    0.1  # render floor (%): hosts below this share of an org's PDFs aren't rendered
)
#                         (keeps big orgs light); the slider gates the rest, default 0.5%.

# Cloud-storage / CDN hosts — a strong "org's OWN document store" signal regardless of link count
# (an org self-hosting PDFs gives each a unique URL, so its store can show even at count 1).
_STORAGE_RE = re.compile(
    r"(?:amazonaws\.com|cloudfront\.net|core\.windows\.net|storage\.googleapis\.com|"
    r"digitaloceanspaces\.com|b-cdn\.net|akamai\w*\.net|fastly\.net|cloudinary\.com|"
    r"rackcdn\.com|awsassets\.|\.blob\.)|^(?:files|assets|cdn|media|downloads|static|dam|docs|s3)\.",
    re.I,
)


def _is_storage_host(host):
    return bool(host) and bool(_STORAGE_RE.search(host))


# --- per-project host exclusions (PDFs tab) ----------------------------------
# A project may hide out-of-scope external PDF hosts from the tab via
# data/<project>/_audit/pdf_exclude.json. The tab exists to surface external hosts of
# each org's OWN documents, so government sites, other big orgs, and the sibling orgs
# already covered by their own spider are noise. This is a READ-ONLY projection: the
# markdown report and crawl data are untouched — the dashboard just hides these rows
# (with a toggle to reveal them). The matching is done in JS (seeded from this file), so
# hosts added live from the tab apply immediately; Python only reads the file and embeds
# the config. Absent file ⇒ no exclusions (the feature is opt-in per project).


def _pdf_exclude_instructions(project):
    """The `_instructions` header written into a scaffolded pdf_exclude.json — same guidance as a
    hand-written one, with the project's own re-run command spelled out."""
    return (
        "Hosts to HIDE from the PDFs tab of the audit dashboard for this project. The tab's job is "
        "to surface external hosts of each org's OWN report PDFs (e.g. an org self-hosting on a "
        "CDN/S3); citations to government sites, other big organisations, and the sibling orgs "
        "already covered by their own spider are noise. This file is READ-ONLY over your data: the "
        "crawl JSONL and external_pdf_report.md are never touched — only the dashboard view hides "
        "these rows, and a 'show excluded' toggle reveals them. Matching is dot-boundary suffix: "
        "'unep.org' hides unep.org AND wedocs.unep.org, but not 'notunep.org'. 'block_tlds' hides "
        "any host whose final DNS label matches (e.g. 'gov' hides every *.gov). "
        "'exclude_sibling_org_domains' also hides, per org, the own-domains of every OTHER org in "
        "this project (derived from each spider's allowed_domains). This file was scaffolded empty; "
        f"fill in the lists and re-run `./scrapai audit --project {project}` to apply. You can also "
        "add domains live from the dashboard's PDFs tab and paste them back here."
    )


def _ensure_pdf_exclude(project):
    """Scaffold an inert pdf_exclude.json (empty lists, sibling exclusion OFF) the first time a
    project is audited, so every project starts from the same editable layout. NEVER overwrites an
    existing file — a real config the user wrote is left exactly as-is. An empty template filters
    nothing, so behaviour is unchanged until someone edits it."""
    if not project:
        return
    path = os.path.join(DATA_DIR, project, "_audit", "pdf_exclude.json")
    if os.path.exists(path):
        return
    template = {
        "_instructions": _pdf_exclude_instructions(project),
        "domains": [],
        "block_tlds": [],
        "exclude_sibling_org_domains": False,
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(template, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError:
        pass  # scaffolding is best-effort, never fatal


def _load_pdf_exclude(project):
    """(domains, tlds, sibling_on) from pdf_exclude.json, or ([], set(), False) if absent/bad."""
    if not project:
        return [], set(), False
    path = os.path.join(DATA_DIR, project, "_audit", "pdf_exclude.json")
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return [], set(), False
    domains = [
        d.strip().lower().lstrip(".")
        for d in cfg.get("domains", [])
        if isinstance(d, str) and d.strip()
    ]
    tlds = {
        t.strip().lower().lstrip(".")
        for t in cfg.get("block_tlds", [])
        if isinstance(t, str) and t.strip()
    }
    return domains, tlds, bool(cfg.get("exclude_sibling_org_domains"))


def _project_own_domains(project):
    """{spider: [own domain, ...]} from each spider's final_spider.json allowed_domains — the
    basis for per-org sibling exclusion (an org's PDF on another org's domain is that org's job).
    A leading www. is stripped so the dot-boundary match also covers the bare domain."""
    out = {}
    if not project:
        return out
    for path in glob.glob(
        os.path.join(DATA_DIR, project, "*", "analysis", "final_spider.json")
    ):
        spider = path.split(os.sep)[-3]
        try:
            with open(path, encoding="utf-8") as fh:
                ad = json.load(fh).get("allowed_domains") or []
        except (OSError, ValueError):
            continue
        doms = sorted(
            {
                (d[4:] if d.lower().startswith("www.") else d).strip().lower()
                for d in ad
                if isinstance(d, str) and d.strip()
            }
        )
        if doms:
            out[spider] = doms
    return out


def _pdf_exclude_config(project):
    """The exclusion config embedded (as a JSON island) for the JS matcher: the file's `domains`
    / `block_tlds` plus a {sibling-domain: owning-spider} map when sibling exclusion is on. `raw`
    is the file verbatim (or {}), so a live-add can rebuild the whole file for copy/download.
    """
    domains, tlds, sib_on = _load_pdf_exclude(project)
    raw = {}
    if project:
        try:
            with open(
                os.path.join(DATA_DIR, project, "_audit", "pdf_exclude.json"),
                encoding="utf-8",
            ) as fh:
                loaded = json.load(fh)
            raw = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            raw = {}
    siblings = {}
    if sib_on:
        for owner, doms in _project_own_domains(project).items():
            for d in doms:
                siblings.setdefault(
                    d, owner
                )  # first owner wins if two spiders share a domain
    return {
        "domains": domains,
        "block_tlds": sorted(tlds),
        "exclude_sibling_org_domains": sib_on,
        "siblings": siblings,
        "raw": raw,
    }


def _pdf_config_blob(cfg):
    """Embed the exclusion config as a JSON island the JS matcher reads once. Escaped so no
    `</script>` in a file-supplied value can break out (belt-and-braces; source is local).
    """
    payload = (
        json.dumps(cfg, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f'<script type="application/json" id="pdf-exclude">{payload}</script>'


def _pdf_exclude_infobox(project, cfg):
    """The explainer + live exclusion manager shown under the PDFs table. Server renders the
    skeleton only; the chip lists and count are filled by JS from the #pdf-exclude island (so a
    live add re-renders them without a page rebuild). Rendered whenever the project has a
    pdf_exclude.json — always, once the audit scaffolds the template — because the box hosts
    the live-add UI (the count simply shows 0 when nothing is active); only a project with no
    file at all gets no box."""
    active = bool(cfg.get("domains") or cfg.get("block_tlds") or cfg.get("siblings"))
    if not active and not cfg.get("raw"):
        return ""
    proj = _esc(project or "")
    return (
        f'<div class="pdf-info" data-project="{proj}">'
        '<details class="pdf-expanel"><summary>'
        '<span class="pdf-ex-count">0</span> host exclusions active '
        '<span class="sub">— why some hosts are hidden from this tab, and how to change it</span>'
        '</summary><div class="pdf-exbody">'
        '<p class="sub">This tab exists to surface the external hosts of each org’s <b>own</b> report '
        "PDFs (e.g. an org self-hosting on a CDN/S3). Citations to government sites, big multilateral "
        "orgs, and the sibling orgs already covered by their own spider are hidden so they don’t drown "
        "the signal. Matching is dot-boundary suffix (<code>unep.org</code> also hides "
        "<code>wedocs.unep.org</code>). Nothing is deleted — the crawl data and "
        "<code>external_pdf_report.md</code> are untouched, and the <b>show excluded hosts</b> toggle "
        "above reveals what’s hidden.</p>"
        '<div class="pdf-exsec"><b>Government TLDs</b> '
        '<span class="sub">— any host whose final label matches</span>'
        '<div class="pdf-ex-tlds chips"></div></div>'
        '<div class="pdf-exsec"><b>Excluded organisations</b> '
        '<span class="sub">— big orgs / multilaterals out of scope for an advocacy KB</span>'
        '<div class="pdf-ex-domains chips"></div></div>'
        '<div class="pdf-exsec pdf-ex-sibwrap"><b>Sibling orgs in this project</b> '
        '<span class="sub">— auto: each is covered by its own spider, so no duplicate hosts</span>'
        '<div class="pdf-ex-siblings chips"></div></div>'
        '<div class="pdf-addrow">'
        '<input class="pdf-add" placeholder="add a domain (worldbank.org) or a TLD (tld:gov)" '
        'aria-label="add an exclusion">'
        '<button class="pdf-add-btn" type="button">add</button>'
        '<span class="pdf-add-msg sub"></span></div>'
        '<div class="pdf-savebox" hidden>'
        f'<p class="sub">You added exclusions in-page. To make them permanent, paste this into '
        f"<code>data/{proj}/_audit/pdf_exclude.json</code> and re-run "
        f"<code>./scrapai audit --project {proj}</code>:</p>"
        '<pre class="pdf-savejson mono"></pre>'
        '<button class="dl pdf-copy-json" type="button">copy JSON</button>'
        '<button class="dl pdf-dl-json" type="button">download pdf_exclude.json</button>'
        "</div></div></details></div>"
    )


def _sample_urls(urls, seed):
    """A small, SEEDED-random, stable-ordered sample of a host's URLs — deterministic (same seed
    ⇒ same sample every build), so the output is reproducible and the embedded blob stays tiny.
    """
    urls = list(urls or [])
    if len(urls) <= _PDF_URL_SAMPLE:
        return sorted(urls)
    return sorted(random.Random(seed).sample(urls, _PDF_URL_SAMPLE))


def _pdf_detail_placeholder(n_shown, n_total):
    """An EMPTY detail — the ≤5 sample links are built lazily on first expand (buildPdfDetail in
    _JS) from the `#pdf-urls` JSON blob, so no link nodes sit in the initial DOM."""
    note = f" — random sample of {n_total}" if n_total > n_shown else ""
    return (
        f'<div class="pdfurls" data-n="{n_shown}"></div>'
        f'<span class="sub">{n_shown} URLs{note}</span> '
        f'<button class="copyurls" type="button">copy</button>'
    )


def _pdf_json_blob(urlmap):
    """Embed per-host URL lists as one JSON island parsed once on demand (not rendered). Escaped
    so no `</script>`/tag can break out (site-derived URLs are untrusted)."""
    payload = (
        json.dumps(urlmap, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f'<script type="application/json" id="pdf-urls">{payload}</script>'


def _pdf_table(pdf_spiders, project=None):
    exc_cfg = _pdf_exclude_config(project)
    # Group by ORGANISATION (spider) — one collapsible section each, orgs ordered by total links
    # (a heavy host is likely the org's own repository). Within an org, hosts by link count.
    groups = []
    for s in pdf_spiders or []:
        hosts = [h for h in s.get("hosts", [])]
        if not hosts:
            continue
        total = sum(h.get("count", 0) for h in hosts)
        groups.append((s.get("spider", ""), total, hosts, s.get("own_unique", 0)))
    if not groups:
        return '<p class="empty">No external PDF links recorded for this project.</p>'
    groups.sort(key=lambda g: -g[1])
    body = []
    urlmap = {}  # rid -> full URL list (emitted once as a JSON island, built on expand)
    rc = 0
    for spider, total, hosts, own_unique in groups:
        gid = _esc(spider)
        # One filter: a host's SHARE of the org's PDFs. Render only hosts above a small floor (keeps
        # big orgs light + small orgs complete); the slider then gates the display. Sort by count.
        shown = [
            h
            for h in sorted(hosts, key=lambda x: -x.get("count", 0))
            if total and 100 * h.get("count", 0) / total >= _PDF_SHARE_FLOOR
        ]
        if not shown:
            continue
        body.append(
            f'<tr class="fx-group" data-group="{gid}">'
            f'<td colspan="3"><span class="caret">▸</span> <b class="mono">{_esc(spider)}</b> '
            f'<span class="sub">· {total} links · {len(shown)} hosts'
            + (f" · {own_unique} same-org PDFs" if own_unique else "")
            + "</span>"
            f'<span class="exc-note sub" data-group="{gid}"></span></td></tr>'
        )
        for h in shown:
            hhost, n = h.get("host", ""), h.get("count", 0)
            urls = h.get("urls", []) or []
            rid = f"p{rc}"
            rc += 1
            share = (
                round(100 * n / total, 2) if total else 0
            )  # this host's % of the org's PDFs
            tip_storage = _tip(
                "Cloud storage / CDN host (e.g. S3, CloudFront, Azure blob, a "
                "files./cdn. subdomain) — sometimes an org's OWN document store, "
                "worth a look."
            )
            badge = (
                f'<span class="stor" {tip_storage}>☁ storage</span> '
                if _is_storage_host(hhost)
                else ""
            )
            expandable = len(urls) > 1
            caret = ' <span class="caret">▸</span>' if expandable else ""
            sampled = _sample_urls(urls, hhost) if expandable else []
            if expandable:
                urlmap[rid] = sampled
            body.append(
                f'<tr class="fx-row" data-id="{rid}" data-group="{gid}" data-share="{share}" '
                f'data-name="{_esc(spider + " " + hhost)}" data-spider="{_esc(spider)}" '
                f'data-host="{_esc(hhost)}">'
                f'<td class="sel"><input type="checkbox" class="fx-check" aria-label="include {_esc(hhost)}"></td>'
                f'<td class="mono" data-key="{_esc(hhost.lower())}">{badge}{_esc(hhost)}{caret}'
                f' <span class="sub">{share}%</span><span class="excb"></span></td>'
                f'<td class="r" data-key="{n}">{n}</td>'
                f"</tr>"
                + (
                    f'<tr class="fx-detail" data-id="{rid}" data-group="{gid}" hidden><td colspan="3">'
                    f"{_pdf_detail_placeholder(len(sampled), len(urls))}</td></tr>"
                    if expandable
                    else ""
                )
            )
    facetbar = (
        '<div class="fx-facets" data-for="pdfs">'
        '<label class="sharectl">show hosts ≥ '
        '<input type="range" class="pdf-share" min="0.1" max="5" step="0.1" value="0.5" '
        'aria-label="minimum share of the org\'s PDFs"> '
        '<b class="pdf-share-val">0.5%</b> of the org’s PDFs</label>'
        '<span class="pdf-shown sub"></span>'
        '<label class="att excctl"><input type="checkbox" class="pdf-showexc"> '
        "show excluded hosts</label>"
        '<input class="fx-search" placeholder="filter org / host…" aria-label="filter">'
        '<button class="clear" type="button">clear</button></div>'
    )
    hint = (
        '<p class="tabintro"><b>This tab finds an organisation’s documents stored outside its '
        "own website.</b> While crawling, every PDF link is recorded (nothing is downloaded). "
        "PDFs on the org’s own domain are only a count in its group header — the table below "
        "lists the PDFs hosted on <b>other</b> domains, grouped by the organisation whose pages "
        "link to them, most-linked first. Why this matters: many organisations keep their "
        "reports in an external store (a cloud bucket, a CDN, a second domain) — a host holding "
        "a large share of an org’s PDFs is probably that store, while a host linked once or "
        "twice is usually just a citation to someone else’s document. Drag the slider to hide "
        "those one-offs. A blue <b>☁ storage</b> tag marks known cloud-storage / CDN hosts — "
        "often an org’s own store in disguise. Tick the hosts you want included, and click a "
        "host to see a sample of its PDF URLs.</p>"
    )
    tip_host = _tip(
        "The external domain that hosts the linked PDFs. Click a row to see a "
        "random sample of its PDF URLs."
    )
    head = (
        '<tr><th class="sel">✓</th>'
        f"<th {tip_host}>host</th>"
        f'<th class="r" {_tip(COLUMN_DEFS["links"])}>links</th></tr>'
    )
    return (
        hint
        + facetbar
        + f'<table class="fx-table" data-tab="pdfs"><thead>{head}</thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
        + _pdf_exclude_infobox(project, exc_cfg)
        + _pdf_json_blob(urlmap)
        + _pdf_config_blob(exc_cfg)
    )
