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

## Security

- Files are `0600` and hold live login cookies — treat them like passwords.
- Only the session a crawl names is loaded, so each scraped site sees only its
  own login.
- scrapai never stores or types your username/password.
