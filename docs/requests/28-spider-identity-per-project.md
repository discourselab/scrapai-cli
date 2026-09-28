# Change request: a spider is identified by name and project, not name alone

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-09-28)
- **Files:** `cli/spiders.py` — `import_spider()`, `delete_spider()`; `spiders/base.py` — new `_find_spider_record()`; `spiders/database_spider.py`, `spiders/sitemap_spider.py` — `__init__()`, `_load_config()`; `cli/crawl.py` — `_run_spider()`
- **Type:** framework change (data-integrity bugfix)
- **Requested by:** @MirjamOdile

## Problem

The schema scopes spider names to a project: `core/models.py` declares
`UniqueConstraint("name", "project", name="uq_spider_name_project")` (alembic
`1beddbb53e84`), and `tests/unit/test_models.py` requires one name to be
allowed in two projects. `docs/projects.md` opens with "Projects isolate
spiders, queue items, and scraped data." Four code paths ignored that and
looked a spider up by name alone.

**`spiders import`** ran `filter(Spider.name == spider_name).first()`. Importing
`example_org` into project `proj` while `example_org` already existed in `news`
matched the `news` row, set its `project` to `proj`, deleted its `SpiderRule`
and `SpiderSetting` rows and wrote the new config into it. Because the row kept
its id, every `scraped_items` row keyed by that `spider_id` moved to `proj` with
it. The only output was `Spider 'example_org' already exists. Updating...`.

**The crawl-time loaders** — `DatabaseSpider._load_config()` and
`SitemapDatabaseSpider._load_config()` — used the same name-only `.first()`,
with no `order_by`. `cli/crawl.py` validates the spider by name and project,
but the Scrapy command it builds passed only `-a spider_name=<name>`, so the
project never reached the spider. Reproduced on a copy of the working
database: with the import fixed alone, a `--limit` crawl for `proj` loaded the
`news` config and wrote its items under the `news` spider's id and in the
`news` project's schema.

**`spiders delete <name>`** without `--project` deleted the first match
silently.

Nothing is broken in data today: the working database holds 228 spiders across
6 projects and every name is unique. The failure is latent and becomes silent
data loss the first time a name is reused — the case the schema was built to
allow.

Already project-scoped and unchanged: `queue`, `export`, `health`, `show`,
`crawl`'s validation, the crawl output path, `JOBDIR`, `DELTAFETCH_DIR` and the
Pueue labels.

## Change

**`spiders import`** looks the spider up by name and project. A re-import into
the same project updates that row in place, as before, and the message now
names the project (`already exists in project 'news'. Updating...`). A name
held only in other projects creates a new row and says so:
`'example_org' also exists in project(s) news; creating a separate spider in
'proj' and leaving those untouched.` The update branch no longer assigns
`existing.project`.

**Every crawl passes the project to the spider.** All launch paths reach Scrapy
through one command builder, `_run_spider()` in `cli/crawl.py`, which now adds
`-a project=<p>`:

| Launch path | Route |
|---|---|
| `crawl <name> --project <p> --limit N` | `_run_spider()` → Scrapy directly |
| `crawl <name> --project <p>` (production) | `_run_spider()` → Pueue task `crawl … --detached` → `_run_spider()` |
| `crawl-all --project <p>` | `_run_spider()` per spider, either route above |
| `health --project <p>` | subprocess `./scrapai crawl <name> --project <p> --limit N` |

`queue` hands out work but launches nothing; `scrape`, `inspect` and `try`
fetch without a spider row.

**`DatabaseSpider` and `SitemapDatabaseSpider`** accept a keyword-only
`project` and load their row through `_find_spider_record()`: scoped by name and
project when one is given; without one (a direct `scrapy crawl`), a name held
by exactly one row still resolves, and a name held in several projects raises
`Spider 'example_org' exists in more than one project (news, proj); pass -a
project=<name> to choose one` instead of taking whichever row comes first.

**`spiders delete <name>`** without `--project` refuses when the name exists in
more than one project, listing them. With `--project`, or with a unique name,
it behaves as before.

## Behavior changes

- Importing a name into a second project creates a second spider. Before, it
  moved the first project's spider — items included — and replaced its config.
- A direct `scrapy crawl … -a spider_name=<name>` without `-a project` now
  fails on an ambiguous name. The CLI always passes the project.
- `spiders delete <name>` without `--project` refuses an ambiguous name.

Unchanged: re-importing into the same project, every crawl while names stay
unique (all of them today), delete with `--project`, and every path already
listed as project-scoped. Name matching stays case-sensitive, as the unique
constraint is.

**Moving a spider between projects** was only ever a side effect of the bug,
and never a whole move: the database rows went, while its crawl files,
checkpoint and DeltaFetch state stayed under the old project's directories. The
path now is to import into the new project and `spiders delete <name> --project
<old>` — which also deletes the old row's DB items; production crawls keep
their corpus in `crawls/*.jsonl`, which the delete does not touch.

**Rejected:** a global unique constraint on `name`. It would make the name-only
lookups correct by forbidding what the schema and its tests deliberately allow,
and it would need a migration that fails on any database already reusing a
name.

## Tracked docs this makes wrong

`CLAUDE.md` Phase 4B says "same name auto-updates". Read with the `--project
<p>` it sits beside, that stays true; what no tracked doc stated is that the
name is per project, so `CLAUDE.md` §6.1 gains one line saying it (import
updates within a project, another project gets a separate spider, delete
without `--project` refuses an ambiguous name). §6.1 rather than Phase 4B
because PR 20 rewrites the line next to 4B, and adjacent edits would conflict.
`docs/analysis-workflow.md` Step 4B's "(auto-updates)" is the same
same-project case and stays correct. `docs/projects.md` already said projects
isolate spiders; the change makes that true. README's "move them between
projects" is about JSON configs and stays correct.

## Verification

- `tests/unit/test_spider_project_scope.py`, 16 tests against an in-memory
  SQLite database (every `get_db()` patched, so the working database is never
  opened):
  - `test_import_into_second_project_leaves_first_untouched` — original row keeps
    its project, config and items.
  - `test_reimport_into_same_project_updates_in_place`
  - For both `DatabaseSpider` and `SitemapDatabaseSpider`:
    `test_load_picks_the_row_of_the_given_project`,
    `test_scrapy_a_project_reaches_the_lookup` (through `from_crawler`, as
    `scrapy crawl -a` delivers it),
    `test_load_without_project_refuses_an_ambiguous_name`,
    `test_load_without_project_still_resolves_a_unique_name`,
    `test_load_with_project_not_holding_the_name_fails`.
  - `test_crawl_command_passes_the_project_to_the_spider`
  - `test_delete_without_project_refuses_an_ambiguous_name`,
    `test_delete_with_project_removes_only_that_row`,
    `test_delete_without_project_still_works_for_a_unique_name`.
- 12 of the 16 fail against unchanged `main`; the four that pass pin behaviour
  that must not change (unique-name load; delete by `--project` or unique name).
- Existing spider-construction mocks in five test files now stub
  `filter().all()` instead of `filter().first()`, the query shape
  `_find_spider_record()` uses.
- Full unit suite green (504 passed).

## Merge note

`pr/21`'s repository-harvest spider (`spiders/repository_spider.py`, absent on
`main`) has the same name-only `_load_config()`. It is fixed on the `pr/21`
branch itself, not here, so the two merge independently in either order: there
the spider takes the same optional `project` keyword under the same rules,
inlined because `_find_spider_record()` does not exist until this request
lands. Before this request the CLI does not pass `project` and the spider
behaves as before; after it, `cli/crawl.py` passes `-a project` to every spider
class, the repository spider included.
