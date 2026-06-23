"""Single source of truth for proxy URLs.

Every proxy value comes from ``.env`` — nothing provider-specific is hardcoded.
Proxies are referenced by **name** (``datacenter``, ``residential``, ``isp``,
``mobile``, ``residential_us``, …). For a name, the URL comes from either:

  - a full URL:        ``<NAME>_PROXY_URL``   (paste any provider's endpoint), or
  - component vars:    ``<NAME>_PROXY_{USERNAME,PASSWORD,HOST,PORT}``

(``<NAME>`` uppercased). All proxy-using code (crawl middleware, browser handler,
inspector) goes through this module, so URL-building lives in exactly one place.
"""

import logging
import os

logger = logging.getLogger(__name__)

# "static" is a legacy alias for the datacenter tier.
_ALIASES = {"static": "datacenter"}


def url_for(name):
    """Return the proxy URL for a named proxy, or None if not configured."""
    name = _ALIASES.get(name, name)
    prefix = name.upper()
    full = os.getenv(f"{prefix}_PROXY_URL")
    if full:
        return full
    user = os.getenv(f"{prefix}_PROXY_USERNAME")
    pw = os.getenv(f"{prefix}_PROXY_PASSWORD")
    host = os.getenv(f"{prefix}_PROXY_HOST")
    port = os.getenv(f"{prefix}_PROXY_PORT")
    if all([user, pw, host, port]):
        return f"http://{user}:{pw}@{host}:{port}"
    return None


def datacenter_url():
    return url_for("datacenter")


def residential_url():
    return url_for("residential")


def configured_names():
    """All proxy names that have a URL configured in the environment, sorted."""
    names = set()
    for key in os.environ:
        for suffix in ("_PROXY_URL", "_PROXY_USERNAME"):
            if key.endswith(suffix):
                names.add(key[: -len(suffix)].lower())
    return sorted(n for n in names if url_for(n))


def _auto():
    """Auto mode: datacenter if configured, else residential, else none."""
    dc = datacenter_url()
    if dc:
        return dc, "datacenter"
    res = residential_url()
    if res:
        return res, "residential"
    return None, None


def _unknown(proxy_type):
    logger.error(
        f"❌ Proxy '{proxy_type}' is not configured in .env "
        f"(set {proxy_type.upper()}_PROXY_URL or {proxy_type.upper()}_PROXY_*). "
        f"Configured proxies: {', '.join(configured_names()) or 'none'}"
    )


def select(proxy_type="auto"):
    """Return (proxy_url, active_name) for a single-proxy selection.

    - "none"   -> (None, None)
    - "auto"   -> datacenter if configured, else residential, else none
    - "<name>" -> that named proxy's URL. An unknown/unconfigured name does NOT
                  silently fall back — it logs a clear error and returns (None, None).
    """
    proxy_type = _ALIASES.get(proxy_type, proxy_type)
    if proxy_type == "none":
        return None, None
    if proxy_type == "auto":
        return _auto()
    url = url_for(proxy_type)
    if url:
        return url, proxy_type
    _unknown(proxy_type)
    return None, None


def chain(proxy_type="auto"):
    """Ordered list of proxy URLs to try (``None`` == direct).

    Used by the browser / inspector escalation path.
    - "none"   -> [None]
    - "auto"   -> [None, datacenter, residential] (configured only)
    - "<name>" -> [that proxy] (or [None] + a clear error if unconfigured)
    """
    proxy_type = _ALIASES.get(proxy_type, proxy_type)
    if proxy_type == "none":
        return [None]
    if proxy_type == "auto":
        out = [None]
        dc = datacenter_url()
        res = residential_url()
        if dc:
            out.append(dc)
        if res:
            out.append(res)
        return out
    url = url_for(proxy_type)
    if url:
        return [url]
    _unknown(proxy_type)
    return [None]
