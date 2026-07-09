"""robots.txt parsing and the hand-rolled wildcard/`$`-aware matcher, plus the
AI-crawler read of the rule groups. The matcher semantics are regression-pinned
(tests/unit/test_compliance_robots.py) and were moved VERBATIM."""

import re
from urllib.parse import urlparse

from .store import spider_target_urls

# AI / LLM crawler user-agents — a Disallow: / for any of these is an explicit opt-out
# of AI/LLM use (training, RAG, answer engines). Canonical names; matched case-insensitively.
AI_BOTS = [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "CCBot",
    "Google-Extended",
    "anthropic-ai",
    "ClaudeBot",
    "Claude-Web",
    "PerplexityBot",
    "Perplexity-User",
    "Bytespider",
    "Amazonbot",
    "Applebot-Extended",
    "Meta-ExternalAgent",
    "FacebookBot",
    "Diffbot",
    "ImagesiftBot",
    "Omgilibot",
    "cohere-ai",
    "Timpibot",
    "YouBot",
    "AI2Bot",
    "Kangaroo Bot",
]

# AI crawlers route their content into our distribution channel — flagged by name in the
# report ("blocks your <X> channel") because a block on these binds the exact bot we feed.
AI_CHANNEL_BOTS = ("PerplexityBot", "Perplexity-User", "OAI-SearchBot")

# Narrow heuristic for AI/LLM user-agents NOT in AI_BOTS (new bots appear constantly). Matches
# only tokens that strongly imply AI use — deliberately EXCLUDES a bare "bot" so Googlebot /
# Bingbot / AhrefsBot and other SEO/search crawlers are never mis-read as AI agents.
AI_UA_HEURISTIC = re.compile(
    r"(?i)(gpt|claude|perplexity|\bllm\b|openai|anthropic|cohere|gemini|bard|"
    r"\bai\b|-extended|chatgpt|deepseek|mistral)"
)


def _is_robots(text):
    """True if `text` contains actual robots.txt directives — works even when a browser fetch
    returns the file HTML-wrapped, and rejects HTML 404/soft-404 pages that have none.
    """
    return bool(text) and bool(
        re.search(r"(?im)^\s*(user-agent|disallow|allow|sitemap)\s*:", text)
    )


def parse_robots(text):
    """Parse into per-user-agent rule groups + sitemaps. Returns
    {groups: {agent_lc: {disallow,allow,crawl_delay}}, sitemaps: [...]}."""
    groups, sitemaps, cur, last_agent = {}, [], [], False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            if not last_agent:
                cur = []
            cur.append(v.lower())
            groups.setdefault(
                v.lower(), {"disallow": [], "allow": [], "crawl_delay": None}
            )
            last_agent = True
            continue
        if k == "sitemap" and v:
            sitemaps.append(v)
            continue
        last_agent = False
        if k in ("disallow", "allow") and v:
            for a in cur:
                groups[a][k].append(v)
        elif k == "crawl-delay" and v:
            for a in cur:
                groups[a]["crawl_delay"] = v
    return {"groups": groups, "sitemaps": sitemaps}


def blocks_whole_site(disallow):
    """True if a disallow list blocks the ENTIRE site. Catches the literal `Disallow: /`
    AND the wildcard forms (`/*`, bare `*`) that Python's robotparser does NOT expand — so
    a site that bars all crawlers via `Disallow: /*` isn't mis-read as open."""
    return any((d or "").strip() in ("/", "/*", "/**", "*") for d in (disallow or []))


def _robots_rule_re(path):
    """A robots path (with `*` wildcards and `$` end-anchor) → regex anchored at path start."""
    return re.compile(
        "".join(".*" if c == "*" else "$" if c == "$" else re.escape(c) for c in path)
    )


def _robots_group(groups, ua):
    """Most specific UA group for `ua` (longest UA token that is a substring of it), else `*`."""
    ual = (ua or "*").lower()
    best, blen = None, -1
    for agent, g in groups.items():
        if agent and agent != "*" and agent in ual and len(agent) > blen:
            best, blen = g, len(agent)
    return best if best is not None else groups.get("*", {"disallow": [], "allow": []})


