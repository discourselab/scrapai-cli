"""Store and reuse browser login sessions.

A "session" is a CloakBrowser/Playwright storage_state (cookies + localStorage)
captured AFTER a hand login. scrapai never types a password; it reuses the saved
session so a crawl reaches gated pages.

Files live at ~/.scrapai/sessions/<name>.json (override the directory with the
SCRAPAI_SESSIONS_DIR env var), owner-readable only.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Optional

# Session names become filenames, so keep them to a safe slug — no path
# separators, dots, or spaces that could escape the sessions directory.
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid session name: {name!r}. "
            "Use letters, digits, underscores, or hyphens only."
        )
    return name


def sessions_dir() -> Path:
    base = os.environ.get("SCRAPAI_SESSIONS_DIR")
    return Path(base) if base else Path.home() / ".scrapai" / "sessions"


def session_path(name: str) -> Path:
    return sessions_dir() / f"{_validate_name(name)}.json"


def save_session(name: str, storage_state: dict) -> Path:
    """Write a storage_state to the named session file (mode 0600)."""
    path = session_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(storage_state, f)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_session(name: str) -> Optional[dict]:
    """Return the saved storage_state, or None if the session doesn't exist."""
    path = session_path(name)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_sessions() -> List[str]:
    """Return saved session names (sorted), without the .json extension."""
    d = sessions_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def remove_session(name: str) -> bool:
    """Delete the named session. Returns True if it existed, False otherwise."""
    path = session_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
