---
description: Diagnose a slow / stalled / blocked spider and propose config fixes (final_spider.json only, apply on approval)
argument-hint: <project> <spider> [spider ...]
---

You are running `/spider-slow`. Arguments given: `$ARGUMENTS`

> **HARD CONSTRAINT — if (and only if) the user approves a fix, the ONLY file you may change is that spider's own `final_spider.json`** (`data/<project>/<spider>/analysis/final_spider.json`), applied via `./scrapai spiders import`. You must NOT edit `.env`, `settings.py` or any Scrapy/framework setting, framework code, spider Python, or any other project file. **Never run, kill, or restart the crawl process yourself, and never run a full crawl** — pausing (production crawls run DETACHED under Pueue: `pueue kill <id>` sends a graceful stop, checkpoint saved), resuming, and any full/production crawl are the USER's to perform. You DIRECT the user when to pause and resume; you may only run BOUNDED single-URL probes and `--limit 5` re-tests yourself.

**What good looks like:** a clear classification (slow / stalled / blocked), the *real* bottleneck identified from evidence (not guessed), and a short ordered list of proposed `final_spider.json` fixes — applied only on the user's go-ahead, each re-tested so it doesn't drop valid content. Then the right recovery path: **prefer the fast path — pause, fix, resume from checkpoint** (saves re-crawling everything) — and reserve a clean restart for when the frontier/output is genuinely polluted (junk URLs already queued). Diagnose, don't thrash: a flatline is not proof of a block.

## Argument handling (do this FIRST)

- The **first** token is the project name. It MUST exactly match an existing project (`./scrapai projects list`). If missing or not an exact match, **STOP and ask** — never assume or default.
- The **remaining** tokens are the slow spider(s). "Slow" is not an audit category, so there is no whole-table default: if no spider is named, ask the user which spider is slow. If more than one, process in BATCHES of ≤5 (one Task agent per spider, embed these Rules + Procedure in each).

## Rules (strict)

- **PROPOSE, then apply on go-ahead.** Diagnose fully and propose fixes with evidence; apply to `final_spider.json` (and re-import) only after the user's explicit approval. Bounded probes and `--limit 5` re-tests are always allowed.
- **SPIDER-LEVEL ONLY, with push-back before deferring.** Every approved change lands in the spider's `final_spider.json`, re-imported (`./scrapai spiders import … --project <project>`) — never `.env`, settings, framework, or spider Python. Before concluding a fix can't be done at the spider level, re-attempt from a different angle, then once more; only then defer, stating what you tried.
- **Re-ban hygiene.** If you suspect a block/ban, do NOT keep probing — repeated fetches deepen the ban. One bounded probe, then stop and reason. After a ban: fix the URL patterns, advise a cooldown, and confirm recovery later with a SINGLE clean probe (a real content page, not an error page).
- The crawl may be LIVE while you diagnose (running detached under Pueue) — read the in-progress output and `pueue follow <id>` the log; never `pueue kill/pause/restart` anything yourself. Fixes are for the user's NEXT run.

## Procedure

Apply only the steps that bear on this spider's symptom — a step that doesn't apply gets a one-line "N/A (why)". Lead with reasoning, not box-ticking.

