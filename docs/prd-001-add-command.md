# PRD-001 — LLM-Driven Spider Generation (`./scrapai add`)

## Overview
`./scrapai add` must expose the existing 4-phase pipeline (inspect → analyze → generate → validate/test crawl) as a single CLI flow so users can script spider creation with their own OpenAI-compatible model. The command must:

- accept the target `URL`, a project name, and a description of the extraction goal,
- run `inspect` (HTTP → browser if needed) and summarize selectors/URLs for the LLM prompt,
- query the user-supplied LLM once per spider attempt and validate against `SpiderConfigSchema`,
- import a Pydantic-validated config into the DB (unless `--dry-run`), and
- run a short test crawl (`--limit 3`) with zero-downtime behavior if the spider already existed (`--backup` default).

### Removed complexity

- Fallback chains for secondary LLMs are no longer required. The command only targets a single OpenAI-compatible endpoint provided via `--llm-api`/`--llm-key`/`--llm-model` or the matching `SCRAPAI_LLM_*` environment variables.
- Retry logic is limited to the same model; failed validations should re-prompt (up to 3 attempts) before aborting.
- The PRD no longer mandates logging or behavioral handling for multiple fallback entries.

## Acceptance Criteria

1. `./scrapai add <url> --project <project> --description "goal" --llm-api <api> --llm-key <key> --llm-model <model>` produces a valid spider, imports it, and prints `[4/4] Validating with test crawl...`.
2. Omitting `--description` still triggers the existing command-level validation error.
3. When a spider already exists, `--backup` (default) exports the previous config before overwriting (INFO log including old ID).
4. `--dry-run` prints the generated JSON, writes `final_spider.json`, and skips DB writes/test crawls.
5. `--dry-run --output spider.json` writes both files without any DB connection.
6. Invalid JSON from the LLM triggers up to three self-correction attempts using the same model before the command exits with code 1.
7. All CLI `--llm-*` flags behave identically when provided via `SCRAPAI_LLM_*` environment variables.
8. `--llm-timeout` enforces the per-call timeout (default 30s).
9. Batch CSV flows still rely on `queue add-with-generate` using the same single-model logic per row.
10. API keys are never logged, stored, or emitted (stdout/stderr/DB/File).