def robots_can_fetch(robots_txt, url, ua="*"):
    """Spec-style robots check with FULL `*`/`$` wildcard support and Allow/Disallow
    longest-match precedence (Allow wins ties) — which `urllib.robotparser` lacks. Picks the
    most specific UA group. We roll our own because protego/scrapy aren't installed here;
    this is advisory only (the crawler's own ROBOTSTXT_OBEY is off)."""
    groups = parse_robots(robots_txt)["groups"]
    pu = urlparse(url)
    path = (pu.path or "/") + (("?" + pu.query) if pu.query else "")
    g = _robots_group(groups, ua)
    best_len, allow = -1, True
    for kind in ("disallow", "allow"):
        for rule in g.get(kind, []):
            if rule and _robots_rule_re(rule).match(path):
                strength = len(rule.replace("*", "").replace("$", ""))
                if strength > best_len or (strength == best_len and kind == "allow"):
                    best_len, allow = strength, kind == "allow"
    return allow


def robots_blocks_targets(robots_txt, urls, ua="*"):
    """(checked, blocked_urls) — how many of `urls` robots forbids for `ua`.
    Returns (None, []) when there is nothing to assess (no robots or no spider paths).
    """
    if not robots_txt or not urls:
        return None, []
    blocked = [u for u in urls if not robots_can_fetch(robots_txt, u, ua)]
    return len(urls), blocked


# Representative PDF URLs probed against robots — a generic /*.pdf plus the common CMS
# upload dirs PDFs live in. We capture PDFs LINKED FROM articles (the article's pdf_url),
# so a robots Disallow on PDFs is a real restriction on what we may fetch & store.
PDF_PROBES = (
    "/file.pdf",
    "/wp-content/uploads/2024/file.pdf",
    "/sites/default/files/file.pdf",
    "/files/file.pdf",
    "/downloads/file.pdf",
    "/assets/file.pdf",
    "/documents/file.pdf",
    "/media/file.pdf",
    "/uploads/file.pdf",
)


def robots_blocks_pdfs(robots_txt, domain, ua="*"):
    """(blocked, evidence) — does robots.txt forbid PDF access for `ua`? Catches explicit
    `*.pdf` disallow lines (shown as evidence) AND directory blocks covering PDFs (probe
    representative PDF URLs through the wildcard-aware matcher). (None, []) if no robots.txt.
    """
    if not robots_txt:
        return None, []
    # only a WILDCARD pdf rule (`/*.pdf`, `*.pdf$`) means PDFs are blocked broadly; a disallow
    # of one specific file (`/docs/form-0142.pdf`) does not — don't treat it as a blanket block.
    explicit = [
        d
        for d in parse_robots(robots_txt)["groups"].get("*", {}).get("disallow", [])
        if "*" in d and ".pdf" in d.lower()
    ]
    probes = [
        p
        for p in PDF_PROBES
        if not robots_can_fetch(robots_txt, f"https://{domain}{p}", ua)
    ]
    # an explicit `*.pdf` rule is itself the reason the probes are blocked — report the rule,
    # not the redundant probe paths; fall back to the probe dirs for directory-based blocks.
    evidence = explicit or probes
    return (len(evidence) > 0), evidence


def ai_bots_blocked(groups):
    """AI bots given a whole-site disallow (the clear opt-out) — `/`, `/*`, etc."""
    return ai_bot_signals(groups)["full"]


