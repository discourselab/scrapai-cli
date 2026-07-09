"""All human-facing prose: the status legend, per-status fix guidance, the
review-config instruction strings, and the report's big static paragraphs."""

from .scoring import LIVENESS_FLAG_BELOW, STALE_DAYS, THIN_CHARS

# Self-documenting `_instructions` written into each project's _audit/ config and kept
# current on every audit run (your entries are never touched). The `_instructions` key
# (and any `_`-prefixed key) is ignored by the loaders, so it's safe in-file docs that
# live right where you edit the data.
_NOTES_INSTRUCTIONS = (
    'Manual review notes for THIS project, keyed by spider name. Shape: {"status": '
    '"ok" | "discard", "flag": "<short flag(s) shown in the report>", "note": '
    '"<concise explanation>", "note_long": "<optional fuller detail>", '
    '"updated": "YYYY-MM-DD"}. The `status` key is the ONLY thing that changes the '
    "report; a note with NO `status` is inert (documentation/draft — it changes neither "
    'status nor flags). status "ok" promotes the row to `ok` and shows `✓ reviewed: '
    "<flag>` (which REPLACES the auto-flags that prompted review; an already-ok spider "
    "stays ok and just gains the tag; a spider with broken extraction is NOT promoted — it "
    "shows `⚠ reviewed-stale` so a note can't claim empty content is fine, but `incomplete` "
    "(a coverage shortfall) CAN be promoted by a reviewed note vouching it's a false positive). status "
    '"discard" moves it to the `discarded` group with `🗑 discard: <flag>`. (Legacy '
    '`"discard": true` still works as status "discard".) Whenever `status` is set a '
    "`flag` is REQUIRED and must be genuinely short — the 1-2 most central points only, "
    "NOT a summary of the note; everything else belongs in `note`/`note_long`. The flag "
    "must add NEW information: state WHAT you verified and the OUTCOME, not the symptom that "
    "triggered review. Keep it HIGH-LEVEL and qualitative — NO volatile per-crawl numbers "
    "(item/row counts, percentages, dup rates) that go stale on the next crawl; describe the "
    "outcome in words, e.g. 'real articles only (non-content pruned)' NOT '1768 articles, "
    "100% coverage'. DO include the corpus coverage year-span when known and meaningful "
    "(e.g. 'all years covered (2017-2026)') — a stable scope descriptor, not a volatile "
    "count. NEVER restate anything already visible elsewhere in the report — the "
    "sitemap column already shows sitemap state, so don't write 'no sitemap'/'sitemap "
    "ignored'; and WHY a sitemap was ignored lives in audit_sitemap_skip.json, so don't "
    "repeat it here. Prefer the positive finding, e.g. 'all years covered (2017-2026)' or "
    "'thin but complete', NOT 'no news sitemap, coverage checked manually'. `note` is "
    "BRIEF — roughly one short clause per auto-flag, mapping the symptom to why it's fine "
    "(e.g. 'thin? -> genuinely short posts', 'sitemap-drift -> nav-only sitemap, real "
    "content is X'). Address ONLY the flags that triggered review; do NOT retell the whole "
    "story here. Everything else — fuller detail, background, caveats, known limitations, "
    "maintenance/commands — goes in `note_long`. Rule of thumb: if `note` runs past ~2 "
    "sentences, move the overflow into `note_long`. Put dates only in the `updated` field, "
    "not in the note text. `note`/`note_long` are file-only — never "
    "rendered; only `flag` is. Keys starting with _ are ignored. Auto-created if missing; "
    "this `_instructions` line is refreshed automatically on each audit run, but your "
    "entries are never touched. AI agents: you may SUGGEST entries (status + flag + "
    "note) when reviewing the audit, but must get explicit user approval before writing "
    "any — never auto-add them during bulk analysis. These are human review records."
)
_SKIP_INSTRUCTIONS = (
    "Spiders whose auto-discovered sitemap the audit must IGNORE — never probe it or "
    "use it as the coverage denominator. Each entry is keyed by spider name -> "
    '{"reason": "<why it\'s the wrong yardstick: nav-only, malformed, or excludes the '
    'real content>", "updated": "YYYY-MM-DD"}. (A bare reason string is still '
    "accepted, but please use the object form and add the date.) Only the `reason` is "
    "shown in the report (on the `ignored` row); `updated` is file-only. Keys starting "
    "with _ are ignored. Auto-created if missing; this `_instructions` line is refreshed "
    "automatically on each audit run, but your skip entries are never touched. AI agents: "
    "you may SUGGEST a skip entry (reason + date) when reviewing the audit, but must get "
    "explicit user approval before writing it — never auto-add during bulk analysis. "
    "These are human review records."
)


