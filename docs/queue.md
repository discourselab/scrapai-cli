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
./scrapai queue complete <id>
./scrapai queue fail <id> [-m "error message"]
./scrapai queue retry <id>
./scrapai queue remove <id>
```

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
- `priority` - Higher number = higher priority (optional, default: 0)

## Queue Processing Workflow

1. `./scrapai queue next --project NAME` — claim next item
2. Note: ID, URL, project, custom_instruction
3. If custom_instruction exists: use it to override CLAUDE.md defaults
4. Run Phases 1-4. Include `"source_url": "<queue_url>"` in final_spider.json.
5. Import spider with `--project` matching queue project.
6. On success: `./scrapai queue complete <id>`
7. On failure: `./scrapai queue fail <id> -m "error description"`

## Custom Instruction Handling

When `queue next` returns a `custom_instruction`, use it to override CLAUDE.md defaults during analysis.
Example: instruction "Focus only on research articles" → only create rules for research article URL patterns, skip other content sections.

## Direct vs Queue

- User says "Add this website: X" → process immediately (Phases 1-4), no queue
- User says "Add X to the queue" → `queue add` only, do NOT process
- User says "Process next" → `queue next` then Phases 1-4

## Project Isolation

NEVER omit `--project` when importing spiders from queue. Without it, spider defaults to "default" project, mixing data across projects. Always match the queue item's project.
