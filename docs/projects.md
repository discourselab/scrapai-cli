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

---

## Project Schema

Each named project should have a config at `data/<project>/project.json` declaring the goal, content type, and the schema (fields to extract). This is the contract every spider in the project must satisfy.

### Triggering project creation

When the user asks to add a URL, ALWAYS confirm which project it belongs to before doing anything.

1. **If the user did not name a project** → ask: "Which project should this URL go into?" Do not assume `default`.
2. **If the named project is `default`** → proceed straight to `queue add`. No schema required.
3. **If the named project is anything else** → check if `data/<name>/project.json` exists:
   - **Exists** → proceed to `queue add`.
   - **Missing** → run the interview below, write the file, show the JSON for confirmation, then proceed to `queue add`.

Named projects require a schema. `default` is the only exempt project — use it for ad-hoc, one-off scrapes.

**The interview is mandatory.** NEVER create `project.json` with default or invented values. Even if the user pushes back ("just add it", "use defaults"), stop and explain: a project's schema is a long-lived contract — getting it wrong on day one costs more than the 60 seconds it takes to answer six questions. The only acceptable shortcuts are:

- The user explicitly answers each question (even with "skip" / "none" / "use the standard 4 fields") — that is the interview, just terse.
- The user wants ad-hoc — redirect to `--project default`, which needs no schema.

### Interview

Ask one question at a time. Do not batch.

1. **Goal** — one sentence on what this project is for.
2. **Content type** — `articles` / `products` / `forums` / `listings` / `mixed`. Determines default extractor strategy.
3. **Mandatory fields** — `name:type` pairs. Types: `string`, `datetime`, `list`, `number`, `url`. These must populate or Phase 4 fails the spider.
4. **Optional fields** — same format. Nice-to-have, won't fail the crawl but tracked.
5. **Infinite traps (usually skip this question)** — the crawl collects **everything** by default; there is no exclusion list. About/contact pages (when they hold content) and PDF links (`PDF_MODE: links_only`; set `PDF_MODE: extract` to download and extract text — see CLAUDE.md §7.1) are all collected. Only ask if the user already knows of a specific infinite-trap pattern to avoid — calendar `?date=` loops, faceted-search/filter permutations — which goes in `exclusions`. Everything else: collect it.
6. **Language / date scope** — only ask if the user signals non-English content or a time-bounded corpus.

After collecting answers, show the user the proposed JSON for confirmation before writing.

### File shape

```json
{
  "name": "kb",
  "goal": "Climate science knowledge base for fact-checking",
  "content_type": "articles",
  "schema": {
    "fields": [
      {"name": "title",          "type": "string",   "required": true,  "core": true},
      {"name": "content",        "type": "string",   "required": true,  "core": true},
      {"name": "author",         "type": "string",   "required": false, "core": true},
      {"name": "published_date", "type": "datetime", "required": false, "core": true},
      {"name": "tags",           "type": "list",     "required": false}
    ]
  },
  "exclusions": [],
  "created_at": "YYYY-MM-DD"
}
```

- `core: true` → maps to a typed column on `items` (title, content, author, published_date). These are the only fields `"auto"` can fill.
- `core: false` (or omitted) → lands in `metadata_json`. Give it a selector in a section's `extract` (it can't be `"auto"`).
- `required: true` → `spiders import` rejects spiders that have no source for the field (a section `extract` or `auto` section in the `sections` format; a generic extractor, `FIELDS` directive, or callback in the older format); Phase 4 rejects items where the value is null.

### How the schema flows into Phase 1-4

- **Phase 2** — read `data/<project>/project.json`, then author the spider. Every required field must be **sourced by some section**: each field in a section's `extract` is either `"auto"` (core fields only — `title`/`content`/`author`/`published_date`) or a selector (everything else). `url` is always populated automatically. Keep `"auto"` for the fields the reader gets right; only the extras need selectors.
- **`spiders import`** — rejects the spider if any `required: true` field has no source (not in any section's `extract`, and not covered by an `"auto"` section). Add the missing source and re-import. `--skip-validation` bypasses the check.
- **Phase 4** — after the 5-item test crawl, verify every `required: true` field has a non-null value on every item (import already covered "can it populate"; this covers "did it actually populate"). On failure → `queue fail <id> -m "schema validation failed: <field>"`.
- **Conflict rule** — project schema always wins over queue item `custom_instruction`. The instruction can refine *how* to extract, but cannot remove or rename schema fields.

### Reading the schema later

To inspect the active schema for a project, read the file directly with the Read tool. No CLI command needed.