# ordered legend: (label, definition) — FOUR groups, one per solution family. Within-group
# nuance lives in the `flags` column (see Notes & definitions). Hoisted to module scope so the
# HTML dashboard's status tooltips render the SAME text as the MD report (single source, no drift).
# Stored as (label, lead, rest) triples — `lead` is the bolded opening (the action),
# `rest` the remainder — and rebuilt below into the exact (label, definition) 2-tuples
# every consumer has always seen.
_LEGEND_PARTS = [
    (
        "extraction broken",
        "Fix: selectors.",
        "HTML pages were reached but came back empty — content < 70% (or < 30% on a small <20-page crawl); "
        "FIELDS/selectors are wrong, or the empties are CF-challenge/blank pages (check `analysis/NOTES.md`). Judged "
        "over HTML rows only — harvested PDF rows never count as empty pages.",
    ),
    (
        "too few pages",
        "Fix: run a full crawl (or confirm it's a small site).",
        "Too little output to judge completeness — `never-ran` (0 pages, no crawl-stats: no production crawl; "
        "`--limit` test crawls write DB-only so this also covers spiders only tested at creation), `ran-empty` (0 "
        "pages but crawl-stats present: it DID run and came back empty — investigate, don't just re-run; check "
        "`liveness`/`eligible` and `analysis/NOTES.md`), or `small/partial` (a small or stalled *production* crawl "
        "with no sitemap to verify against — could be a small site); `pdf-only (N)` = no HTML articles but N PDF "
        "links harvested — likely a document-repository site.",
    ),
    (
        "incomplete",
        "Investigate why it stalled, then re-crawl (`/spider-review`).",
        "It ran but fell short — verified coverage < 90% (see `coverage`) or the DeltaFetch cache holds far more "
        "than the output (flag `deltafetch-stale` → `--reset-deltafetch`). Diagnose the cause FIRST (rate-limit / "
        "dead proxy / too-narrow scope / a deny rule) — a blind re-crawl just repeats the shortfall; use "
        "`/spider-review` to find and fix it, then re-crawl.",
    ),
    (
        "manual review",
        "Review it carefully (`/spider-review`), then record the verdict.",
        "Extraction works and it ran, but a concern flag means it's not auto-clean — coverage can't be verified "
        "(`no-sitemap` / `sitemap-empty` / `sitemap-drift` / `sitemap-cap-hit`), content looks `thin?`, or "
        "`liveness` is low. This is NOT a quick glance — run the evidence-based `/spider-review` process (a bounded "
        "verification crawl, a ground-truth count check against the site's own totals, and coverage / temporal / "
        "PDF-URL checks) to decide whether it's a genuine problem or actually fine. If fine, record it with "
        '`"status": "ok"` + a short `flag` in this project\'s `_audit/audit_notes.json` and it promotes to `ok` '
        "with `✓ reviewed`. (A note without a `status` is inert — it won't change the row.)",
    ),
    (
        "ok",
        "No action.",
        "Extraction works and coverage is verified against the sitemap. A clean row here has an empty `flags` column "
        '— except rows flagged `✓ reviewed`, which a human set `"status": "ok"` on in `audit_notes.json` (full note '
        "+ date in that file) rather than auto-verified.",
    ),
    (
        "discarded",
        "Ignore — deliberately dropped.",
        'A human set `"status": "discard"` (or legacy `"discard": true`) on this source in `audit_notes.json` (e.g. '
        "duplicate, out of scope, dead). Never set automatically; the `🗑 discard` flag carries the short reason and "
        "the full note is in the file.",
    ),
]

