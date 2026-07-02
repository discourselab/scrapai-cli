# Authenticated sessions

Scrape content behind a login (paywalls, members-only areas, social sites) by
reusing a login the **human** performs once. scrapai **never types a password**
and stores no credentials. It captures the resulting browser session (cookies +
localStorage) and replays it so later crawls start already logged in.

## The model

- A **session** is a saved `storage_state` file at `~/.scrapai/sessions/<name>.json`
  (mode `0600`, owner-readable only). Override the directory with the
  `SCRAPAI_SESSIONS_DIR` env var.
- Sessions are **global and per-site.** One `nytimes_com` login serves every
  spider and every project that scrapes NYT — a login is not project-specific, so
  it is never duplicated under a project.
- **Name a session after its domain, like a spider** (`nytimes_com`,
  `thefga_org`). You may use other names (e.g. `nytimes_com_work` for a second
  account on the same site), but the domain is the convention.
- Only the **one** session you point a crawl/inspect at is ever loaded — never
  all of them. So a scraped site's browser context contains only its own login,
  nothing else.

## The full flow, end to end

What actually happens, from a gated URL to a running authenticated crawl:

1. **QA the paywall anonymously first.** Inspect an article without a session. If
   the full text is already in the HTML (a *soft* paywall), you need no login at
   all. If you get a login/paywall stub (a *hard* paywall — e.g. a page titled
   "Muro de pago"), continue. This one check saves you from spending a manual
   login on a site that never needed one.
2. **Capture the login** — `session login <name>` opens a browser; the **human**
   logs in and closes the window. scrapai saves the resulting cookies +
   localStorage to `~/.scrapai/sessions/<name>.json`. No password is typed.
3. **Verify it took** — `session check <name> <gated-url>` loads the saved file,
   opens the gated page, and saves a PNG. Read the PNG: you should see the logged-in
   page (account name in the corner, full article), not the paywall.
4. **Configure the spider** — set `"SESSION": "<name>"` plus a browser transport
   (see below). Point Phase-2 inspects at `--session <name> --browser`.
5. **The crawl reads the file — it does NOT log in again.** `SESSION` makes the
   browser load that saved `storage_state` into its context, so the lane starts
   already authenticated. On a hybrid crawl it then solves Cloudflare once, hands
   the cookies (login + CF clearance) to curl_cffi, and fetches the rest over fast
   HTTP. `session login`/`session check` are **one-off human commands** the crawl
   never runs.
6. **Guard against silent expiry** — set `SESSION_EXPIRED_SIGNAL` so a lapsed login
   stops the crawl loudly instead of quarantining every row (see below).

## Commands

```bash
scrapai session login <name> [url]    # capture a login (see below)
scrapai session check <name> <url>    # confirm: open a gated URL, save a PNG to view
scrapai session list                  # list saved sessions
scrapai session remove <name>         # delete a session
```

### `session login` — capture (human-in-the-loop)

```bash
scrapai session login nytimes_com https://www.nytimes.com/
```

A browser window opens. **The user logs in by hand** (including any 2FA or
"Sign in with Google"). When logged in, the user **closes the window** — that
captures the session. No password is typed and no Enter is needed, so the same
flow works headless/remote.

Re-running `session login <name>` overwrites the file — that is how you
**refresh** a session once its cookies expire.

### `session check` — confirm with a screenshot

```bash
scrapai session check nytimes_com https://www.nytimes.com/account
scrapai session check x_com https://x.com/home --wait 8     # SPAs need more time
```

Loads the session, opens the gated URL in its own browser context, and saves a
PNG (`~/.scrapai/sessions/<name>_check.png`). Open/Read it to verify you are
actually logged in. `--wait <seconds>` (default 3) is how long to let the page
render before the screenshot — raise it for JS-heavy single-page apps like x.com,
whose timeline takes several seconds to paint (otherwise you screenshot a
loading spinner).

## Using a session in a crawl or inspect

- **Inspect (Phase 1, gated pages):**
  ```bash
  scrapai inspect https://www.nytimes.com/section/world --session nytimes_com --browser --project news
  ```
