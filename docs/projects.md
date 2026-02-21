# Projects

Projects isolate spiders, queue items, and scraped data. **Always specify `--project <name>`.**

Without `--project`, commands default to "default" project, mixing data.

## List Projects

```bash
./scrapai projects list
```

## Commands That Need --project

```bash
./scrapai spiders list --project <name>
./scrapai spiders import <file> --project <name>
./scrapai spiders delete <name> --project <name>
./scrapai crawl <name> --project <name>
./scrapai show <name> --project <name>
./scrapai export <name> --project <name> --format csv
./scrapai queue add <url> --project <name>
./scrapai queue list --project <name>
./scrapai queue next --project <name>
./scrapai queue cleanup --all --force --project <name>
```

**Exception:** `./scrapai spiders list` (no --project) lists ALL spiders across all projects.

**Exception:** Queue status commands use globally unique IDs, no --project needed:
`queue complete <id>`, `queue fail <id>`, `queue retry <id>`, `queue remove <id>`