LEGEND = [(label, f"**{lead}** {rest}") for label, lead, rest in _LEGEND_PARTS]

# just the bolded action per status, markdown stripped — for compact UI surfaces
STATUS_LEADS = {label: lead.replace("`", "") for label, lead, _ in _LEGEND_PARTS}


def fix_hints(project):
    """Per-status 'how to fix' guidance keyed by status label. A function (not a constant)
    because the text interpolates the project name. Shared by the MD report's per-group tables
    and the dashboard's contextual fix-hint banner, so the two never disagree."""
    return {
        "extraction broken": "**→ How to fix:** pages were reached but came back empty — the content selector is "
        "wrong (or the pages are blank / challenge pages).\n\n"
        "- Re-inspect a sample page: `./scrapai analyze <cached.html>` or `./scrapai inspect <url>`.\n"
        "- Fix the `content` / `FIELD_EXTRACT` selector in `final_spider.json`, re-import "
        f"(`./scrapai spiders import final_spider.json --project {project}`), and re-test with `--limit 5`.\n"
        "- If the empties are CF-challenge / blank pages (not a selector bug), see the spider's "
        "`analysis/NOTES.md` — likely a proxy / block issue.\n"
        "- Or let `/spider-review` diagnose it and propose the fix.",
        "too few pages": "**→ How to fix:** too little output to judge — first work out which case it is, then act.\n\n"
        "- `never-ran` = no production crawl yet (`--limit` test crawls don't write JSONL) → run the "
        f"full crawl: `./scrapai crawl --project {project} <spider>`.\n"
        "- `ran-empty` = it already ran but produced 0 output — re-running won't help; investigate "
        "(`eligible` 0 = allow-rules match no sitemap URLs · low `liveness` = blocked / 403 · else "
        "dropped items — see `analysis/NOTES.md`).\n"
        "- `pdf-only (N)` = the crawl harvested only PDF links — a document repository. "
        "Confirm the site's content really is documents, then record an `audit_notes.json` "
        "review note (`status: ok`).\n"
        "- `small/partial` = a small or stalled run — confirm it isn't just a small site; if stalled, "
        "look for 403 / proxy blocks.",
        "incomplete": "**→ How to fix:** investigate the shortfall FIRST — a blind re-crawl just repeats it.\n\n"
        "- Diagnose with `/spider-review`: a low `coverage` % is usually rate-limiting / a dead proxy "
        "(look for 403s + TunnelError), too-narrow scope, or a deny rule — see the spider's "
        "`analysis/NOTES.md`.\n"
        f"- Then re-crawl: `./scrapai crawl --project {project} <spider>` (add `--reset-deltafetch` if "
        "flagged `deltafetch-stale`).",
        "manual review": "**→ How to review:** a concern flag needs a careful, evidence-based review — the "
        "`/spider-review` process (a bounded verification crawl + a ground-truth count check), not a "
        "quick glance.\n\n"
        f"- Run `/spider-review {project} <spider>`, or start manually with "
        f"`./scrapai show --project {project} --limit 5 <spider>`.\n"
        "- The flag says why: coverage can't be verified (no / empty / drifting sitemap — `sitemap-empty` "
        "on a CF site may be a block; `found` spiders are candidates for `USE_SITEMAP`), content looks "
        "`thin?` (over-broad rules?), or `liveness` is low.\n"
        "- If it's actually fine, record it in `_audit/audit_notes.json` (`status: ok` + `flag` + `note` "
        "+ `updated`) → it promotes to `ok` with `✓ reviewed`. Without a `status` the note is inert.",
    }


# ---- big static report paragraphs (written verbatim by report.py) ----------------
AGENTS_PREAMBLE = (
    "> 🤖 **For AI agents reviewing this audit:** you may *suggest* "
    "`audit_notes.json` review notes and `audit_sitemap_skip.json` entries, "
    "but you may NOT write them yourself — not even while bulk-analysing or "
    "fixing spiders. These are **human review records**: propose the entry "
    "(status + flag + note) and the reasoning, then wait for explicit user "
    "approval before adding it. Fixing a spider's config/JSON is fine; "
    "recording a review verdict is the human's call.\n\n"
)

