# Queue System (Optional)

**The queue system is OPTIONAL. Use it when the user explicitly requests it.**

## When to Use Queue vs Direct Processing

**Direct Processing (Default):**
```
User: "Add this website: https://example.com"
Claude Code: [Immediately processes: analyze -> rules -> import -> test]
```

**Queue Mode (When User Requests):**
```
User: "Add climate.news to the queue"
Claude Code: [Adds to queue for later processing]

User: "Process the next one in the queue"
Claude Code: [Gets next item, then processes it]
```

## Queue CLI Commands

**Add to Queue:**
```bash
source .venv/bin/activate && ./scrapai queue add <url> [-m "custom instruction"] [--priority N] [--project NAME]
```

**List Queue:**
```bash
# By default: shows 5 pending/processing items (excludes failed/completed)
source .venv/bin/activate && ./scrapai queue list --project NAME
```
```bash
# Show more items
source .venv/bin/activate && ./scrapai queue list --project NAME --limit 20
```
```bash
# Show all items including failed and completed
source .venv/bin/activate && ./scrapai queue list --project NAME --all --limit 50
```
```bash
# Filter by specific status
source .venv/bin/activate && ./scrapai queue list --project NAME --status pending
```
```bash
source .venv/bin/activate && ./scrapai queue list --project NAME --status completed --limit 10
```

**Get Queue Count (just the number):**
```bash
# Count pending/processing items (default)
source .venv/bin/activate && ./scrapai queue list --project NAME --count

# Count by specific status
source .venv/bin/activate && ./scrapai queue list --project NAME --status pending --count
source .venv/bin/activate && ./scrapai queue list --project NAME --status completed --count
source .venv/bin/activate && ./scrapai queue list --project NAME --status failed --count
source .venv/bin/activate && ./scrapai queue list --project NAME --status processing --count
```

**Claim Next Item (Atomic - Safe for Concurrent Use):**
```bash
source .venv/bin/activate && ./scrapai queue next [--project NAME]
# Returns: ID, URL, custom_instruction, priority
```

**Update Status (by ID - no project needed):**
```bash
# Mark as completed
source .venv/bin/activate && ./scrapai queue complete <id>
```
```bash
# Mark as failed
source .venv/bin/activate && ./scrapai queue fail <id> [-m "error message"]
```
```bash
# Retry a failed item
source .venv/bin/activate && ./scrapai queue retry <id>
```
```bash
# Remove from queue
source .venv/bin/activate && ./scrapai queue remove <id>
```

**Note:** Queue item IDs are globally unique, so `--project` is not needed for these commands.

**Bulk Add from File (JSON or CSV):**
```bash
# From JSON file (array of objects with "url" field)
source .venv/bin/activate && ./scrapai queue bulk urls.json --project NAME [--priority N]

# From CSV file (columns: url, name/custom_instruction, priority)
source .venv/bin/activate && ./scrapai queue bulk urls.csv --project NAME [--priority N]
```

**JSON format example:**
```json
[
  {"url": "https://site1.com", "name": "Focus on research articles"},
  {"url": "https://site2.com", "priority": 10},
  {"url": "https://site3.com"}
]
```

**CSV format example:**
```csv
url,name,priority
https://site1.com,Focus on research articles,5
https://site2.com,,10
https://site3.com,Include all news sections,
```

**Bulk Cleanup:**
```bash
source .venv/bin/activate && ./scrapai queue cleanup --completed --force --project NAME  # Remove all completed
```
```bash
source .venv/bin/activate && ./scrapai queue cleanup --failed --force --project NAME     # Remove all failed
```
```bash
source .venv/bin/activate && ./scrapai queue cleanup --all --force --project NAME        # Remove all completed and failed
```

## Queue Workflow for Claude Code

**When user says "Add X to queue":**
1. Run `source .venv/bin/activate && ./scrapai queue add <url> -m "custom instruction if provided" --priority N --project <project_name>`
2. Confirm addition with queue ID
3. Do NOT process immediately

**When user says "Process next in queue":**
1. Run `source .venv/bin/activate && ./scrapai queue next --project <project_name>` to claim next item
2. Note the ID, URL, project, and custom_instruction from output
3. **If custom_instruction exists**: Use it to override CLAUDE.md defaults during analysis
4. Follow the full workflow (Phases 1-4):
   - Phase 1: Analysis & Section Documentation
   - Phase 2: Rule Generation
   - Phase 3: Prepare spider JSONs (**IMPORTANT**: Include `"source_url": "<queue_url>"` in final_spider.json)
   - Phase 4A: Import test_spider.json, verify extraction quality
   - Phase 4B: Import final_spider.json **with --project parameter matching the queue project** (ready for production)
5. **If successful**: `source .venv/bin/activate && ./scrapai queue complete <id>`
6. **If failed**: `source .venv/bin/activate && ./scrapai queue fail <id> -m "error description"`

**CRITICAL: Project Isolation**
- **ALWAYS** import spiders with `--project <name>` matching the queue project
- Example: Processing brown queue -> `source .venv/bin/activate && ./scrapai spiders import file.json --project brown`
- Never omit --project - it will default to "default" and mix up your data
- Maintains clean project separation

## Queue Features

- **Project Isolation**: Multiple projects can have separate queues (default: "default")
- **Priority System**: Higher priority items processed first (default: 5)
- **Custom Instructions**: Per-site instructions override CLAUDE.md defaults
- **Concurrent Safe**: Multiple team members can work simultaneously without conflicts
- **Atomic Claiming**: `queue next` uses PostgreSQL locking to prevent duplicate work
- **Audit Trail**: Tracks who's processing what, when completed/failed

## Example: Queue with Custom Instructions

```
User: "Add climate.news to the queue and focus only on research articles"
Claude Code runs:
  source .venv/bin/activate && ./scrapai queue add https://climate.news -m "Focus only on research articles" --priority 10 --project <project_name>

Later...

User: "Process the next one"
Claude Code runs:
  source .venv/bin/activate && ./scrapai queue next --project <project_name>
  # Output: ID: 1, URL: https://climate.news, Instructions: Focus only on research articles

  # During analysis, Claude Code remembers:
  # "USER INSTRUCTION: Focus only on research articles"
  # This overrides the default content focus rules

  # After successful processing:
  source .venv/bin/activate && ./scrapai queue complete 1
```
