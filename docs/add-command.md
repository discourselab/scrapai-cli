# `./scrapai add` — LLM-Driven Spider Generation

Generate and import a spider config from a single URL and description using any OpenAI-compatible LLM endpoint.

## Usage

```bash
./scrapai add <url> \
  --project <name> \
  --description "Extract article titles and links" \
  --llm-api https://api.openai.com/v1 \
  --llm-key $MY_LLM_KEY \
  --llm-model gpt-4o
```

### Dry run

```bash
./scrapai add https://example.com \
  --project demo \
  --description "Extract the main article title and content" \
  --llm-api https://api.openai.com/v1 \
  --llm-key $MY_LLM_KEY \
  --llm-model gpt-4o \
  --dry-run --output spider.json
```

## Flags

- `--project` (required): Project name
- `--description` (required): Extraction goal
- `--llm-api`: LLM base URL (default: `https://api.openai.com/v1`)
- `--llm-key`: LLM API key (required unless set in env)
- `--llm-model`: Model name (required unless set in env)
- `--llm-timeout`: Per-call timeout in seconds (default: 30)
- `--dry-run`: Skip DB write and test crawl; prints JSON to stdout
- `--output`: Write JSON to file
- `--backup/--no-backup`: Backup existing spider before overwrite (default: true)
- `--skip-test-crawl`: Skip Phase 4 test crawl (use with `--dry-run`)

The generated config is also written to `data/<project>/<spider>/analysis/final_spider.json`.

## Environment Variables

```bash
export SCRAPAI_LLM_API=https://openrouter.ai/api/v1
export SCRAPAI_LLM_KEY=your-api-key
export SCRAPAI_LLM_MODEL=anthropic/claude-sonnet-4-6
```

## Dry-Run Caveat

`--dry-run` skips Phase 4 (test crawl). The generated JSON may be structurally valid but functionally broken if selectors do not match the live page. Always run without `--dry-run` before using a config in production.
