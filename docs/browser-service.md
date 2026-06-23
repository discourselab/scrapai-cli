# Persistent Browser Service

An optional background browser that `inspect` reuses instead of cold-starting a
fresh browser on every call. For Cloudflare-protected sites the cold-start cost
is large (launch browser + solve the challenge, ~10-15s each time). The service
pays that once and keeps the browser warm, so repeated inspects — and several
agents inspecting different sites at once — are far faster.

## When to use it

Start it when a session will do **many browser inspects**:

- Repeated `inspect --screenshot` across a site's sections and sample pages.
- Cloudflare/JS sites where every `inspect` would otherwise cold-start a browser.
- **Parallel processing** — several agents each inspecting a *different* site.

For a one-off inspect you don't need it; `inspect` cold-starts a browser on its
own and works exactly as before.

## Commands

```bash
./scrapai browser start [--pool 5] [--proxy-type auto]   # launch the warm browser
./scrapai browser status                                  # running? pid/port
./scrapai browser stop                                    # shut it down
./scrapai browser shot <url> --project <name> [--screens N]  # screenshot via the service
```

- `--pool N` — max sites open at once (default 5; matches the max-5 parallel
  queue limit). Each site is one tab.
- `--proxy-type` — any proxy configured in `.env` (or `auto`/`none`).
- On a headless server the browser runs under Xvfb automatically — no windows,
  no `xvfb-run` needed.

## How `inspect` uses it

Nothing changes in how you call `inspect`. When the service is running,
`inspect` (and the `--screenshot` / `--browser` paths, and the auto-escalation
from HTTP → curl_cffi → browser) **route through the service automatically** —
no separate browser, no subprocess, no Xvfb. When the service is **not**
running, `inspect` cold-starts its own browser exactly as before. It is a pure
speed-up; behaviour and output (`page.html`, `page.png`, transport report) are
identical either way.

## How it works

- **One browser, one window.** The service launches a single browser. Each site
  gets its own **tab** in that one window.
- **One tab per site (domain-sticky).** A site reuses its tab and its
  already-solved Cloudflare session, so the second inspect of a site skips the
  challenge and is much faster. Different sites get different tabs and solve
  Cloudflare concurrently without interfering.
- **LRU eviction.** When more than `--pool` sites are in play, the
  least-recently-used tab is closed.

Memory: one shared browser for, say, 5 sites uses roughly **half** of what 5
separate browsers would (one browser baseline instead of five).

## Parallel processing

Before processing multiple sites in parallel, start the service once:

```bash
./scrapai browser start
```

Each agent's `inspect` then shares the one browser (one tab per site) instead of
launching its own. Run `./scrapai browser stop` when the batch is done.

## Caveat

Because all tabs share one browser session, if a site needs to **switch proxies
mid-solve** (only when Cloudflare blocks *and* a proxy chain is configured) it
can disturb other tabs. With direct connections — the normal case — this does
not happen.
