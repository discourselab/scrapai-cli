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
- Check if page needs `--browser` or `--cloudflare`
- Verify processor chain (failed processor may return None)

**Wrong type in output:**
- Add `cast` processor: `{"type": "cast", "to": "float"}`

**Rule references undefined callback:**
- Add callback to `callbacks` dict
- Or use `callback: null` for navigation-only rules