GOAL = (
    "**The goal: every spider ends up in `ok` (or deliberately `discarded`).** "
    "The status groups below are a worklist, worst-first; each names the ONE "
    "action that moves its spiders toward `ok` — fix + re-crawl for the defect "
    "groups, a careful human review for the judgment groups. Review verdicts "
    "live in two files (both suggest-only for agents): "
    "`_audit/audit_sitemap_skip.json` corrects the *yardstick* BEFORE scoring "
    "(ignore a sitemap that is the wrong coverage denominator — nav-only, "
    "malformed, excludes the real content), while `_audit/audit_notes.json` "
    "records the *verdict* AFTER scoring (`status: ok` promotes a reviewed row, "
    "`status: discard` retires it). The audit is done when every row sits in "
    "`ok`/`discarded` and the flags column carries only `✓ reviewed` tags.\n\n"
)

FETCH_MODES_NOTE = (
    "By default sitemaps are fetched only where none is cached yet "
    "(sites already confirmed to have no sitemap aren't re-probed, and "
    "sitemaps recorded during the crawl are never fetched). Add "
    "**`--no-fetch`** to suppress sitemap fetching entirely (cache only), "
    "or **`--fetch-all`** to re-fetch every sitemap (refresh the cache).\n\n"
)

DUPES_EXPLAINER = (
    "**true dupes** = rows with the same URL **and** identical "
    "content (re-run artifacts — what the default dedupe removes). "
    "**versions** = same URL but *changed* content (genuine history "
    "from re-fetching updated pages — default dedupe **keeps** "
    "these; only `--latest-only` drops them). Neither affects the "
    "`scraped`/`coverage` numbers elsewhere (those use unique "
    "URLs).\n\n"
)

DUPES_CAUSE = (
    "\n**Cause.** Re-running a crawl with `--reset-deltafetch` clears the "
    "dedup cache but the date-named `crawl_DDMMYYYY.jsonl` is opened in "
    "*append* mode, so each re-run appends another full copy.\n\n"
)

DEDUPE_FIX = (
    "**Fix — `./scrapai dedupe`** consolidates each spider's "
    "`crawls/*.jsonl` into one file (originals kept as `*.superseded`, so "
    "it's reversible). It writes immediately. The default dedupes on "
    "**URL+content** (collapses identical re-scrapes, keeps "
    "genuinely-changed versions); add `--latest-only` to keep just the "
    "newest row per URL instead.\n\n"
)

