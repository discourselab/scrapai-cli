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
5. **Exclusions** — anything beyond the standard skips (about, contact, donate, legal, search, PDFs)?
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

- `core: true` → maps to a typed column on `items` (title, content, author, published_date). Generic extractors (trafilatura, newspaper) fill these natively.
- `core: false` (or omitted) → lands in `metadata_json`. Populate via `FIELD_EXTRACT` directives or named callbacks.
- `required: true` → `spiders import` rejects spiders that have no source for the field; Phase 4 rejects items where the value is null.

### How the schema flows into Phase 1-4

- **Phase 2** — read `data/<project>/project.json`. If schema is core-only → `EXTRACTOR_ORDER: ["trafilatura", "newspaper"]`. If non-core fields exist → use `FIELD_EXTRACT` (overlay mode for a few extras, or pure-CSS mode with `EXTRACTOR_ORDER: ["custom"]` when most fields are non-core). For non-article structured data use named callbacks.
- **`spiders import`** — rejects the spider if any `required: true` field has no source (no generic extractor in `EXTRACTOR_ORDER` AND no `FIELD_EXTRACT` directive). Add the missing directives and re-import. Use `--skip-validation` only if you know what you're doing.
- **Phase 4** — after the 5-item test crawl, verify every `required: true` field has a non-null value on every item (import already covered "can it populate"; this covers "did it actually populate"). On failure → `queue fail <id> -m "schema validation failed: <field>"`.
- **Conflict rule** — project schema always wins over queue item `custom_instruction`. The instruction can refine *how* to extract, but cannot remove or rename schema fields.

### Reading the schema later

To inspect the active schema for a project, read the file directly with the Read tool. No CLI command needed.
