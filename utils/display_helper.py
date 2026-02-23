"""Display helper utilities for detecting headless environments."""

import os
import shutil
import sys


def needs_xvfb() -> bool:
    """Check if xvfb is needed (Linux servers without DISPLAY)."""
    # macOS and Windows have native GUI support
    if sys.platform in ("darwin", "win32"):
        return False
    # Linux without DISPLAY needs Xvfb
    return not os.environ.get("DISPLAY")


def has_xvfb() -> bool:
    """Check if xvfb-run is available on the system."""
    return shutil.which("xvfb-run") is not None


def ensure_display_for_cf():
    """Raise if CF bypass needs a display but none is available."""
    if needs_xvfb() and not has_xvfb():
        raise RuntimeError(
            "Cloudflare bypass requires a display but xvfb-run is not installed. "
            "Install with: sudo apt-get install xvfb"
        )
