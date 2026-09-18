# 25 — `parse_datetime` `languages` silently discards dates it could parse

**Requested by:** MirjamOdile (2026-09-18)
**Type:** bugfix (`core/processors.py`) + docs
**Status:** implemented locally; ships as its own PR

## Problem

`languages` reads as a hint and is documented as one — `docs/processors.md:226` called it a
hint that "speeds parsing and disambiguates locales", with
`{"type": "parse_datetime", "languages": ["de"]}` shown as the recommended shape. The
docstring at `core/processors.py` said the same.

It is passed straight to `dateparser`, where it **restricts** the candidate set. A value
that doesn't match the page makes parsing return `None`, and the existing `dateutil`
fallback cannot rescue a non-English month name, so the row is quarantined for a missing
date. Measured before the change:

| value | `languages` | result |
|---|---|---|
| `"15. Januar 2024"` | `["de"]` | parses |
| `"15. Januar 2024"` | omitted | parses (auto-detect) |
| `"15. Januar 2024"` | `["en"]` | `None` |

The middle row is the point: `dateparser` can read the value unaided, and setting the
option is what stops it. Because the doc recommended setting it, a null `published_date`
gets diagnosed as "the month name isn't English" — the opposite of the cause — and the
option that produced the failure looks like the thing that should fix it.

## Change (`core/processors.py`)

When `languages` is set and `dateparser` returns `None`, retry once without it before
falling through to `dateutil`:

```python
if parsed is None and languages:
    parsed = _dateparser.parse(value, settings={"DATE_ORDER": "MDY"})
```

`languages` becomes what it reads as: a preference tried first, not a filter. A wrong
value now costs one extra parse attempt instead of the date. `DATE_ORDER="MDY"` is pinned
on both attempts, so ambiguous numeric dates resolve identically either way and no
currently-parsing date changes value.

Docstring and `docs/processors.md` updated to describe the behaviour. Two tests added: a
mismatched `languages` value parses, and auto-detect reads a non-English month unaided.

## Impact

- A spider with a wrong or stale `languages` value starts extracting dates it previously
  dropped. No date that parses today changes.
- Text around the date (`Veröffentlicht am …`) still defeats parsing in any language; that
  is a separate problem and the docs point at `replace`/`regex` for it.
