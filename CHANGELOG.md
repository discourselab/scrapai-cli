# Changelog

All notable changes to ScrapAI will be documented in this file.

## [Unreleased]

### Added

- **Incremental crawling with DeltaFetch** - Skip already-crawled URLs across sessions
  - Enabled by default for all crawls
  - Per-spider, per-project isolation (no collisions)
  - `--reset-deltafetch` flag to start fresh

- **New CLI flags for better control:**
  - `--browser` - Enable JS rendering and Cloudflare bypass
  - `--scrapy-args` - Pass any Scrapy setting directly (e.g., `-s CONCURRENT_REQUESTS=32`)
  - `--save-html` - Include raw HTML in output files (off by default)
  - `--reset-deltafetch` - Clear URL cache to re-crawl everything

- **Checkpoint pause/resume for production crawls:**
  - Press Ctrl+C to pause, run same command to resume
  - Automatically cleans up on successful completion
  - Date-based output filenames (one file per day, appends if run multiple times)

### Changed

- **CloakBrowser replaces nodriver for Cloudflare bypass**
  - **Visible browser by default** for easier debugging (Xvfb auto-used on headless servers)
  - Superior stealth: 0.9 reCAPTCHA score (vs 0.5-0.7)
  - Passes FingerprintJS, BrowserScan, Cloudflare Turnstile (30/30 tests)
  - Source-level C++ patches (more reliable, survives Chrome updates)
  - Platform: Linux, macOS, Windows (via WSL or Docker)
  - Migration: Existing configs work unchanged

- **Improved platform detection** - Switched to `platform.system()` for better WSL and cross-platform support

- **HTML storage disabled by default** - 90% smaller output files (use `--save-html` to include)

- **Output filenames now date-based** - `crawl_28022026.jsonl` (no time), multiple runs same day append to same file

### Fixed

- **Race conditions in Cloudflare handler** - Multiple requests no longer trigger simultaneous cookie refreshes
- **Checkpoint corruption detection** - Auto-fixes Scrapy bug #4106 (dupefilter persists but queue doesn't)
- **DeltaFetch path isolation** - Per-project databases prevent spider name collisions
- **Checkpoint resume creates new files** - Now reuses same output file when resuming
- **Reset DeltaFetch not clearing checkpoint** - Now clears both for true fresh start
- **Browser event loop errors** - Fixed "Task got Future attached to different loop" on cleanup

### Performance

- **Faster incremental crawls** - DeltaFetch skips already-seen URLs (10x+ speedup on repeat runs)
- **Smaller output files** - HTML disabled by default (50KB vs 5MB per 100 articles)
- **No more hanging crawls** - Race condition fix prevents 0 pages/0 items hangs

See [CHANGES.md](CHANGES.md) for technical details and [docs/cloudflare.md](docs/cloudflare.md) for Cloudflare setup.
