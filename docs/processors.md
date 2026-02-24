# Field Processors Reference

Processors transform extracted values (strip whitespace, cast types, apply regex, etc.). They run sequentially in the order specified.

## Processor List

### 1. strip

Remove leading and trailing whitespace from strings.

**Parameters:** None

**Example:**
```json
{
  "css": "h1::text",
  "processors": [{"type": "strip"}]
}
```

**Input → Output:**
```
"  Hello World  " → "Hello World"
```

**Works on:** Strings and lists of strings

---

### 2. replace

Replace substring in strings.

**Parameters:**
- `old` (required): Substring to replace
- `new` (required): Replacement string

**Example:**
```json
{
  "css": "span.price::text",
  "processors": [
    {"type": "replace", "old": "$", "new": ""},
    {"type": "replace", "old": ",", "new": ""}
  ]
}
```

**Input → Output:**
```
"$1,299.99" → "1299.99"
```

**Works on:** Strings and lists of strings

---

### 3. regex

Extract substring using regular expression pattern.

**Parameters:**
- `pattern` (required): Regex pattern to match
- `group` (optional): Capture group to extract (default: 1)

**Example:**
```json
{
  "css": "span::text",
  "processors": [
    {"type": "regex", "pattern": "Price: \\$([\\d.]+)"}
  ]
}
```

**Input → Output:**
```
"Price: $99.99" → "99.99"
```

**Multiple groups:**
```json
{
  "css": "span::text",
  "processors": [
    {"type": "regex", "pattern": "(\\d+) items", "group": 1}
  ]
}
```

**Returns original value if no match.**

**Works on:** Strings only

---

### 4. cast

Convert value to specified type.

**Parameters:**
- `to` (required): Target type - `"int"`, `"float"`, `"bool"`, or `"str"`

**Example:**
```json
{
  "css": "span.rating::attr(data-rating)",
  "processors": [
    {"type": "cast", "to": "float"}
  ]
}
```

**Input → Output:**
```
"4.5" → 4.5
"42" → 42 (for int)
"true" → True (for bool)
```

**Boolean conversion:**
- `true`, `1`, `yes`, `on` → True
- Everything else → False

**Returns None if conversion fails.**

**Works on:** Any type

---

### 5. join

Join list values into a single string.

**Parameters:**
- `separator` (optional): String to join with (default: `" "`)

**Example:**
```json
{
  "css": "li.feature::text",
  "get_all": true,
  "processors": [
    {"type": "join", "separator": ", "}
  ]
}
```

**Input → Output:**
```
["WiFi", "Bluetooth", "GPS"] → "WiFi, Bluetooth, GPS"
```

**Filters out None values automatically.**

**Works on:** Lists only

---

### 6. default

Return default value if input is None, empty string, or empty list.

**Parameters:**
- `default` (required): Fallback value

**Example:**
```json
{
  "css": "span.optional::text",
  "processors": [
    {"type": "default", "default": "N/A"}
  ]
}
```

**Input → Output:**
```
None → "N/A"
"" → "N/A"
[] → "N/A"
"actual value" → "actual value"
```

**Works on:** Any type

---

### 7. lowercase

Convert strings to lowercase.

**Parameters:** None

**Example:**
```json
{
  "css": "span.status::text",
  "processors": [
    {"type": "strip"},
    {"type": "lowercase"}
  ]
}
```

**Input → Output:**
```
"IN STOCK" → "in stock"
```

**Works on:** Strings and lists of strings

---

### 8. parse_datetime

Parse datetime string into ISO format.

**Parameters:**
- `format` (optional): strptime format string (if None, uses dateutil parser for flexible parsing)

**Example with format:**
```json
{
  "css": "time.date::attr(datetime)",
  "processors": [
    {"type": "parse_datetime", "format": "%Y-%m-%d"}
  ]
}
```

**Example without format (auto-detect):**
```json
{
  "css": "span.date::text",
  "processors": [
    {"type": "parse_datetime"}
  ]
}
```

