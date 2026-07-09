"""Quality-audit engines behind `./scrapai audit` / `./scrapai overview` /
`./scrapai dedupe`.

Each module exposes a `run(project, opts)` that RETURNS its structured result and
still writes its markdown/CSV, resolving the data root via `core.config.DATA_DIR`
and the repo environment (CLI launcher, settings.py, .scrapy) via `_env`.

These modules are CANONICAL. They began as ports of standalone root scripts, which
are kept at the repo root as frozen `*.superseded` reference copies (never edit or
delete them). The ports have since deliberately diverged from those references:

- compliance: report-time recomputes (legal-page prohibitions, the AI-reuse
  aggregate incl. legacy-snapshot evidence fallback) refresh verdicts on stored
  snapshots without re-capture; snapshots are written only for reachable domains.
- crawl_audit: `run()` accepts `reset` for compliance snapshots; the sitemap cache
  is generation-pruned with temp+swap fetches; `db_query` fails loudly.
- report text: retry hints reference the `./scrapai audit` flags.
"""
