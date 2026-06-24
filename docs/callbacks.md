# Named Callbacks & Custom Fields

Extract custom fields from any structured data - products, jobs, listings, forums. Not limited to articles.

## When to Use

**Use callbacks for:**
- E-commerce (products, prices, ratings)
- Job boards (titles, companies, salaries)
- Real estate (properties, prices, features)
- Forums (posts, authors, replies)
- Any non-article structured data

**Use parse_article for:**
- News, blogs, documentation
- Content with title/content/author/date structure

## Basic Structure

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

## Iterate: Listing-to-Detail Workflows

For sites where data spans two pages — e.g., a ranking table (listing) links to individual detail pages — use `iterate` to loop over rows, extract per-row fields, and follow links to detail pages with that data passed along.

**Use iterate when:**
- Rankings/directories where rank lives on the listing page but details live on linked pages
- Search results where you need data from both the result snippet and the full page
- Any listing → detail pattern where you need fields from both pages

### Structure

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

### How it works

1. `parse_listing` loops over each row matching `selector`
2. For each row, `extract` fields are pulled from the **row element** (not full page)
3. The `follow.url` selector extracts the link from the row
4. A request is made to that URL with `callback: "parse_detail"`
5. Extracted row fields are passed via Scrapy `meta` as `listing_data`
6. `parse_detail` receives the response, merges `listing_data` into its item, then extracts its own fields

The final item contains fields from **both** pages (listing + detail) at the top level.

### Optional: url_context

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

### Key details

- `extract` in iterate mode uses the **row** as scope (not full response)
- `url_context` regex must have exactly **one capture group**
- `follow.callback` must reference a defined callback (or `parse_article`)
- Rows without a matching URL are silently skipped
- Items are only counted when the detail callback yields (not the iterate callback)
- `extract` is optional in iterate callbacks (you can follow without extracting row fields)

## AJAX Nested List (`ajax_nested_list`)

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

### Nesting replies (threaded comments)

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

### Common patterns

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
3. Build callback config with processors
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
