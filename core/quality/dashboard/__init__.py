"""Quality-audit dashboard — the primary, interactive view of a project's crawl corpus.

Rendered from the engines' RETURNED structured objects (and the compliance snapshots via
`compliance_capture.build_report_data`), NEVER by re-parsing the markdown reports. The three
markdown files remain the untouched ground truth; this HTML is a *projection* of the same data.

One elegant idea runs through it: a quality report is a **faceted view over one corpus of
sources, each carrying three lenses**. So the UI is *one generic interactive table*
(sort · facet · search · select · expand · tooltip), written once in vanilla JS/CSS and
instantiated three times — Coverage · Compliance · PDFs. Add a lens later = add a column spec,
not more JS.

Everything derives from a single source of truth per fact: status meanings from
`crawl_audit.LEGEND`, fix guidance from `crawl_audit.fix_hints()`, compliance verdicts from
`compliance_capture.assess_crawl` / `assess_reuse`. Every dynamic value is `html.escape`d
(site-derived clause/URL text is untrusted). Self-contained: no server, no new dependency.

This package is a facade over the split modules (assets, widgets, coverage_tab,
compliance_tab, pdfs_tab, render) — every name the old single-file module exposed
is re-exported here, so `from core.quality.dashboard import ...` keeps working
unchanged (including the legacy underscore aliases `_CSS` / `_JS`).
"""

from core.quality._env import DATA_DIR  # noqa: F401 — part of the old module surface
from core.quality.crawl_audit import (
    LEGEND,
    fix_hints,
)  # noqa: F401 — old module surface

from .assets import CSS, JS
from .compliance_tab import (
    _CRAWL_FACET,
    _CRAWL_FACET_LABEL,
    _CRAWL_SEV,
    _REUSE_SEV,
    _compliance_detail,
    _compliance_table,
    _flatten_compliance,
    build_compliance_rows,
)
from .coverage_tab import (
    _SELECT_MODE,
    _SELECT_NOUN,
    _STATUS_ORDER,
    _all_spiders_table,
    _cov_table,
    _coverage_detail,
    _dupes_section,
    _flag_guidance,
    _health_strip,
    _notes_definitions,
    _num_cell,
    _render_hint,
    _slug,
    _status_lead,
    _status_section,
    _status_summary,
    bulk_dedupe_command,
    dupe_command,
)
from .pdfs_tab import (
    _PDF_SHARE_FLOOR,
    _PDF_URL_SAMPLE,
    _STORAGE_RE,
    _ensure_pdf_exclude,
    _is_storage_host,
    _load_pdf_exclude,
    _pdf_config_blob,
    _pdf_detail_placeholder,
    _pdf_exclude_config,
    _pdf_exclude_infobox,
    _pdf_exclude_instructions,
    _pdf_json_blob,
    _pdf_table,
    _project_own_domains,
    _sample_urls,
)
from .render import render_dashboard, write_dashboard
from .widgets import (
    COLUMN_DEFS,
    GLOSSARY,
    STATUS_CLASS,
    _STATUS_CLASS,
    _chip,
    _copy_btn,
    _esc,
    _flag_title,
    _flags_cell,
    _link,
    _md_strip,
    _meter,
    _tip,
    chip,
    copy_btn,
    esc,
    flag_title,
    flags_cell,
    link,
    md_strip,
    meter,
    tip,
)

# legacy asset names — the original module exposed the CSS/JS blocks as _CSS / _JS
_CSS = CSS
_JS = JS


__all__ = [
    "COLUMN_DEFS",
    "CSS",
    "DATA_DIR",
    "GLOSSARY",
    "JS",
    "LEGEND",
    "STATUS_CLASS",
    "_CRAWL_FACET",
    "_CRAWL_FACET_LABEL",
    "_CRAWL_SEV",
    "_CSS",
    "_JS",
    "_PDF_SHARE_FLOOR",
    "_PDF_URL_SAMPLE",
    "_REUSE_SEV",
    "_SELECT_MODE",
    "_SELECT_NOUN",
    "_STATUS_CLASS",
    "_STATUS_ORDER",
    "_STORAGE_RE",
    "_all_spiders_table",
    "_chip",
    "_compliance_detail",
    "_compliance_table",
    "_copy_btn",
    "_cov_table",
    "_coverage_detail",
    "_dupes_section",
    "_ensure_pdf_exclude",
    "_esc",
    "_flag_guidance",
    "_flag_title",
    "_flags_cell",
    "_flatten_compliance",
    "_health_strip",
    "_is_storage_host",
    "_link",
    "_load_pdf_exclude",
    "_md_strip",
    "_meter",
    "_notes_definitions",
    "_num_cell",
    "_pdf_config_blob",
    "_pdf_detail_placeholder",
    "_pdf_exclude_config",
    "_pdf_exclude_infobox",
    "_pdf_exclude_instructions",
    "_pdf_json_blob",
    "_pdf_table",
    "_project_own_domains",
    "_render_hint",
    "_sample_urls",
    "_slug",
    "_status_lead",
    "_status_section",
    "_status_summary",
    "_tip",
    "build_compliance_rows",
    "bulk_dedupe_command",
    "chip",
    "copy_btn",
    "dupe_command",
    "esc",
    "fix_hints",
    "flag_title",
    "flags_cell",
    "link",
    "md_strip",
    "meter",
    "render_dashboard",
    "tip",
    "write_dashboard",
]
