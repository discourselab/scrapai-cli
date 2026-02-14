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
source .venv/bin/activate && ./scrapai queue list
```
```bash
# Show more items
source .venv/bin/activate && ./scrapai queue list --limit 20
```
```bash
# Show all items including failed and completed
source .venv/bin/activate && ./scrapai queue list --all --limit 50
```
```bash
# Filter by specific status
source .venv/bin/activate && ./scrapai queue list --status pending
```
```bash
source .venv/bin/activate && ./scrapai queue list --status completed --limit 10
```

**Claim Next Item (Atomic - Safe for Concurrent Use):**
```bash
source .venv/bin/activate && ./scrapai queue next [--project NAME]
# Returns: ID, URL, custom_instruction, priority
```

**Update Status:**
```bash
source .venv/bin/activate && ./scrapai queue complete <id>
```
```bash
source .venv/bin/activate && ./scrapai queue fail <id> [-m "error message"]
```
```bash
source .venv/bin/activate && ./scrapai queue retry <id>
```
```bash
source .venv/bin/activate && ./scrapai queue remove <id>
```

**Bulk Cleanup:**
```bash
source .venv/bin/activate && ./scrapai queue cleanup --completed --force  # Remove all completed
```
```bash
source .venv/bin/activate && ./scrapai queue cleanup --failed --force     # Remove all failed
```
```bash
source .venv/bin/activate && ./scrapai queue cleanup --all --force        # Remove all completed and failed
```

## Queue Workflow for Claude Code

**When user says "Add X to queue":**
1. Run `source .venv/bin/activate && ./scrapai queue add <url> -m "custom instruction if provided" --priority N`
2. Confirm addition with queue ID
3. Do NOT process immediately

**When user says "Process next in queue":**
1. Run `source .venv/bin/activate && ./scrapai queue next --project <project_name>` to claim next item
2. Note the ID, URL, project, and custom_instruction from output
3. **If custom_instruction exists**: Use it to override CLAUDE.md defaults during analysis
4. Follow the full workflow (Phases 1-4):
   - Analysis & Section Documentation
   - Rule Generation
   - Import Spider **with --project parameter matching the queue project**
   - Test & Verify
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
  source .venv/bin/activate && ./scrapai queue add https://climate.news -m "Focus only on research articles" --priority 10

Later...

User: "Process the next one"
Claude Code runs:
  source .venv/bin/activate && ./scrapai queue next
  # Output: ID: 1, URL: https://climate.news, Instructions: Focus only on research articles

  # During analysis, Claude Code remembers:
  # "USER INSTRUCTION: Focus only on research articles"
  # This overrides the default content focus rules

  # After successful processing:
  source .venv/bin/activate && ./scrapai queue complete 1
```
