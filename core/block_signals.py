"""Shared anti-bot block detection.

Decides whether a response looks like an *anti-bot block* that a stronger
transport (curl_cffi, then a browser) might bypass — as opposed to a genuine
404/500, which a different transport won't fix. Used by `inspect` escalation
and reusable elsewhere.
"""

BLOCKED_STATUSES = {403, 429, 503}

_CHALLENGE_MARKERS = (
    "checking your browser",
    "just a moment",
    "cf-browser-verification",
    "/cdn-cgi/challenge-platform",
    "sorry, you have been blocked",
    "attention required",
    "error 1020",
    "error 1015",
)


def is_blocked(status, body):
    """Return True if the response looks like an anti-bot block.

    Args:
        status: HTTP status code (int) or None.
        body: response body text or None.
    """
    if status in BLOCKED_STATUSES:
        return True

    # For an apparently-OK response (200 or unknown), inspect the body for
    # empty/challenge content that signals a soft block.
    if status == 200 or status is None:
        body = body or ""
        if not body.strip():
            return True
        low = body.lower()
        if any(marker in low for marker in _CHALLENGE_MARKERS):
            return True
        if len(body) < 5000 and "cloudflare" in low:
            return True

    return False
