# Change request: spider name-vs-domain mismatch is a warning, not a hard block

- **Status:** RE-APPLIED IN THIS INSTANCE on upstream's rewritten `import_spider()` (2026-07-09). Proven REQUIRED during the gscc_batch_0 migration: upstream's hard block rejected the legitimate secondary spider `nsefi_in_pdfindex`; with the warning it imports cleanly. Any fleet with more than one spider per domain needs this.
- **File:** `cli/spiders.py` — `import_spider()`
- **Type:** framework change (CLI import validation)

## Problem

`spiders import` rejected (with `return`) any spider whose `name` did not equal its domain with dots replaced by underscores. But a single domain legitimately hosts **more than one spider**:
- `noaa_gov` + `noaa_gov_gc` (General Counsel section of the same site),
- a subdomain grouped under the parent, e.g. `ncei.noaa.gov` → `noaa_gov_ncei`.

Crawls and analysis both key off the spider **name** consistently, so a name that differs from the domain doesn't actually scatter anything. The hard block forced these legitimate sub-spiders to drop `source_url` to sneak past validation — losing provenance.

## Change

Downgrade the mismatch from a hard error (`❌ … return`) to a non-blocking warning:

```
⚠️  Spider name '<name>' differs from its domain ('<expected>') — fine for a
    secondary or sub-domain spider. Data will live under data/<project>/<name>/.
```

Import proceeds. The name remains the single source of truth for where data lives.

## Notes
- No loss of safety: the warning still surfaces genuine typos; the operator decides.
- Enables `source_url` to be kept on sub-spiders (better provenance + compliance capture, which derives the site root from `source_url`).
