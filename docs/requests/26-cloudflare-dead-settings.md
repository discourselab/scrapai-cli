# Change request: warn on the five Cloudflare settings nothing reads

- **Status:** IMPLEMENTED IN THIS INSTANCE (2026-09-18; corrected 2026-10-20)
- **File:** `cli/spiders.py` — `DEAD_SETTINGS`, `import_spider`; `cli/crawl.py` — the missing-Xvfb message
- **Type:** framework change (dead settings + misleading docs)
- **Requested by:** @MirjamOdile
- **Docs made wrong:** none. Corrected here because they described the dead settings as working: `docs/cloudflare.md`, and the template under `templates/cloudflare/` (`sections.md`, `test_spider.json`, `final_spider.json`).

## Problem

`docs/cloudflare.md` lists five Cloudflare settings that nothing in the codebase reads: `CLOUDFLARE_HEADLESS`, `CLOUDFLARE_COOKIE_REFRESH_THRESHOLD`, `CF_MAX_RETRIES`, `CF_RETRY_INTERVAL`, `CF_POST_DELAY`. They validate (the settings schema allows extra keys), `spiders import` stores them as `SpiderSetting` rows and `spiders/base.py` copies them into `crawler.settings`, so they read back as configuration in force.

The docs also describe behaviour that does not exist: "Auto-refresh cookies every 10 minutes (configurable)", while the handler re-verifies only when a host has no cookie yet or a response comes back blocked. The shipped Cloudflare template sets four of the dead keys, and `cli/crawl.py`'s missing-Xvfb error tells the user to set `CLOUDFLARE_HEADLESS=true`.

## Correction (2026-10-20)

The first version of this request (2026-09-18) also removed `CLOUDFLARE_STRATEGY` from `core/schemas.py` and listed it, `CF_WAIT_SELECTOR` and `CF_WAIT_TIMEOUT` as dead. It was cut from `main` at `2ed37dc`, which deleted the old `browser_only` code. Upstream `main` then merged #22 (`f85679d`, 2026-08-26), which brings `browser_only` back through the shared browser service: `CloudflareDownloadHandler.download_request` reads `CLOUDFLARE_STRATEGY`, and `_verify_via_service` reads `CF_WAIT_SELECTOR` and `CF_WAIT_TIMEOUT`. Those three are live, so the branch was rebased on `main` and they were taken out of this request: the schema field and its validator stay as `main` has them, and the docs for browser-only mode and `CF_WAIT_SELECTOR` are left as they are.

## Change

- `cli/spiders.py`: `DEAD_SETTINGS` maps each of the five keys to why it does nothing; `spiders import` prints `⚠️ '<key>' has no effect (<reason>); remove it`. The check runs outside the validation branch, so it also fires under `--skip-validation`.
- `cli/crawl.py`: the missing-Xvfb error offers `CURL_CFFI_ENABLED` as the second option instead of the dead `CLOUDFLARE_HEADLESS`.
- `docs/cloudflare.md`: the five keys move from the settings table to an "Accepted but not read" table; the cookie re-verification text matches the handler; the `CF_WAIT_SELECTOR` entries say it applies only to pages the browser renders in hybrid mode.
- Template: the four dead keys are removed from `final_spider.json`, `test_spider.json` and `sections.md`, so the shipped template no longer trips the warning on import.

## Trade-offs

- A warning, not a rejection: old configs keep importing.
- Rejected: `warnings.warn` in the schema. It would not fire under `--skip-validation`, and `pytest.ini` sets `-p no:warnings`.

## Verification

- `tests/unit/test_input_validation.py`: `test_dead_settings_are_not_schema_fields`, and `test_dead_settings_have_no_reader`, which scans the framework's `.py` files (outside `tests/` and the warning itself) for every `DEAD_SETTINGS` key. The second fails on the first version of this request, which listed `CLOUDFLARE_STRATEGY` and `CF_WAIT_*` while `handlers/cloudflare_handler.py` read them. `main`'s two `CLOUDFLARE_STRATEGY` validator tests are kept.
