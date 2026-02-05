"""
Display helper utilities for detecting headless environments
and automatically using xvfb when needed.
"""

import os
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)


def has_display() -> bool:
    """
    Check if a display is available.

    Returns:
        True if display is available, False if headless environment
    """
    # Check DISPLAY environment variable
    display = os.environ.get('DISPLAY')

    if not display:
        logger.debug("No DISPLAY environment variable set")
        return False

    # Try to connect to the display
    try:
        # Use xdpyinfo to check if display is accessible
        result = subprocess.run(
            ['xdpyinfo'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        if result.returncode == 0:
            logger.debug(f"Display {display} is accessible")
            return True
        else:
            logger.debug(f"Display {display} not accessible")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # xdpyinfo not found or timed out - assume no display
        logger.debug("xdpyinfo not available or timed out")
        return False


def has_xvfb() -> bool:
    """
    Check if xvfb-run is available on the system.

    Returns:
        True if xvfb-run is available, False otherwise
    """
    try:
        result = subprocess.run(
            ['which', 'xvfb-run'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        available = result.returncode == 0
        logger.debug(f"xvfb-run available: {available}")
        return available
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.debug("xvfb-run not available")
        return False


def needs_xvfb() -> bool:
    """
    Determine if xvfb is needed for this environment.

    Returns:
        True if xvfb is needed (headless environment), False otherwise
    """
    # If display is available, no need for xvfb
    if has_display():
        return False

    # No display available - we need xvfb
    return True


def run_with_display(command: list, **kwargs) -> subprocess.CompletedProcess:
    """
    Run a command with display support, automatically using xvfb if needed.

    Args:
        command: Command to run as list of strings
        **kwargs: Additional arguments to pass to subprocess.run

    Returns:
        CompletedProcess instance

    Raises:
        RuntimeError: If headless environment but xvfb not available
    """
    if needs_xvfb():
        if not has_xvfb():
            raise RuntimeError(
                "Headless environment detected but xvfb-run not available. "
                "Install xvfb: sudo apt-get install xvfb"
            )

        logger.info("Headless environment detected, using xvfb-run")
        # Wrap command with xvfb-run
        command = ['xvfb-run', '-a'] + command
    else:
        logger.debug("Display available, running command directly")

    return subprocess.run(command, **kwargs)


def get_crawl_command_prefix() -> str:
    """
    Get the command prefix needed for crawling (xvfb-run or empty).

    Returns:
        Command prefix string (e.g., "xvfb-run -a" or "")
    """
    if needs_xvfb():
        if not has_xvfb():
            logger.warning(
                "Headless environment detected but xvfb-run not available. "
                "Cloudflare bypass may fail. Install xvfb: sudo apt-get install xvfb"
            )
            return ""
        return "xvfb-run -a"
    return ""


def ensure_display_for_cf():
    """
    Ensure display is available for Cloudflare bypass.

    Raises:
        RuntimeError: If CF bypass is needed but no display available and no xvfb
    """
    if needs_xvfb() and not has_xvfb():
        raise RuntimeError(
            "Cloudflare bypass requires a display, but no display is available and "
            "xvfb-run is not installed.\n\n"
            "Options:\n"
            "1. Install xvfb: sudo apt-get install xvfb\n"
            "2. Run on a machine with a display (local development)\n"
            "3. Use remote desktop (VNC/X11 forwarding)\n"
        )
