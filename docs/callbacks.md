# Custom Field Extraction (sections & named callbacks)

Extract custom fields from any structured data - products, jobs, listings, forums. Not limited to articles.

The recommended authoring format is **`sections`**: one section per kind of page, each with its own `match` and `extract`. Sections are desugared into named callbacks at import (`core/sections.py`) — a section whose `extract` is an all-selector dict compiles to exactly one `parse_section_N` callback. **Named callbacks remain fully supported** (sections are what they compile to), and a handful of advanced features — `iterate` (listing-to-detail) and `ajax_nested_list` — are still authored with the explicit `callbacks` block (see [Deferred features](#deferred-features-still-authored-with-callbacks)).

## When to Use

**Use a per-field `extract` (selectors) for:**
- E-commerce (products, prices, ratings)
- Job boards (titles, companies, salaries)
- Real estate (properties, prices, features)
- Forums (posts, authors, replies)
- Any non-article structured data

**Use `extract: "auto"` for:**
- News, blogs, documentation
- Content with title/content/author/date structure

## Sections: one section per layout

Route each kind of page to its own section. Products and reviews live on different layouts, so each gets its own section with its own selectors:

```json
{
  "sections": [
    {
      "match": ["/product/.*"],
      "extract": {
        "name": {"css": "h1::text"},
        "price": {
          "css": "span.price::text",
          "processors": [
            {"type": "strip"},
            {"type": "regex", "pattern": "\\$([\\d.]+)"},
            {"type": "cast", "to": "float"}
          ]
        }
      }
    },
    {
      "match": ["/review/.*"],
      "extract": {
        "title": {"css": "h1.review-title::text"},
        "rating": {"css": "span.stars::attr(data-score)"},
        "body": {"css": "div.review-body p::text", "get_all": true}
      }
    },
    { "match": [".*"], "follow": true }
  ]
}
```

A section is `{ "match": [regex...], "extract": <spec>, "follow": bool (default true), "priority": int? (0-1000), "deny"?, "restrict_xpaths"?, "restrict_css"?, "tags"? }`. The `extract` spec is exactly one of:

- **absent** — follow-only navigation (no extraction); the trailing `{"match": [".*"], "follow": true}` above is a navigation section that just discovers links.
- **`"auto"`** — the built-in article reader (fills title/content/author/published_date).
- **a per-field dict** `{ field: value }` — each value is either `"auto"` (allowed **only** for the four core fields: `title`, `content`, `author`, `published_date`) or a directive `{ "css"|"xpath": "...", "get_all"?, "to_text"?, "to_markdown"?, "processors"? }`.

For non-article structured pages (products, jobs, forums), give every field a selector — `"auto"` is article-only and is rejected on a non-core field at import. Every `required: true` field in the project schema must be sourced by some section.

### auto + one override

A section may mix `"auto"` core fields with a selector override on a specific core field (e.g. fix a wrong author guess while letting the reader handle the rest):

```json
{
  "sections": [
    {
      "match": ["/articles/.*"],
      "extract": {
        "title": "auto",
        "content": "auto",
        "author": { "css": ".byline a::text" }
      }
    }
  ]
}
```

**Constraint:** at most **one** section per spider may mix `"auto"` with overrides. That override path compiles to a spider-wide global `FIELDS` dict (plus the single article extractor), so it is not per-section — give other sections explicit selectors for every field instead. A second such section is rejected at import.

### What sections compile to

`expand_sections` (`core/sections.py`) translates each section into the legacy shape at import:

| Section `extract` | Compiles to |
|---|---|
| absent | a rule with `callback: null` (follow-only) |
| `"auto"` | a rule with `callback: "parse_article"` |
| all selectors | a rule + a generated `parse_section_N` callback holding the `extract` |
| `"auto"` + overrides | a rule with `callback: "parse_article"` + the override merged into global `settings.FIELDS` |

Transport, throughput, `PDF_MODE`, DeltaFetch, and sitemap settings stay in the top-level `settings` block — they are not per-section.

## Still-supported: explicit named callbacks

The format below is what `sections` compiles to, and it imports and runs unchanged. Author it directly when you need a feature not yet covered by `sections` (see [Deferred features](#deferred-features-still-authored-with-callbacks)).

```json
{
  "rules": [{"allow": ["/product/.*"], "callback": "parse_product"}],
  "callbacks": {
    "parse_product": {
      "extract": {
        "name": {"css": "h1::text"},
        "price": {
          "css": "span.price::text",
          "processors": [
            {"type": "strip"},
            {"type": "regex", "pattern": "\\$([\\d.]+)"},
            {"type": "cast", "to": "float"}
          ]
        }
      }
    }
  }
}
```

## Field Extraction

These directives are the same whether a field lives in a section's `extract` or a named callback's `extract`.

**Selectors:**
- CSS: `{"css": "h1::text"}`, `{"css": "img::attr(src)"}`
- XPath: `{"xpath": "//h1/text()"}`
- Lists: `{"css": "li::text", "get_all": true}`
- Clean text: `{"css": "div.body", "to_text": true}` — joined whitespace-stripped descendant text of the matched element
- Markdown: `{"css": "div.body", "to_markdown": true}` — outer HTML of the matched element converted to markdown

`to_text` / `to_markdown` operate on a single element (not compatible with `get_all`, and mutually exclusive).

**Nested lists:**
```json
{
  "reviews": {
    "type": "nested_list",
    "selector": "div.review",
    "extract": {
      "author": {"css": "span.author::text"},
      "rating": {"css": "span.stars::attr(data-rating)", "processors": [{"type": "cast", "to": "int"}]},
      "comment": {"css": "p.text::text"}
    }
  }
}
```

Max depth: 3 levels.

## Processors

8 available - see [processors.md](processors.md):

- `strip` - Remove whitespace
- `replace` - Replace substring
- `regex` - Extract with pattern
- `cast` - Convert type (int, float, bool, str)
- `join` - Join list to string
- `default` - Fallback value
- `lowercase` - Convert to lowercase
- `parse_datetime` - Parse dates (stores as ISO strings)

**Chain processors:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "regex", "pattern": "\\$([\\d.]+)"},
  {"type": "cast", "to": "float"}
]}
```

## Deferred features (still authored with `callbacks`)

The following two features are not yet expressible in `sections` — author them with the explicit `rules` + `callbacks` block. (JS `PAGINATED_LISTINGS` is likewise still authored the legacy way; see [settings.md](settings.md). Sitemaps, by contrast, **do** work with `sections` — just set `"USE_SITEMAP": true` in `settings`; see [sitemap.md](sitemap.md).)

### Iterate: Listing-to-Detail Workflows

For sites where data spans two pages — e.g., a ranking table (listing) links to individual detail pages — use `iterate` to loop over rows, extract per-row fields, and follow links to detail pages with that data passed along.

**Use iterate when:**
- Rankings/directories where rank lives on the listing page but details live on linked pages
- Search results where you need data from both the result snippet and the full page
- Any listing → detail pattern where you need fields from both pages

#### Structure

```json
{
  "callbacks": {
    "parse_listing": {
      "iterate": {
        "selector": "table tr:has(td.rank)",
        "follow": {
          "url": {"css": "td.name a::attr(href)"},
          "callback": "parse_detail"
        }
      },
      "extract": {
        "rank": {"css": "td.rank::text", "processors": [{"type": "strip"}, {"type": "cast", "to": "int"}]},
        "name": {"css": "td.name a::text"}
      }
    },
    "parse_detail": {
      "extract": {
        "website": {"css": "a.website::attr(href)"},
        "description": {"css": "div.about::text"}
      }
    }
  }
}
```

#### How it works

1. `parse_listing` loops over each row matching `selector`
2. For each row, `extract` fields are pulled from the **row element** (not full page)
3. The `follow.url` selector extracts the link from the row
4. A request is made to that URL with `callback: "parse_detail"`
5. Extracted row fields are passed via Scrapy `meta` as `listing_data`
6. `parse_detail` receives the response, merges `listing_data` into its item, then extracts its own fields

The final item contains fields from **both** pages (listing + detail) at the top level.

#### Optional: url_context

Extract fields from the **page URL** using regex (useful when URL contains data like country codes):

```json
{
  "iterate": {
    "selector": "table tr",
    "url_context": {
      "country_code": {"regex": "/(\\w{2})/"},
      "state": {"regex": "/\\w{2}/([\\w-]+)\\.htm"}
    },
    "follow": {
      "url": {"css": "td a::attr(href)"},
      "callback": "parse_detail"
    }
  }
}
```

`url_context` fields are extracted once per page and included in every row's `listing_data`.

#### Key details

- `extract` in iterate mode uses the **row** as scope (not full response)
- `url_context` regex must have exactly **one capture group**
- `follow.callback` must reference a defined callback (or `parse_article`)
- Rows without a matching URL are silently skipped
- Items are only counted when the detail callback yields (not the iterate callback)
- `extract` is optional in iterate callbacks (you can follow without extracting row fields)

### AJAX Nested List (`ajax_nested_list`)

For extracting data from AJAX endpoints (e.g., AJAX-loaded comments). Makes HTTP requests to fetch additional data not in the main page HTML.

```json
{
  "comments": {
    "type": "ajax_nested_list",
    "ajax_url": "/wp-admin/admin-ajax.php",
    "ajax_method": "POST",
    "ajax_data": {
      "action": "wpdLoadMoreComments",
      "postId": "{post_id}"
    },
    "post_id_css": "body::attr(class)",
    "post_id_regex": "postid-(\\d+)",
    "response_json_field": "data.comment_list",
    "selector": "div.wpd-comment",
    "extract": {
      "username": {"css": "div.wpd-comment-author a::text"},
      "text": {"css": "div.wpd-comment-text p::text", "get_all": true}
    }
  }
}
```

**Config options:**
- `ajax_url` — endpoint URL (relative or absolute)
- `ajax_method` — `GET` or `POST` (default: `POST`)
- `ajax_data` — request parameters. Use `{post_id}` placeholder for dynamic post IDs
- `post_id_css` — CSS selector to extract post ID from the page
- `post_id_regex` — regex to extract ID from the selector value (e.g., `"postid-(\\d+)"`)
- `response_json_field` — dot-path to HTML content in JSON response (e.g., `"data.comment_list"`)
- `response_type` — `json_html` (default, HTML inside JSON), `json_array` (JSON array of objects), or `json_object` (single JSON object — extracts `json_path` fields and stores the result as one dict rather than a list)
- `ajax_per_page` — items per page for pagination (0 = no pagination)
- `selector` / `extract` — same as `nested_list` for HTML responses
- For `json_array` responses, use `json_path` in extract fields instead of CSS/XPath:
  ```json
  {"json_path": "author_name", "processors": [{"type": "strip"}]}
  ```

#### Nesting replies (threaded comments)

When comments have parent-child relationships (e.g., WP REST API returns flat list with `parent` field):
```json
{
  "nest_replies": true,
  "comment_id_field": "comment_id",
  "parent_id_field": "parent_id",
  "replies_field": "replies"
}
```
Builds a tree structure where replies are nested inside their parent comment's `replies` array.

#### Common patterns

*wpDiscuz AJAX comments (POST):*
```json
{
  "type": "ajax_nested_list",
  "ajax_url": "/wp-admin/admin-ajax.php",
  "ajax_data": {"action": "wpdLoadMoreComments", "offset": "0", "postId": "{post_id}"},
  "post_id_css": "body::attr(class)",
  "post_id_regex": "postid-(\\d+)",
  "response_json_field": "data.comment_list",
  "selector": "div.wpd-comment",
  "extract": { ... }
}
```

*WP REST API comments (GET, with nesting):*
```json
{
  "type": "ajax_nested_list",
  "ajax_url": "/wp-json/wp/v2/comments",
  "ajax_method": "GET",
  "ajax_data": {"post": "{post_id}", "order": "asc"},
  "ajax_per_page": 100,
  "post_id_css": "body::attr(class)",
  "post_id_regex": "postid-(\\d+)",
  "response_type": "json_array",
  "nest_replies": true,
  "selector": "unused",
  "extract": {
    "username": {"json_path": "author_name"},
    "comment_text": {"json_path": "content.rendered"},
    "comment_date": {"json_path": "date"},
    "parent_id": {"json_path": "parent"},
    "comment_id": {"json_path": "id"}
  }
}
```

## Templates

Complete working examples in `templates/`:

- **E-commerce:** `templates/spider-ecommerce.json`
- **Job boards:** `templates/spider-jobs.json`
- **Real estate:** `templates/spider-realestate.json`

Use as starting points - adjust selectors to match target site.

## Reserved Names

Never use: `parse_article`, `parse_start_url`, `start_requests`, `from_crawler`, `closed`, `parse`

## Storage

- Standard fields (url, title, content, author, published_date) → DB columns
- Custom fields → `metadata_json` column
- `show` command displays custom fields
- Exports flatten custom fields to top-level columns/keys

## Workflow

1. Analyze sample page: `./scrapai analyze page.html`
2. Identify fields and discover selectors: `./scrapai analyze page.html --test "h1::text"`
3. Build a section per layout (one `match` + `extract` each), with processors
4. Test on multiple pages to verify selectors work
5. Import and test: `./scrapai crawl spider --limit 5 --project proj`

## Common Patterns

**Extract price:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "regex", "pattern": "\\$([\\d,.]+)"},
  {"type": "replace", "old": ",", "new": ""},
  {"type": "cast", "to": "float"}
]}
```

**Extract boolean:**
```json
{"processors": [
  {"type": "lowercase"},
  {"type": "regex", "pattern": "(yes|true|available)"},
  {"type": "cast", "to": "bool"}
]}
```

**Handle missing fields:**
```json
{"processors": [
  {"type": "strip"},
  {"type": "default", "default": null}
]}
```

## Troubleshooting

**Field returns None:**
- Test selector: `./scrapai analyze page.html --test "selector"`
- Check if page needs `--browser` (for JS-rendered or Cloudflare-protected sites)
- Verify processor chain (failed processor may return None)

**Wrong type in output:**
- Add `cast` processor: `{"type": "cast", "to": "float"}`

**Rule references undefined callback:**
- Add callback to `callbacks` dict
- Or use `callback: null` for navigation-only rules
