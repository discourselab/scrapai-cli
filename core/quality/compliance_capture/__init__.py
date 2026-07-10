"""Compliance capture — robots.txt, legal/ToS, copyright/licence, and AI-scraping signals.

Independent of the content spiders: needs only a domain, so it can run BEFORE a spider
is built (check a site's terms first). Fetches via `./scrapai inspect` (reusing proxy /
Cloudflare handling), STORES the raw robots + legal pages + any .well-known opt-out files
as evidence, and writes a structured report. It's an OVERVIEW of the live signals (a triage
view, not a legal determination); the `verdict` / `reviewed` / `notes` fields are OPTIONAL
human annotations the tool never sets.

The report separates the two INDEPENDENT questions a scraping pipeline faces — CRAWL (may we
fetch the pages?) and REUSE (may we republish? licence) — into one table each.
CRAWL signals: robots for the paths OUR spider crawls (judged for the UA we actually send,
via a wildcard/`$`-aware matcher — ALL paths or whole-site blocked = 🔴, SOME = 🟡), robots
disallowing the PDFs we capture, and a DIRECTED anti-scraping ToS clause (not a mere mention
of automated processing). The lightweight robots fetch is retried with the browser when it's
blocked (Cloudflare/TLS); a truly unfetchable robots is flagged, not read as "open".
AI signals are flagged ONLY as BLANKET opt-outs: a site-wide AI/TDM reservation (TDMRep
file/meta, a `noai` meta, ai.txt, or a no-AI-training ToS clause) or "per-AI-bot bans" (named
AI/training crawlers disallowed — shown generically, never by name). Individual non-AI bot
blocks (SEO/search) are ignored: they don't bind our UA and say nothing about reuse.
Copyright is kept in the evidence JSON but de-emphasised — absence of a notice means nothing
(content is copyrighted by default); only a licence changes your reuse rights.

Results live per ORGANISATION inside the project, as a DATED snapshot per check — so the
record of what a site's terms/robots said is preserved over time (terms change):
  data/<project>/_audit/compliance/<orgname>/<YYYY-MM-DD>/   (orgname = domain slug, rmi.org -> rmi_org)
    ├── compliance.json   report: robots, AI signals, copyright/licence, legal pages, date
    ├── robots.txt        raw fetched robots.txt
    ├── legal_<slug>.txt  clean full text of each legal/ToS/privacy/licence page
    └── tdmrep.json / ai.txt   .well-known opt-out files, if genuinely present

A project-wide rollup of every org's LATEST snapshot — the human-readable overview — is
written to  data/<project>/_audit/compliance_<project>.md  on every run.

By default a domain that ALREADY has a snapshot is SKIPPED. --update adds a NEW dated
snapshot alongside the existing ones (time-versioning; history is kept). --reset OVERWRITES:
it removes the domain's prior dated snapshots and writes a single fresh one (no history).

Usage (via the CLI — this module is the compliance engine behind `./scrapai audit`,
which captures every project domain inline; new domains only, unless a re-capture flag):
  ./scrapai audit --project gscc                     # capture new domains + build reports
  ./scrapai audit --project gscc --refresh           # re-capture existing snapshots (keep history)
  ./scrapai audit --project gscc --reset             # re-capture, overwriting snapshots (no history)
  ./scrapai audit --project gscc --no-compliance     # skip compliance entirely (cache only)
This package is a facade over the split modules (signals, robots, fetch, page,
store, assess, capture, report) — every name the old single-file module exposed
is re-exported here, so `from core.quality import compliance_capture` keeps
working unchanged.
"""

# Open follow-up work (language-aware legal pages; spider-vs-mini-crawl safety net)
# is tracked in docs/requests/quality-tool.md, not here.


from core.quality._env import DATA_DIR  # noqa: F401 — part of the old module surface