def ai_bot_signals(groups):
    """Richer AI-crawler read of robots, beyond whole-site bans. Returns
      {full: [bots], partial: [(bot, sample_paths)], allowed: [bots],
       heuristic: [ua], channel: [bots]}
    - full      = whole-site Disallow (the clear opt-out)
    - partial   = some paths disallowed (not whole-site) — a softer signal
    - allowed   = explicit `Allow: /` with no whole-site disallow
    - heuristic = an AI-ish UA group NOT in AI_BOTS (narrow match; excludes bare 'bot')
    - channel   = AI answer-engine bots we feed (PerplexityBot…) that are blocked — flagged
                  by name because a block binds the exact bot our KB routes content to.
    """
    full, partial, allowed, heuristic, channel = [], [], [], [], []
    known = {b.lower() for b in AI_BOTS}
    for bot in AI_BOTS:
        g = groups.get(bot.lower())
        if not g:
            continue
        if blocks_whole_site(g["disallow"]):
            full.append(bot)
            if bot in AI_CHANNEL_BOTS:
                channel.append(bot)
        elif g["disallow"]:
            partial.append((bot, g["disallow"][:4]))
        elif any((a or "").strip() in ("/", "/*") for a in g.get("allow", [])):
            allowed.append(bot)
    for agent, g in groups.items():
        if (
            agent
            and agent != "*"
            and agent not in known
            and AI_UA_HEURISTIC.search(agent)
            and (blocks_whole_site(g["disallow"]) or g["disallow"])
        ):
            heuristic.append(agent)
    return {
        "full": full,
        "partial": partial,
        "allowed": allowed,
        "heuristic": heuristic,
        "channel": channel,
    }


def ai_scrape_block_from(bots, ai_txt_present):
    """The ACCESS-axis AI-scraping signal: any robots AI-bot ban (whole-site,
    partial, or heuristic UA group) or a Spawning ai.txt opt-out. One formula,
    shared by capture() and the rescued-robots path in build_report_data() so the
    two sites can never drift."""
    return bool(bots["full"] or bots["partial"] or bots["heuristic"] or ai_txt_present)


# robots.txt comments are stripped by parse_robots, but a site occasionally states real
# INTENT there ("# AI scraping prohibited — contact legal@…"). We surface ONLY those: an
# AI/ML mention, an email/contact, or a directed prohibition. Deliberately NOT bare
# "crawl"/"scrape"/"spider" — those appear in the boilerplate comment of nearly every
# robots.txt ("# prevent crawling and indexing"), which is noise, not a policy.
_ROBOTS_COMMENT_SIGNAL = re.compile(
    r"(?i)"
    r"\b(?:ai|gpt\w*|llm|chatgpt|claude|tdm|machine[- ]?learning|train(?:ing)?|generative)\b"
    r"|[\w.+-]+@[\w-]+\.[\w.]+"  # an email / contact address
    r"|\b(?:prohibit\w*|forbidden|not permitted|may not|must not|"
    r"without (?:prior |written )?permission)\b"
)


def robots_comment_signals(robots_txt):
    """Comment lines in robots.txt that state a real POLICY or CONTACT — an AI/ML mention, an
    email, or a directed prohibition (NOT generic 'prevent crawling' boilerplate). [] if none.
    These are otherwise discarded by parse_robots, so a stated intent isn't lost."""
    out = []
    for raw in (robots_txt or "").splitlines():
        s = raw.strip()
        if s.startswith("#"):
            body = s.lstrip("#").strip()
            if body and _ROBOTS_COMMENT_SIGNAL.search(body):
                out.append(body)
    return out[:6]


def robots_view_from_text(project, dom, robots_txt, ua):
    """Build the full robots view (overlap, PDFs, AI bots, comments) from a robots.txt body —
    the same shape capture() stores. Used to DISPLAY the crawl-captured robots when the
    independent fetch was blocked ('rescued'): the spider's downloader got the real file, so
    the report should show it, not the failed lightweight fetch. `source` marks its origin.
    """
    parsed = parse_robots(robots_txt)
    star = parsed["groups"].get("*", {"disallow": [], "allow": [], "crawl_delay": None})
    robots = {
        "fetched": True,
        "fetch_status": "ok",
        **star,
        "sitemaps": parsed["sitemaps"],
        "source": "crawl-capture",
    }
    checked, tblocked = robots_blocks_targets(
        robots_txt, spider_target_urls(project, dom), ua
    )
    robots["target_urls_checked"] = checked
    robots["target_urls_blocked"] = len(tblocked) if checked is not None else None
    robots["target_blocked_sample"] = tblocked[:8]
    pb, pe = robots_blocks_pdfs(robots_txt, dom, ua)
    robots["pdf_blocked"], robots["pdf_block_evidence"] = pb, pe[:8]
    robots["ai_bots"] = ai_bot_signals(parsed["groups"])
    robots["comments"] = robots_comment_signals(robots_txt)
    return robots