0. **Measure first (don't guess)** — classify before fixing; the fixes differ:
   - START with `./scrapai crawl-status <spider>` — it joins Pueue run-state with the crawl file: state (running/queued/done/failed), downloaded, with-content %, and **last-item** (time since the last item — the stall signal). `pueue status` shows the queue; `pueue follow <id>` streams the live log.
   - Finer rate over time when needed: items in the last 10 / 30 min — e.g. `./scrapai db query "SELECT COUNT(*) FROM scraped_items si JOIN spiders s ON si.spider_id=s.id WHERE s.project='<project>' AND s.name='<spider>' AND si.scraped_at > datetime('now','-10 minutes')"`, plus the max `scraped_at`; cross-check `crawls/*.jsonl` size/mtime.
   - **Slow** = items still flowing, low rate. **Stalled** = process alive, ~0 new items for a long stretch. **Blocked** = stalled + challenges / 403 / 429 / access errors.

1. **Kill junk / runaway URLs (usually the biggest win)** — group crawled URLs (from output + the checkpoint frontier) by host/pattern; find noise: `mailto:` / email-as-URL, infinite path variants, calendar/pagination loops, session-id explosion. A bloated checkpoint (tens of MB — `du -sh data/<project>/<spider>/checkpoint`) signals URL explosion. Propose `deny` rules for the junk patterns (inspect a sample first so a deny can't drop real content). This cuts fetch load and avoids tripping bot-detection.

2. **Find the real bottleneck**
   - **Browser-render overhead:** with `BROWSER_ENABLED` / `CLOUDFLARE_ENABLED`, each request can take 10–30s. Probe one content page with `./scrapai inspect <url>` (lightweight, no browser) vs `./scrapai inspect <url> --browser`. If the lightweight fetch returns fast, valid HTML → the site is server-rendered / lightly protected and the browser is pure overhead. Propose splitting responsibilities: browser only for JS-heavy listing/discovery (`PAGINATED_LISTINGS`), and `CURL_CFFI_ENABLED` (Chrome TLS impersonation) for content fetch. **Caveat:** do NOT propose `CURL_CFFI_ENABLED` on a `USE_SITEMAP` spider — it breaks sitemap parsing; for a blocked sitemap site use the Cloudflare hybrid instead.
   - **Over-broad scope:** patterns like `/report/.+` can explode into full-site traversal — propose tightening to the actual content units.
   - **Rate-limit / block suspicion** → step 3.

3. **Probe before concluding "blocked"** — a flatline is not evidence of a block. Fetch ONE URL independently (`./scrapai inspect <url>`, add `--browser` / `--proxy-type` only if warranted) and read it:
   - ~6 KB "Access denied" page → IP ban / aggressive blocking (usually from over-crawling).
   - large page, empty or generic → JS challenge or a broken render session.
   - real content → it's a crawl-side issue (hang, config, concurrency, or pipeline stall), not the site.

4. **Common false "slow" causes**
   - **Autothrottle + browser mismatch:** renders get read as a slow server → AutoThrottle compounds the delay. For browser/`curl_cffi` crawls, propose disabling AutoThrottle and using a fixed `DOWNLOAD_DELAY`. (Exception: if step 3 shows the site bans under load, do the opposite — throttle DOWN: lower concurrency / add delay.)
   - **Concurrency misconfiguration:** browser-heavy crawls behave serially, so raising concurrency may not help; too low leaves idle slots.
   - **Duplicate inflation:** repeated runs or browser double-fetch. Check timestamps; if duplicates are already in the output, that points to Path B (clean restart with `--reset-deltafetch`) in step 8.

5. **Fix order (highest leverage first)** — when proposing, order them: (1) remove junk URL patterns; (2) reduce browser usage (`curl_cffi` where possible, browser only for JS discovery); (3) tighten `allow`/`start_urls` to real content units; (4) set fixed pacing (delay + moderate concurrency, AutoThrottle off — unless banned-under-load, then throttle down); (5) only then accept site limits or recommend external infrastructure (CF-bypass / API). Each approved fix is verified by a bounded `--limit 5` re-test confirming required fields still populate (a scope/deny change must not drop valid content).

5b. **Choose the recovery path** — decide, with reasons, which the user should do after approving fixes:
   - **Resume (fast path)** — when the discovered URL set is sound and the fixes are about *how* pages are fetched/handled (browser→curl_cffi, pacing, concurrency, a selector/extraction fix). The existing checkpoint frontier is fine, so a pause→fix→resume picks up the new config on remaining + newly-discovered requests and saves re-crawling everything. **Caveat:** new `deny`/scope rules only affect URLs discovered AFTER resume — URLs ALREADY queued in the checkpoint are still processed.
   - **Clean restart** — when the frontier/output is already polluted (junk URLs / emails / loops queued, a bloated checkpoint), or scope/deny changes need to drop URLs already discovered. Resume would carry the junk forward, so the checkpoint + deltafetch must be cleared. (This is the email-explosion case: clean and restart.)
   Rule of thumb: junk already in the frontier → clean restart; fetch/pacing/extraction fix on a sound frontier → resume.

6. **Report (BLUF)** — 3-line verdict: classification (slow / stalled / blocked) · the real bottleneck · confidence. Then: the rate/measurement evidence; junk-URL findings; bottleneck probe results; proposed fixes in priority order (each with evidence + whether re-tested); and the chosen recovery path (resume vs clean restart) with the exact commands from step 8.

7. **Self-critique** — did I call it "blocked" on a flatline without an independent probe? did I over-probe a banned site? would a proposed deny/scope change drop real content? is the bottleneck the site or my crawl config? Revise only on concrete evidence.

8. **Recovery handover (the user runs these; you only apply the fix in between).** Once fixes are approved, give the user the path chosen in 5b. In BOTH paths you apply the approved change while the crawl is paused: the user Ctrl+C's the crawl (checkpoint auto-saves and the process exits), THEN you re-import the edited `final_spider.json`, THEN the user runs the resume / restart command. Sequence and print exactly one path:

    **Path A — pause → fix → resume (fast; sound frontier):**
    1. User: find the task (`pueue status`, label `scrapai:<project>:<spider>`) and stop it gracefully — `pueue kill <id>` (one graceful stop; the checkpoint is saved). (A rare foreground crawl: **Ctrl+C** once.)
    2. You: apply the approved fix to `final_spider.json` and `./scrapai spiders import <file> --project <project>`.
    3. User: re-run the SAME command — it resumes from the checkpoint with the new config:
       ```bash
       ./scrapai crawl <spider> --project <project>
       ```
       (It re-enqueues into Pueue and resumes from the checkpoint. New deny/scope rules apply only to URLs discovered after resume; already-queued URLs still run — if that's not good enough, use Path B.)

    **Path B — clean restart (polluted frontier: junk/emails/loops already queued).** PRINT, do NOT execute — deletion is the user's job. `--reset-deltafetch` clears `.scrapy/deltafetch` + the checkpoint, so don't delete those manually:
    1. User: `pueue kill <id>` (or **Ctrl+C** a foreground crawl) and wait for exit.
    2. You: apply the fix + `spiders import`.
    3. User: run the clean block, then the reset crawl:
       ```bash
       # Clean restart for <spider> in <project> — run this yourself.
       rm -f  data/<project>/<spider>/crawls/*.jsonl            # junk/stale crawl output
       rm -f  data/<project>/_audit/crawl_stats/<spider>.json   # stale audit stats
       rm -f  data/<project>/_audit/scan_cache/<spider>.json    # stale crawl-scan cache
       rm -rf data/<project>/_audit/sitemap_cache/<spider>_*    # stale sitemap cache
       ./scrapai crawl <spider> --project <project> --reset-deltafetch
       ```