from .assess import (
    CRAWL_COLOR_ORDER,
    REUSE_COLOR_ORDER,
    SUBSTANTIVE_LEGAL_TOKENS,
    _cell,
    _color_rank,
    _is_substantive_legal,
    _norm_legal,
    ai_reuse_flag,
    ai_scrape_flag,
    assess_crawl,
    assess_reuse,
    crawl_notes,
    crawl_pdf_cell,
    crawl_robots_cell,
    cross_check,
    header_probe_blocked,
    license_class,
    license_review_needed,
    license_scope,
    license_source_link,
    llms_cell,
)
from .capture import INSTRUCTIONS, capture, main, run
from .fetch import (
    HEADER_BLOCK_CODES,
    header_signals,
    header_tdm_reserved,
    http_response_headers,
    inspect,
    looks_html,
    visible_text,
)
from .page import (
    LEGAL_WORDS,
    LICENSE_PRIORITY,
    TERMS_PRIORITY,
    cc_from_html,
    detect_license,
    jsonld,
    legal_links,
    link_license,
    meta_copyright,
    robots_meta,
    tdm_meta,
)
from .report import build_report_data, crawl_detail_block, write_report
from .robots import (
    AI_BOTS,
    AI_CHANNEL_BOTS,
    AI_UA_HEURISTIC,
    PDF_PROBES,
    _is_robots,
    ai_bot_signals,
    ai_bots_blocked,
    ai_scrape_block_from,
    blocks_whole_site,
    parse_robots,
    robots_blocks_pdfs,
    robots_blocks_targets,
    robots_can_fetch,
    robots_comment_signals,
    robots_view_from_text,
)
from .signals import (
    BESPOKE_PERMISSION,
    CC_CODE_RE,
    CC_URL_RE,
    COPYRIGHT_RE,
    COPYRIGHT_STMT_RE,
    LICENSE_RE,
    LIMITED_LICENSE_RE,
    LLMS_ALLOW,
    LLMS_PROHIBIT,
    SCRAPE_WORDS,
    SUBSET_WORDS,
    _norm_cc,
    ai_training_prohibition,
    bespoke_permission,
    classify_llms,
    copyright_statement,
    first,
    license_sentence,
    refine_license,
    scrape_prohibition,
    split_license,
)
from .store import (
    DATE_RE,
    TARGET_CAP,
    _failed_marker_path,
    _global_user_agent,
    _spider_cfg_path,
    clear_capture_failed,
    compliance_root,
    crawl_captured_legal_urls,
    existing_snapshots,
    has_capture_failed,
    latest_crawl_file,
    latest_snapshot,
    mark_capture_failed,
    norm_domain,
    org_compliance_dir,
    project_domains,
    project_exists,
    project_targets,
    slug,
    spider_dir_for_domain,
    spider_target_urls,
    spider_user_agent,
    unwrap_wayback,
    wayback_orig_url,
    wayback_ts,
)

__all__ = [
    "AI_BOTS",
    "AI_CHANNEL_BOTS",
    "AI_UA_HEURISTIC",
    "BESPOKE_PERMISSION",
    "CC_CODE_RE",
    "CC_URL_RE",
    "COPYRIGHT_RE",
    "COPYRIGHT_STMT_RE",
    "CRAWL_COLOR_ORDER",
    "DATA_DIR",
    "DATE_RE",
    "HEADER_BLOCK_CODES",
    "INSTRUCTIONS",
    "LEGAL_WORDS",
    "LICENSE_PRIORITY",
    "LICENSE_RE",
    "LIMITED_LICENSE_RE",
    "LLMS_ALLOW",
    "LLMS_PROHIBIT",
    "PDF_PROBES",
    "REUSE_COLOR_ORDER",
    "SCRAPE_WORDS",
    "SUBSET_WORDS",
    "SUBSTANTIVE_LEGAL_TOKENS",
    "TARGET_CAP",
    "TERMS_PRIORITY",
    "_cell",
    "_color_rank",
    "_failed_marker_path",
    "_global_user_agent",
    "_is_robots",
    "_is_substantive_legal",
    "_norm_cc",
    "_norm_legal",
    "_spider_cfg_path",
    "ai_bot_signals",
    "ai_bots_blocked",
    "ai_reuse_flag",
    "ai_scrape_block_from",
    "ai_scrape_flag",
    "ai_training_prohibition",
    "assess_crawl",
    "assess_reuse",
    "bespoke_permission",
    "blocks_whole_site",
    "build_report_data",
    "capture",
    "cc_from_html",
    "classify_llms",
    "clear_capture_failed",
    "compliance_root",
    "copyright_statement",
    "crawl_captured_legal_urls",
    "crawl_detail_block",
    "crawl_notes",
    "crawl_pdf_cell",
    "crawl_robots_cell",
    "cross_check",
    "detect_license",
    "existing_snapshots",
    "first",
    "has_capture_failed",
    "header_probe_blocked",
    "header_signals",
    "header_tdm_reserved",
    "http_response_headers",
    "inspect",
    "jsonld",
    "latest_crawl_file",
    "latest_snapshot",
    "legal_links",
    "license_class",
    "license_review_needed",
    "license_scope",
    "license_sentence",
    "license_source_link",
    "link_license",
    "llms_cell",
    "looks_html",
    "main",
    "mark_capture_failed",
    "meta_copyright",
    "norm_domain",
    "org_compliance_dir",
    "parse_robots",
    "project_domains",
    "project_exists",
    "project_targets",
    "refine_license",
    "robots_blocks_pdfs",
    "robots_blocks_targets",
    "robots_can_fetch",
    "robots_comment_signals",
    "robots_meta",
    "robots_view_from_text",
    "run",
    "scrape_prohibition",
    "slug",
    "spider_dir_for_domain",
    "spider_target_urls",
    "spider_user_agent",
    "split_license",
    "tdm_meta",
    "unwrap_wayback",
    "visible_text",
    "wayback_orig_url",
    "wayback_ts",
    "write_report",
]
