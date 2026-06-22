# Extractors

How to get fields out of HTML — discovery workflow, extractor order, and the schema-driven `FIELD_EXTRACT` directives.

Test generic extractors (trafilatura, newspaper) first. Reach for `FIELD_EXTRACT` when the schema declares non-core fields or generic extractors get the core fields wrong.

---

## Discovery Workflow

**1. Inspect a sample page**
```bash
./scrapai inspect https://example.com/article-url --project proj
```
Add `--browser` if the site is JS-rendered or shows a Cloudflare challenge.

**2. Sanity-check with `try`** — runs newspaper + trafilatura in-process:
```bash
./scrapai try data/proj/spider/analysis/page.html
```
Clean title/author/date/length on both → generic extractors will work. Garbage output → you'll need selectors.

**3. Analyze HTML structure**
```bash
./scrapai analyze data/proj/spider/analysis/page.html
```
Shows h1/h2 titles with classes, content containers by size, date elements, author elements.

**4. Test selectors**
```bash
./scrapai analyze data/proj/spider/analysis/page.html --test "h1.article-title"
./scrapai analyze data/proj/spider/analysis/page.html --test "div.article-body"
```

**5. Search for specific fields**
```bash
./scrapai analyze data/proj/spider/analysis/page.html --find "price"
```

---

## Extractor Order Options

| Config | When to use |
|---|---|
| `["trafilatura", "newspaper"]` | Generic extractors handle clean news/blog HTML. Default. |
| `["newspaper", "trafilatura"]` + `FIELD_EXTRACT` overlay | Mostly article-shaped with 1–2 extra fields. Newspaper fills core; directives override per field. |
| `["custom"]` + `FIELD_EXTRACT` | **Pure-CSS mode** — every field via a deliberate selector. Best when most schema fields are non-core. |
| `["playwright", "trafilatura"]` | JS-rendered, generic extractors work after rendering. |
| `["playwright", "custom"]` + `FIELD_EXTRACT` | JS-rendered, need selectors. |

For non-article structured data (products, jobs, forums) use **named callbacks** instead — see [callbacks.md](callbacks.md).

---

## Schema-driven Extraction (`FIELD_EXTRACT`)

When a project declares a schema in `project.json`, the schema is the contract: every field in `schema.fields` is guaranteed to appear as a top-level key in every exported row, populated or `null`. Extractor side-channels (newspaper's `markdown`/`top_image`/`videos`, newspaper's wrong author guesses, etc.) are pruned before storage — only schema fields make it through.

`FIELD_EXTRACT` is the per-spider directive set that tells the framework how to populate each schema field. Keyed by schema field name.

### Two modes

**Pure-CSS mode** — recommended when many non-core fields need site-specific selectors:
```json
{
  "EXTRACTOR_ORDER": ["custom"],
  "FIELD_EXTRACT": {
    "title":            {"css": "h1.article-title", "to_text": true},
    "content":          {"css": "div.article-body",  "to_text": true},
    "author":           {"css": "span.byline a::text", "processors": [{"type": "strip"}]},
    "published_date":   {"css": "time::attr(datetime)", "processors": [{"type": "parse_datetime"}]},
    "headline_image":   {"css": "img.hero::attr(src)"},
    "markdown_content": {"css": "div.article-body", "to_markdown": true},
    "tags":             {"css": "a.tag::text", "get_all": true},
    "pdf_links":        {"css": "div.article-body a[href$='.pdf']::attr(href)", "get_all": true}
  }
}
```
Skips newspaper/trafilatura entirely. Every field comes from a deliberate selector. Items are stored as long as the URL fetched — content-light pages (video-only, image-only, short notices) get persisted with whatever schema fields populated. Quality gating is the agent's job in Phase 4.

**Overlay mode** — use generic extractor for core fields, override per field as needed:
```json
{
  "EXTRACTOR_ORDER": ["newspaper", "trafilatura"],
  "FIELD_EXTRACT": {
    "author":           {"css": "span.byline a::text"},
    "headline_image":   {"from": "top_image"},
    "video_links":      {"from": "videos"},
    "markdown_content": {"from": "markdown"},
    "tags":             {"css": "a.tag::text", "get_all": true}
  }
}
```
Newspaper runs first; any field with a directive overrides newspaper's value. `from: "<name>"` pulls from the extractor's auto-computed side fields (`markdown`, `top_image`, `images`, `videos`).

### Picking the mode

