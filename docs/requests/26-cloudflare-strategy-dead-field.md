# 26 — Cloudflare settings surface: 8 of 12 documented knobs are read by nothing

**Requested by:** MirjamOdile (2026-09-18)
**Type:** bug (dead settings + misleading docs); completes the unfinished half of `2ed37dc`
**Status:** implemented locally (`core/schemas.py`, `cli/spiders.py`, `cli/crawl.py`,
`docs/cloudflare.md`, example configs, template spider JSON, tests)

## Problem

`docs/cloudflare.md`'s settings table lists 12 settings. **Four are real**
(`CLOUDFLARE_ENABLED`, `BROWSER_ENABLED`, `CURL_CFFI_ENABLED`,
`CONCURRENT_REQUESTS`). The other eight have **zero readers** outside the schema
and tests:

`CLOUDFLARE_STRATEGY` · `CLOUDFLARE_HEADLESS` ·
`CLOUDFLARE_COOKIE_REFRESH_THRESHOLD` · `CF_MAX_RETRIES` · `CF_RETRY_INTERVAL` ·
`CF_POST_DELAY` · `CF_WAIT_SELECTOR` · `CF_WAIT_TIMEOUT`

They are not inert-but-harmless. `spiders/base.py` copies every key into
`crawler.settings` and `cli/spiders.py` stores them as `SpiderSetting` rows, so they
reach the crawl, get stored, and read back as configuration that is in force.

`CLOUDFLARE_STRATEGY` also carried a validator accepting `hybrid` / `browser_only`,
which made a dead value look load-bearing — worse than an unknown key, which is
at least obviously ignored.

### This is an unfinished removal, not a field that never worked

`browser_only` was real. `2ed37dc` ("delete dead browser_only strategy",
2026-07-25) removed `_browser_only_fetch_*`, `_ensure_browser_started` and
`_fetch_with_browser`. Its own message:

> Hybrid is now the only (and default) path; configs still declaring
> browser_only validate and get hybrid. **CLOUDFLARE_STRATEGY knob itself is
> removed at the rename step.**

The rename step never happened. This request is that step.

### The docs kept describing the deleted mode

`docs/cloudflare.md` still carried a **Browser-Only Mode** section ("keeps
browser open for every request"), told users under *Blocked Despite Cookies* to
"Switch to browser-only mode", listed it under *Performance Tips* as the
fallback for tough sites, and at `:165` recommended trying it when debugging.
`handlers/cloudflare_handler.py:179` returns `_hybrid_fetch_sync`
unconditionally — there is no branch.

Two further false claims found alongside:

- "**Auto-refresh cookies** every 10 minutes (configurable)" — the handler's own
  docstring (`cloudflare_handler.py:201`) says *"No time-based reverify"*.
  Re-verification happens only on first sight of a host or after a blocked
  response, and no interval is configurable.
- `cli/crawl.py` offered, as fix option 2 for a headless server, *"Add to spider
  settings: CLOUDFLARE_HEADLESS=true"* — telling the user to set a setting
  nothing reads.

## Change

**`core/schemas.py`** — `CLOUDFLARE_STRATEGY` field and
`validate_cloudflare_strategy` deleted. `SpiderSettingsSchema` sets
`extra="allow"`, so a config still declaring it imports unchanged and carries it
as an ignored extra; nothing breaks.

**`cli/spiders.py`** — `DEAD_SETTINGS` maps each dead key to why it does nothing;
`spiders import` prints `⚠️ '<key>' has no effect (<reason>); remove it`.
Deliberately placed outside the validation branch so it also fires under
`--skip-validation`, which a schema-level check would have skipped. Uses the
`click.echo` warning convention already in that file rather than `warnings.warn`,
which would have emitted a `schemas.py:NNN: UserWarning` prefix unlike every
sibling message.

**`docs/cloudflare.md`** — states that hybrid is the only Cloudflare path; the
dead keys are listed in an explicit **"Accepted but not read"** table; the
cookie-reuse description matches the handler; troubleshooting points at
`--proxy-type` and `CURL_CFFI_ENABLED`.

**`cli/crawl.py`** — the missing-Xvfb error now offers `CURL_CFFI_ENABLED` as
the second option instead of a dead setting. (It cannot suggest `xvfb-run`: that
branch runs precisely when `xvfb-run` is absent, and the CLI already prepends it
automatically when present.)

**Example configs and templates** — removed from `docs/settings.md`,
`docs/deltafetch.md`, `docs/sitemap.md`, and from the reference template's
`sections.md`, `test_spider.json` and `final_spider.json`. The JSON files matter:
`final_spider.json` is the canonical importable artifact, so the shipped template
would otherwise have tripped the new warning on import.

**`tests/unit/test_input_validation.py`** — the two tests asserting the old
validator are replaced by one asserting the field is gone and old configs still
import, and one asserting every `DEAD_SETTINGS` key is absent from
`model_fields` (so a key re-declared as a schema field fails the test rather
than silently disagreeing with the warning).

## Note for review

`pytest.ini:23` sets `-p no:warnings`, so a `warnings.warn`-based approach would
not have been covered by the suite at all. The printed warning is asserted
structurally instead.

## Files

`core/schemas.py`, `cli/spiders.py`, `cli/crawl.py`,
`tests/unit/test_input_validation.py`, `docs/cloudflare.md`, `docs/settings.md`,
`docs/deltafetch.md`, `docs/sitemap.md`,
`templates/cloudflare/thefga_org/analysis/{sections.md,test_spider.json,final_spider.json}`.

## Scope

Schema, import path and CLI output all change here, so this reviews and reverts
on its own.
