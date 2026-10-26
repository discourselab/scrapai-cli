"""Regression pins for the robots.txt matcher in compliance_capture — the hand-rolled
longest-match / Allow-wins-ties semantics that the package restructure must move
VERBATIM. These tests lock the behaviour before the move.
"""

import glob
import os

import pytest

from core.quality.compliance_capture import (
    ai_bot_signals,
    ai_bots_blocked,
    parse_robots,
    robots_blocks_pdfs,
    robots_can_fetch,
)

pytestmark = pytest.mark.unit

BASIC = """User-agent: *
Disallow: /admin/
Allow: /admin/public
"""


def test_longest_match_wins():
    assert robots_can_fetch(BASIC, "https://x.org/admin/secret", "MyBot") is False
    assert robots_can_fetch(BASIC, "https://x.org/admin/public-page", "MyBot") is True
    assert robots_can_fetch(BASIC, "https://x.org/other", "MyBot") is True


def test_wildcard_and_dollar():
    txt = "User-agent: *\nDisallow: /*.pdf$\n"
    assert robots_can_fetch(txt, "https://x.org/report.pdf", "MyBot") is False
    assert robots_can_fetch(txt, "https://x.org/report.pdf?page=2", "MyBot") is True
    assert robots_can_fetch(txt, "https://x.org/report.html", "MyBot") is True


def test_ua_specific_group_beats_star():
    txt = "User-agent: *\nDisallow: /\n\nUser-agent: GoodBot\nAllow: /\n"
    assert robots_can_fetch(txt, "https://x.org/page", "goodbot/1.0") is True
    assert robots_can_fetch(txt, "https://x.org/page", "OtherBot") is False


def test_empty_disallow_means_open():
    assert (
        robots_can_fetch(
            "User-agent: *\nDisallow:\n", "https://x.org/anything", "MyBot"
        )
        is True
    )


def test_robots_blocks_pdfs_directory_block():
    # /files/ covers the /files/file.pdf probe → directory-based PDF block
    blocked, evidence = robots_blocks_pdfs(
        "User-agent: *\nDisallow: /files/\n", "x.org", "MyBot"
    )
    assert blocked is True
    assert "/files/file.pdf" in evidence


def test_robots_blocks_pdfs_explicit_wildcard_rule_is_the_evidence():
    blocked, evidence = robots_blocks_pdfs(
        "User-agent: *\nDisallow: /*.pdf\n", "x.org", "MyBot"
    )
    assert blocked is True
    assert evidence == ["/*.pdf"]  # the rule, not redundant probes


def test_robots_blocks_pdfs_open_site():
    blocked, evidence = robots_blocks_pdfs(
        "User-agent: *\nDisallow: /admin/\n", "x.org", "MyBot"
    )
    assert blocked is False
    assert evidence == []


def test_ai_bots_blocked_equals_signals_full_synthetic():
    txt = (
        "User-agent: GPTBot\nDisallow: /\n\n"
        "User-agent: CCBot\nDisallow: /private/\n\n"
        "User-agent: *\nDisallow: /admin/\n"
    )
    g = parse_robots(txt)["groups"]
    assert set(ai_bots_blocked(g)) == set(ai_bot_signals(g)["full"])
    assert "GPTBot" in ai_bots_blocked(g)  # whole-site ban
    assert "CCBot" not in ai_bots_blocked(g)  # partial ban is not whole-site


def test_ai_bots_blocked_equals_signals_full_stored_corpus():
    """Equivalence over every robots.txt stored in the real compliance snapshots —
    the strongest guard before ai_bots_blocked is reimplemented via ai_bot_signals."""
    stored = glob.glob(
        os.path.join("data", "*", "_audit", "compliance", "*", "*", "robots.txt")
    )
    if not stored:
        pytest.skip("no stored snapshots on this machine")
    for path in stored[:200]:
        try:
            txt = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        g = parse_robots(txt)["groups"]
        assert set(ai_bots_blocked(g)) == set(ai_bot_signals(g)["full"]), path
