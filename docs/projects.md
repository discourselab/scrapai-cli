# Project System

Projects isolate spiders, queue items, and scraped data from each other. Every operation should specify which project it belongs to.

## Why Projects Matter

- **Data isolation**: Spiders in project "brown" don't mix with project "climate"
- **Clean organization**: Each project has its own queue, spiders, and data
- **No accidental overlap**: Without `--project`, everything goes to "default" which gets messy fast

## Listing All Projects

To see what projects exist in your system:

```bash
./scrapai projects list
```

Example output:
```
📁 Available Projects:
  • project_name_1
    Spiders: 10, Queue items: 25
  • project_name_2
    Spiders: 5, Queue items: 12
  • default
    Spiders: 3, Queue items: 0
```

## ALWAYS Specify --project

**Every command that supports --project MUST have it specified. Never omit it.**

If you omit `--project`, the command defaults to the "default" project. This causes:
- Spiders from different projects mixed together
- Queue items claimed from wrong project
- Confusion about which data belongs where

## Commands That Require --project

**Spider Management:**
```bash
# Import spider - ALWAYS specify project
./scrapai spiders import <file> --project <name>
```
```bash
# List spiders in a specific project
./scrapai spiders list --project <name>
```
```bash
# List ALL spiders across all projects (no --project needed here)
./scrapai spiders list
```

**Queue Management:**
```bash
# Add to queue - specify which project's queue
./scrapai queue add <url> --project <name> [-m "instruction"] [--priority N]
```
```bash
# Claim next item from a specific project's queue
./scrapai queue next --project <name>
```

## Project Workflow

When processing a website (whether direct or from queue):

1. **Know your project name** before starting any work
2. **Import with --project**: `./scrapai spiders import final_spider.json --project <name>`
3. **Queue operations with --project**: `./scrapai queue next --project <name>`
4. **Verify in the right project**: `./scrapai spiders list --project <name>`

## Queue + Project Isolation

When processing queue items:
- The queue item has a project field
- **ALWAYS use that project name** for the spider import
- Example: Queue item says project "brown" -> `./scrapai spiders import file.json --project brown`
- Never import a spider to a different project than the queue item's project