- **Spider (production crawl):** set the setting so every fetch is authenticated:
  ```json
  { "settings": { "SESSION": "nytimes_com", "CLOUDFLARE_ENABLED": true } }
  ```

It works everywhere the browser is used — the direct crawl path, `inspect`, and
the warm browser service (`browser start`). In the service, each logged-in site
gets its **own isolated lane/context**, and a lane is recreated if its session
changes, so a logged-in lane is never reused unlogged.

### The session only applies in the browser path

A session is a *browser* storage_state — it takes effect only when the browser
fetches the page. This bites in two ways:

- **`inspect` without `--browser`.** `inspect` escalates HTTP → curl_cffi →
  browser and stops at the first transport that returns a 200. On a paywalled
  site, plain HTTP returns the **paywall page** with a valid 200, so `inspect`
  stops there — never reaching the browser, never applying the session. You get
  "Muro de pago", not the article. Force it: `inspect --session <name> --browser`.
- **Choosing the crawl transport.** `SESSION` needs a browser setting to pair with:
  - `"CLOUDFLARE_ENABLED": true` — **hybrid, preferred.** The browser authenticates
    + solves CF once per host, then curl_cffi replays the login cookies over fast
    HTTP. Works when the paywall is enforced **server-side by cookie** (common).
  - `"BROWSER_ENABLED": true` — renders **every** page in the browser. Correct but
    slow; use only when the paywall is enforced client-side by JS and the hybrid
    path returns the stub.

  Test the hybrid first: crawl `--limit 5`; if articles come back with full text,
  keep it. If they come back as the paywall stub, switch to `BROWSER_ENABLED`.

## The agent cannot log in for the user

There is no stored password and the capture is a by-hand step, so an agent
**orchestrates** authentication but cannot perform the login itself:

1. Detect a login wall / paywall while inspecting (anonymous fetch returns the
   login page, not the content).
2. Run `session login <domain>` to open the window.
3. **Ask the user to log in and close the window.**
4. Then `inspect --session <domain>` and set `"SESSION": "<domain>"` on the spider.

## On a server

`session login` opens a real browser window, so it needs a display. On a
headless server, capture the session on a machine that has a display and copy
`~/.scrapai/sessions/<name>.json` to the server (re-copy when it expires). A
remote, in-browser login (noVNC) that would let you log in to a server's browser
from your own browser tab is planned but not yet built.

## Session expiry: stop loud, never silent

A saved login eventually expires. When it does, every fetch silently reverts to
the site's auth-wall page — which has no article, no date. Under a mandatory-date
project schema those rows are quarantined, so a crawl can run for hours
"succeeding" while collecting nothing. To catch this:

```json
{ "settings": { "SESSION": "ladiaria_com_uy", "SESSION_EXPIRED_SIGNAL": "Muro de pago" } }
```

`SESSION_EXPIRED_SIGNAL` is a string that appears on the site's auth-wall page. On
a `SESSION` crawl, if a fetched page contains it, the login has expired — so the
crawl **stops on the first hit** with an ERROR naming the fix:

```
[ladiaria_com_uy] SESSION expired (auth-wall detected). Stopping crawl.
Re-run: scrapai session login ladiaria_com_uy
```

- **Off by default** — no signal set, no check, behaviour unchanged.
- **Stop-on-first** — a valid session never shows the auth-wall, so the first hit
  is already proof it's dead. No threshold, no tolerance window.
- **No auto-recovery** — unlike a Cloudflare block (which the crawl re-solves
  itself), a dead login needs a human. Re-run `session login <name>` to refresh
  the file, then restart the crawl.

**Finding the signal:** inspect a gated article *without* a session (or after
logout) and note a stable string unique to the wall — a page `<title>` like
`Muro de pago`, a "Suscribite para continuar" banner, etc. Pick something that
never appears on a real logged-in article.

## Security

- Files are `0600` and hold live login cookies — treat them like passwords.
- Only the session a crawl names is loaded, so each scraped site sees only its
  own login.
- scrapai never stores or types your username/password.