NOTES_AND_DEFINITIONS = (
    "**Method.** `scraped` = unique URLs across `crawls/*.jsonl`. "
    "`content%` = share with non-empty content (page *length* surfaces only as "
    "a `thin?` flag). `eligible` = sitemap URLs matching the spider's allow-"
    "rules, reduced to the live fraction when the crawl recorded HTTP-status "
    "stats (the live% shows as a flag only when low). `coverage` = scraped ÷ "
    "eligible. `total`/`eligible` are read from the crawl when it recorded them "
    "(the sitemap spider counts its own URLs while parsing); otherwise the "
    "audit fetches the sitemap via `./scrapai inspect`, nested indexes capped "
    "(huge-index totals are floors). `-` = no sitemap.\n\n"
    "**Columns**\n\n"
    "- **sitemap** — coverage-denominator source: `yes` = USE_SITEMAP "
    "configured; `found` = no USE_SITEMAP but a *usable* sitemap was "
    "auto-discovered (robots.txt → `/sitemap.xml`); `ignored` = deliberately "
    "skipped via `audit_sitemap_skip.json` (the reason is in `flags`); `no` = "
    "no sitemap found at all. A discovered sitemap that parsed to 0 usable URLs "
    "stays `found` and is flagged `found sitemap empty` for review.\n"
    "- **total** — page URLs in the whole sitemap. Preferred source is the "
    "crawl itself: a `USE_SITEMAP` spider counts every page URL while parsing "
    "and records it in its crawl-stats file, so no re-fetch is needed and the "
    "number matches the sitemap the crawl actually saw (no drift). When that's "
    "absent (rule-based spider, or a pre-feature crawl), the audit fetches and "
    "recurses the sitemap here instead (capped per spider, so for huge indexes "
    "the fetched number is a floor).\n"
    "- **eligible** — the coverage denominator (just a number). Its base count "
    "(page URLs matching the spider's `allow` rules) comes from the crawl when "
    "recorded (same source as `total`), else from the fetched sitemap; it "
    "equals `total` when the spider has no allow rules. When the crawl recorded "
    "liveness, it's reduced to the live fraction (`round(rule-eligible × "
    "live%)`, dead entries removed) — the live% itself shows only as a "
    f"`liveness N%` flag, and only when below {LIVENESS_FLAG_BELOW}%. Liveness "
    "comes **only** from a real crawl's own HTTP-status stats "
    "(`.../crawl_stats/<spider>.json`, `live% = 2xx ÷ (2xx+4xx+5xx)`); no "
    "sampling/probing. (For `found` spiders whose rules don't match the "
    "discovered sitemap, eligible = 0 → `manual review` + `sitemap-empty`.)\n"
    "- **scraped** — unique HTML article URLs in the spider's `crawls/*.jsonl` "
    "output (real on-disk data; the DB holds only test-crawl items). PDF "
    "harvest rows are excluded — they get their own column.\n"
    "- **pdf** — unique PDF documents harvested as URL-only rows "
    '(`metadata_json.content_type = "pdf"`, never downloaded under the '
    "default `PDF_MODE=links_only`). `(N ext)` = PDFs on hosts outside the "
    "spider's own `allowed_domains` — external repositories/citations; the "
    "rest are the org's own documents. Per-host detail: "
    "`external_pdf_report.md` / the PDFs tab. Two edges to know: a sitemap "
    "that lists `.pdf` locs directly can leave those out of coverage (they "
    "count as `pdf`, not `scraped`); in `PDF_MODE=extract` the fetched PDFs "
    "sit in DeltaFetch, so the stale check compares against total uniques.\n"
    "- **coverage** — `scraped ÷ eligible` — the fraction of the pages it "
    "*should* have that it *actually* got (eligible already incorporates "
    "liveness when crawl-stats exist). Can read > 100% when the spider scraped "
    "more rule-matching pages than the sitemap lists; that and a poor scraped-"
    "vs-sitemap overlap demote the row to `manual review` with a "
    "`sitemap-drift` flag.\n"
    "- **content%** — share of scraped HTML pages with non-empty `content` "
    "(extraction success; independent of coverage — PDF rows never count for "
    "or against it). Empty when the spider harvested no HTML at all (see the "
    "`pdf-only` flag). Page *length* isn't a column — a too-thin median "
    "surfaces only as a `thin?` flag.\n"
    "- **true dupes / versions** — see the Duplicate-rows section above.\n"
    "- **stale** — `⚠ Nd` when the newest `crawl_*.jsonl` is older than "
    f"{STALE_DAYS} days (N = age in days); empty = fresh. Its OWN column, "
    "separate from `flags`: data age is about freshness, not a coverage/"
    "extraction concern, so it never triggers manual review and is shown even on "
    "a `✓ reviewed` row.\n"
    "- **flags** — the ONE attention column. A clean, verified, recent spider "
    "leaves it EMPTY; anything here is worth a look. Tokens:\n"
    "    - `found → try sitemap` — the spider crawls without USE_SITEMAP but a "
    "*usable* sitemap was auto-discovered; switching to USE_SITEMAP would give "
    "verifiable coverage (compare `scraped` against `total`).\n"
    "    - `found sitemap empty (0 usable URLs)` — a sitemap WAS discovered but "
    "parsed to 0 usable URLs (malformed, an index with no content, or "
    "all-taxonomy); the row stays `found` and goes to *manual review* so a "
    "human can confirm and record the reason in `audit_sitemap_skip.json`. "
    "**Triggers manual review.**\n"
    "    - `never-ran` / `ran-empty` / `small/partial` — within *too few pages*: "
    "zero output **and no crawl-stats** (no production crawl; `--limit` test "
    "crawls write DB-only, so this also covers spiders only tested at creation) "
    "vs. zero output **but crawl-stats present** (`ran-empty` — it executed and "
    "came back empty: blocked, 0 rule-eligible URLs, or dropped items; re-running "
    "won't help) vs. a small or stalled production run (production is the only "
    "mode that writes JSONL).\n"
    "    - `deltafetch-stale` — DeltaFetch cache ≫ output (size estimate, ~8 "
    "URLs/KB) → output lost; re-crawl with `--reset-deltafetch`.\n"
    f"    - `liveness N%` — shown only when live < {LIVENESS_FLAG_BELOW}%: the "
    "sitemap lists many dead URLs (a high live% is silent). **Triggers manual "
    "review.**\n"
    f"    - `thin? Xk` — median page < {THIN_CHARS} chars: likely over-broad "
    "rules pulling in non-article junk (content% can be 100% while pages are "
    "near-empty). A rough hint — short-form sites are legit. **Triggers manual "
    "review.**\n"
    "    - `no-sitemap` / `sitemap-empty` / `sitemap-drift (m/e)` — within "
    "*manual review*: why completeness is unverifiable (none exists / a "
    "*configured* USE_SITEMAP matched 0 rule URLs / only m of e scraped URLs "
    "intersect the sitemap). **Triggers manual review.**\n"
    "    - `sitemap-cap-hit` — sitemap fetch hit the global cap so the "
    "denominator is truncated. **Triggers manual review.**\n"
    "    - on an `ignored` row (sitemap column), `flags` is the skip reason "
    "from `audit_sitemap_skip.json`.\n"
    '    - `✓ reviewed: …` — a human set `"status": "ok"` in `audit_notes.json`; '
    "the short reason shows here and REPLACES the auto-flags that prompted review "
    "(those are addressed in the note), and the spider is promoted into `ok` "
    "(used for genuinely tiny sites, Wayback-archived sources, or coverage "
    "you've verified). `deltafetch-stale` survives review (it's about lost "
    "output, not the original concern); data-age staleness has its own `stale` "
    "column and is always shown. The "
    "fuller note and its `updated` date live in `audit_notes.json`.\n"
    "    - `⚠ reviewed-stale: …` — a `status: ok` note exists but the spider's "
    "extraction is broken, which a note won't hide; "
    "re-check it and refresh the note in `audit_notes.json`.\n"
    '    - `🗑 discard: …` — `"status": "discard"` in `audit_notes.json`; '
    "a human deliberately dropped this source (duplicate / out of scope / dead). "
    "Moves it to the `discarded` group; never set automatically.\n\n"
    "**Two independent axes:** *coverage* (`scraped`/`eligible` — did we get "
    "enough of the right pages?) and *content%* (did extraction work on what "
    "we got?). A spider can be full-coverage yet low content%, or full content "
    "yet incomplete.\n\n"
    "**Status = solution family (6 groups).** Each spider lands in exactly one, "
    "grouped so spiders needing the same action sit together: *extraction "
    "broken* (fix selectors), *too few pages* (run a full crawl / confirm it's "
    "a small site), *incomplete* (re-crawl / investigate the stall), *manual "
    "review* (extraction fine but a concern flag — coverage unverifiable, "
    "thin, or low liveness — needs a careful `/spider-review`, then a note), *ok* (verified or "
    "`✓ reviewed`, nothing to do), *discarded* (deliberately dropped via "
    "`audit_notes.json`). Precedence matters: extraction quality and "
    "'did a real crawl run' are decided BEFORE coverage, so an empty or odd "
    "sitemap can never mask broken selectors.\n\n"
    "**Coverage is count-based (`scraped ÷ eligible`)**; a normalized URL-set "
    "intersection is still computed internally and raises the `sitemap-drift` "
    "flag (demoting the row to *manual review*) when the scraped URLs don't "
    "actually match the sitemap's — so a count that coincides while the pages "
    "differ is caught, not hidden. Drift is only checked on the fetched-sitemap "
    "path; when counts come from the crawl, denominator and scraped share one "
    "source so there's nothing to drift.\n"
)
