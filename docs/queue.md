# Queue System

Optional. Use when the user explicitly requests it. Always specify `--project`.

## Commands

**Add:**
```bash
./scrapai queue add <url> --project NAME [-m "instruction"] [--priority N]
```

**Bulk add:**
```bash
./scrapai queue bulk <file.csv|file.json> --project NAME [--priority N]
```

**List:**
```bash
./scrapai queue list --project NAME                          # 5 pending/processing (default)
./scrapai queue list --project NAME --limit 20               # more items
./scrapai queue list --project NAME --all --limit 50         # include completed/failed
./scrapai queue list --project NAME --status pending         # filter by status
./scrapai queue list --project NAME --count                  # just the count
./scrapai queue list --project NAME --status failed --count  # count by status
```

**Claim next:**
```bash
./scrapai queue next --project NAME
```

**Update status (ID is globally unique, no --project needed):**
```bash
./scrapai queue complete <id> [--spider <name>] [--force]
./scrapai queue fail <id> [-m "error message"]
./scrapai queue retry <id>
./scrapai queue remove <id>
```

`queue complete` verifies before marking done: the spider must exist in the DB
and `final_spider.json` must exist on disk (under
`DATA_DIR/<project>/<spider>/analysis/`). If either is missing it refuses and
leaves the item unchanged. The spider name is derived from the URL's domain
(dots/dashes → underscores); pass `--spider <name>` if the spider has a
different name, or `--force` to skip both checks.

**Cleanup:**
```bash
./scrapai queue cleanup --completed --force --project NAME
./scrapai queue cleanup --failed --force --project NAME
./scrapai queue cleanup --all --force --project NAME
```

## Bulk File Formats

**JSON format** (see `templates/queue-template.json`):
```json
[
  {"url": "https://site1.com", "custom_instruction": "Focus on research articles", "priority": 5},
  {"url": "https://site2.com", "priority": 10},
  {"url": "https://site3.com", "custom_instruction": "Include all news sections", "priority": 1}
]
```

**CSV format** (see `templates/queue-template.csv`):
```csv
url,custom_instruction,priority
https://site1.com,Focus on research articles,5
https://site2.com,,10
https://site3.com,Include all news sections,1
```

**Required columns:**
- `url` - Website URL (required)
- `custom_instruction` - Special instructions for this site (optional)
- `priority` - Higher number = higher priority (optional). Items omitting
  priority fall back to the file's `--priority` value (default: 5).

## Queue Processing Workflow

1. `./scrapai queue next --project NAME` — claim next item
2. Note: ID, URL, project, custom_instruction
3. If custom_instruction exists: use it to override CLAUDE.md defaults
4. Run Phases 1-4. Include `"source_url": "<queue_url>"` in final_spider.json.
5. Import spider with `--project` matching queue project.
6. On success: `./scrapai queue complete <id>`
7. On failure: `./scrapai queue fail <id> -m "error description"`

## Parallel Processing

Process up to **5 sites at once** — never more. Have more than 5 queued? Batch
them (12 → 5 + 5 + 2), finishing one batch before starting the next.

- **Start the browser service first:** `./scrapai browser start`. The parallel
  agents then share one warm browser (Cloudflare solved once) instead of each
  cold-starting their own.
- Spawn one agent per site, each running Phases 1-4 from CLAUDE.md against its
  own queue item.
- **Phases stay sequential within each site** — parallelism is across sites, not
  across phases. Each agent runs 1 → 2 → 3 → 4 in order.
- On success the agent runs `queue complete <id>`; on failure
  `queue fail <id> -m "reason"`. Surface failures as they happen and report per
  batch.

## Custom Instruction Handling

When `queue next` returns a `custom_instruction`, use it to override CLAUDE.md defaults during analysis.
Example: instruction "Focus only on research articles" *narrows* scope against the default collect-everything policy → only create rules for research article URL patterns, skip other content sections. Use such instructions only when the user explicitly wants a subset; the default remains to collect every section and subsection.

## Direct vs Queue

- User says "Add this website: X" → process immediately (Phases 1-4), no queue
- User says "Add X to the queue" → `queue add` only, do NOT process
- User says "Process next" → `queue next` then Phases 1-4

## Project Isolation

NEVER omit `--project` when importing spiders from queue. Without it, spider defaults to "default" project, mixing data across projects. Always match the queue item's project.
