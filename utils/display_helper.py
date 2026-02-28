"""Display helper utilities for detecting headless environments."""

import os
import platform
import shutil


def needs_xvfb() -> bool:
    """Check if xvfb is needed (Linux/WSL servers without DISPLAY).

    Returns:
        True if Xvfb is needed (Linux/WSL without DISPLAY)
        False if native GUI available (macOS, Windows, Linux with DISPLAY)
    """
    # macOS and Windows have native GUI support
    if platform.system() in ("Darwin", "Windows"):
        return False

    # Linux (including WSL) without DISPLAY needs Xvfb
    # WSL reports as "Linux", so this handles both
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