- **Most fields are non-core** (lots of CSS work anyway) → pure-CSS. Cleaner, faster, no wrong newspaper guesses.
- **Mostly article-shaped (title/content/author/date) + 1–2 extras** → overlay. Let newspaper handle the heavy lifting; override what it gets wrong.
- **One-off ad-hoc scrape, no schema** → omit `FIELD_EXTRACT`; generic `EXTRACTOR_ORDER` is enough.

### Directive shape

| Key | Effect |
|---|---|
| `css` / `xpath` | Selector (use `::text` / `::attr(...)` pseudo-elements for parts of an element) |
| `get_all: true` | Return all matches as a list |
| `to_text: true` | Joined descendant text of matched element (bs4 `get_text(separator=" ", strip=True)` equivalent). Mutually exclusive with `get_all`/`to_markdown` |
| `to_markdown: true` | Outer HTML of matched element converted to markdown via markdownify ATX. Mutually exclusive with `get_all`/`to_text` |
| `from: "<name>"` | Pull from extractor's auto-computed field (`markdown`, `top_image`, `images`, `videos`). Only meaningful in overlay mode |
| `processors: [...]` | Chain processors after extraction (`strip`, `regex`, `parse_datetime`, etc.) — see [processors.md](processors.md) |

### How it interacts with the project schema

- Schema fields **with** a directive → populated from the directive
- Schema fields **without** a directive AND in core (`title`/`content`/`author`/`published_date`/`url`) → preserved from the generic extractor (overlay mode); absent / empty string in pure-CSS mode (add a directive)
- Schema fields **without** a directive AND non-core → explicitly set to `null` (auditable in exports)
- Any item key **not** in the schema → pruned before persistence (no extractor side-channels in output)

### Workflow

1. Read `data/<project>/project.json` to know the field list.
2. For each non-core schema field, decide: `from: <extractor_field>` (overlay) or write a CSS selector.
3. For core fields in pure-CSS mode, write selectors for title/content/author/published_date too.
4. Test with `--limit 5` and verify each schema field is populated or explicitly null.

---

## Selector Discovery Principles

1. Target the MAIN content element — not navigation, sidebar, or footer
2. Selector should match ONE element per page — verify uniqueness
3. Prefer specific classes (`.article-title`) over generic (`.title`)
4. Test on multiple articles — selector must work across pages
5. Prefer semantic tags (`<article>`, `<time>`, `<h1>`)
6. Content selector should return >500 chars; title >10 chars
7. Avoid dynamic/random class names

**Common mistakes:** selector matches multiple elements (gets first, often wrong); selector targets sidebar/footer instead of main content; overly generic selectors like `div.text`; guessing without testing on actual HTML.

---

## JS-Rendered Sites

Signs that `page.html` needs browser rendering:
- Minimal/empty content, just `<div id="app"></div>`
- Content only in `<script>` tags as JS data objects
- "Loading..." placeholder elements

**Two options:**

**Hybrid browser (preferred — fast, also bypasses Cloudflare):** add `"BROWSER_ENABLED": true` or `"CLOUDFLARE_ENABLED": true` to settings. See [cloudflare.md](cloudflare.md).

**Playwright extractor (legacy):** `EXTRACTOR_ORDER: ["playwright", "trafilatura"]` with optional wait config:
```json
{
  "EXTRACTOR_ORDER": ["playwright", "trafilatura"],
  "PLAYWRIGHT_WAIT_SELECTOR": ".article-content",
  "PLAYWRIGHT_DELAY": 5
}
```
- `PLAYWRIGHT_WAIT_SELECTOR`: CSS selector to wait for (max 30s)
- `PLAYWRIGHT_DELAY`: extra seconds after page load

Common wait selectors: `.article-content`, `.quote`, `#posts`, `.loaded`, `[data-loaded="true"]`.

For infinite-scroll pages, see `INFINITE_SCROLL` settings in [settings.md](settings.md).

---

## Legacy: `CUSTOM_SELECTORS`

Back-compat only — prefer `FIELD_EXTRACT` for new spiders.

```json
{
  "EXTRACTOR_ORDER": ["custom", "trafilatura", "newspaper"],
  "CUSTOM_SELECTORS": { "title": "h1.x", "content": "div.y", "author": "span.z", "date": "time.w" }
}
```
A flat `{field: selector}` map. Auto-translated internally to `FIELD_EXTRACT` with `to_text: true` per field.
