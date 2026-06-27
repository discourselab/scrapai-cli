"""`scrapai session` — capture and manage login sessions.

scrapai NEVER types your password. `session login` opens a browser, you log in
BY HAND once, and we save the resulting session (cookies + localStorage) for
reuse so later crawls reach gated pages. → core/sessions.py
"""

import asyncio

import click

from core.sessions import (
    save_session,
    list_sessions,
    remove_session,
    session_path,
)

DEFAULT_LOGIN_URL = "https://the-internet.herokuapp.com/login"


@click.group()
def session():
    """Capture and manage login sessions (scrapai never types your password)."""


@session.command()
@click.argument("name")
@click.argument("url", required=False, default=DEFAULT_LOGIN_URL)
def login(name, url):
    """Open a browser, log in BY HAND, and save the session as NAME.

    Log in inside the window that opens (scrapai types nothing), then just
    CLOSE THE WINDOW — that captures the session (cookies + localStorage) for
    reuse. No keyboard needed, so it works headless/remote too.
    """
    try:
        session_path(name)  # validate the name before launching anything
    except ValueError as e:
        raise click.BadParameter(str(e))
    asyncio.run(_login(name, url))


async def _login(name, url):
    from cloakbrowser import launch_async

    click.echo("Launching browser (this may take a moment)...")
    browser = await launch_async(headless=False)
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await page.goto(url, wait_until="domcontentloaded")

    click.echo("=" * 64)
    click.echo(f"Opened: {url}")
    click.echo("Log in BY HAND in the browser window (scrapai types nothing).")
    click.echo("Navigate to the site's login if needed; finish any 2FA / SSO.")
    click.echo("When you're logged in, just CLOSE THE BROWSER WINDOW to save.")
    click.echo("=" * 64)

    # Capture trigger is CLOSING the window — no keyboard needed, so it works
    # headless/remote (noVNC) and through tooling. The context outlives the page,
    # so storage_state still reads after the window is gone.
    try:
        await page.wait_for_event("close", timeout=0)
    except Exception:
        pass

    state = None
    try:
        state = await ctx.storage_state()
    except Exception as e:
        click.echo(f"Couldn't capture the session after the window closed: {e}")

    try:
        await browser.close()
    except Exception:
        pass

    if state:
        path = save_session(name, state)
        n = len(state.get("cookies", []))
        click.echo(f"Saved session '{name}' ({n} cookies) to {path}")
    else:
        click.echo("No session captured (nothing saved).")


@session.command()
@click.argument("name")
@click.argument("url")
@click.option(
    "--wait",
    default=3,
    type=int,
    help="Seconds to let the page render before the screenshot "
    "(raise for JS-heavy SPAs, e.g. --wait 8 for x.com)",
)
def check(name, url, wait):
    """Confirm a session: open URL logged in with session NAME and screenshot it.

    Saves a PNG you can look at to verify you're actually logged in (it drives
    the session's own browser context, so cookies + localStorage apply).
    """
    p = session_path(name)  # validates the name
    if not p.exists():
        raise click.ClickException(
            f"No session named '{name}'. Run: scrapai session login {name}"
        )
    shot = str(p.with_name(f"{name}_check.png"))
    asyncio.run(_check(str(p), url, shot, wait))


async def _check(session_file, url, shot, wait=3):
    from utils.cf_browser import CloudflareBrowserClient
    from utils.inspector import _capture_screenshot

    click.echo("Launching browser (this may take a moment)...")
    async with CloudflareBrowserClient(
        headless=True, session_file=session_file
    ) as browser:
        # Drive the session context directly so the saved login applies.
        await browser.page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(wait)
        landed = browser.page.url
        try:
            await _capture_screenshot(browser.page, shot, 2)
        except Exception as e:
            click.echo(f"Screenshot failed: {e}")
            shot = None
    click.echo(f"Requested: {url}")
    click.echo(f"Landed on: {landed}")
    if shot:
        click.echo(f"Confirmation screenshot: {shot}")
        click.echo("Open it to verify you're logged in.")


@session.command("list")
def list_cmd():
    """List saved sessions."""
    names = list_sessions()
    if not names:
        click.echo("No saved sessions.")
        return
    for n in names:
        click.echo(n)


@session.command()
@click.argument("name")
def remove(name):
    """Delete a saved session."""
    if remove_session(name):
        click.echo(f"Removed session '{name}'.")
    else:
        click.echo(f"No session named '{name}'.")