**Input → Output:**
```
"2024-02-24" → "2024-02-24T00:00:00" (ISO format)
"February 24, 2024" → "2024-02-24T00:00:00"
"24/02/2024" → "2024-02-24T00:00:00" (auto-detected)
```

**Stored as ISO string in database (automatically serialized).**

**Returns None if parsing fails.**

**Works on:** Strings only

---

## Processor Chaining

Processors run sequentially. Output of one becomes input to the next.

### Example 1: Clean and Convert Price

```json
{
  "css": "span.price::text",
  "processors": [
    {"type": "strip"},                        // "  $99.99  " → "$99.99"
    {"type": "replace", "old": "$", "new": ""},  // "$99.99" → "99.99"
    {"type": "cast", "to": "float"}           // "99.99" → 99.99
  ]
}
```

### Example 2: Extract Rating Number

```json
{
  "css": "div.rating::text",
  "processors": [
    {"type": "strip"},                        // "  Rating: 4.5 stars  " → "Rating: 4.5 stars"
    {"type": "regex", "pattern": "([\\d.]+)"}, // "Rating: 4.5 stars" → "4.5"
    {"type": "cast", "to": "float"}           // "4.5" → 4.5
  ]
}
```

### Example 3: Normalize Text

```json
{
  "css": "span.status::text",
  "processors": [
    {"type": "strip"},
    {"type": "lowercase"},
    {"type": "replace", "old": " ", "new": "_"}
  ]
}
```
**Input:** `"  In Stock  "`
**Output:** `"in_stock"`

### Example 4: Handle Missing Values

```json
{
  "css": "span.optional-field::text",
  "processors": [
    {"type": "strip"},
    {"type": "default", "default": "Not specified"}
  ]
}
```

---

## Error Handling

Processors handle errors gracefully:

- **strip, replace, lowercase, join:** Return original value if not applicable type
- **regex:** Returns original value if pattern doesn't match
- **cast:** Returns None if conversion fails
- **parse_datetime:** Returns None if parsing fails
- **Unknown processor type:** Skipped, logs warning

**This means:** If a processor fails mid-chain, subsequent processors receive the last valid value or None.

---

## Common Patterns

### Extracting Currency Values

```json
{
  "css": "span.price::text",
  "processors": [
    {"type": "strip"},
    {"type": "regex", "pattern": "\\$([\\d,.]+)"},
    {"type": "replace", "old": ",", "new": ""},
    {"type": "cast", "to": "float"}
  ]
}
```
**Handles:** `"$1,299.99"`, `"Price: $99"`, `"  $42.50  "`

### Extracting Numbers from Text

```json
{
  "css": "div.quantity::text",
  "processors": [
    {"type": "regex", "pattern": "(\\d+)"},
    {"type": "cast", "to": "int"}
  ]
}
```
**Handles:** `"23 items"`, `"Quantity: 5"`, `"42"`

### Boolean Fields

```json
{
  "css": "span.availability::text",
  "processors": [
    {"type": "lowercase"},
    {"type": "regex", "pattern": "(in stock|available)"},
    {"type": "cast", "to": "bool"}
  ]
}
```
**Returns:** `True` if "in stock" or "available", else `False`

### Date Fields

```json
{
  "css": "time::attr(datetime)",
  "processors": [
    {"type": "parse_datetime"}
  ]
}
```
**Auto-detects format, stores as ISO string.**

### Lists to Comma-Separated String

```json
{
  "css": "li.tag::text",
  "get_all": true,
  "processors": [
    {"type": "join", "separator": ", "}
  ]
}
```
**Input:** `["Python", "Web Scraping", "Automation"]`
**Output:** `"Python, Web Scraping, Automation"`

---

## Tips

1. **Always strip text fields** - Prevents whitespace issues
2. **Use regex before cast** - Extract numeric part first, then convert type
3. **Chain replace for complex cleaning** - Multiple replace processors handle different cases
4. **Default at the end** - Apply fallback after all transformations
5. **Test selectors first** - Use `./scrapai analyze --test "selector"` before adding processors
6. **Validate processor output** - Run `--limit 5` crawl and check with `show` command
