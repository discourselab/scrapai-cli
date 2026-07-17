"""`scrapai crawl` with no --limit submits itself to Pueue (detached) so a full
crawl survives SSH disconnect. The only non-trivial bit is rebuilding the crawl
invocation with its flags for the detached re-run — that's what this checks.
"""

import pytest

from cli.crawl import _build_detached_cmd

pytestmark = pytest.mark.unit


def test_omits_defaults():
    cmd = _build_detached_cmd("/repo/scrapai", "bbc_com", "news")
    assert cmd[:5] == ["/repo/scrapai", "crawl", "bbc_com", "--project", "news"]
    assert "--detached" in cmd
    for flag in ("--browser", "--proxy-type", "--reset-deltafetch", "--save-html"):
        assert flag not in cmd


def test_passes_flags_through():
    cmd = _build_detached_cmd(
        "/repo/scrapai",
        "bbc_com",
        "news",
        proxy_type="residential",
        browser=True,
        reset_deltafetch=True,
        save_html=True,
        timeout=3600,
        scrapy_args="-L DEBUG",
        output="out.jsonl",
    )
    for flag in ("--browser", "--reset-deltafetch", "--save-html", "--detached"):
        assert flag in cmd
    for flag, val in [
        ("--proxy-type", "residential"),
        ("--timeout", "3600"),
        ("--scrapy-args", "-L DEBUG"),
        ("--output", "out.jsonl"),
    ]:
        i = cmd.index(flag)
        assert cmd[i] == flag and cmd[i + 1] == val


# --- crawl-all queues every spider through the same detach path ---------------


def test_crawl_all_enqueues_each_spider(monkeypatch):
    """`crawl-all` (no --limit) must submit EVERY spider through the same
    auto-detach path as a single `crawl` (detached=False → Pueue), not run them
    inline — inline was sequential, terminal-bound, and died on disconnect."""
    from unittest.mock import MagicMock, Mock, patch

    from click.testing import CliRunner

    import importlib

    crawl_mod = importlib.import_module("cli.crawl")  # cli/__init__ shadows the
    #                                                    attribute with the command
    calls = []
    monkeypatch.setattr(crawl_mod, "_run_spider", lambda *a, **k: calls.append(a))

    recs = []
    for n in ("a_org", "b_org"):
        r = Mock()
        r.name = n
        recs.append(r)
    with patch("core.db.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = recs
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        res = CliRunner().invoke(crawl_mod.crawl_all, ["--project", "proj"])
    assert res.exit_code == 0, res.output
    assert [c[1] for c in calls] == ["a_org", "b_org"]  # every spider
    assert all(c[10] is False for c in calls)  # detached=False → Pueue path
    assert "queued in Pueue" in res.output


def test_pueue_active_task_dedup(monkeypatch):
    """The duplicate guard: an unfinished task with the same label is reported,
    finished ones and other labels are not, and unreadable pueue fails open."""
    import json
    from unittest.mock import Mock

    import importlib

    crawl_mod = importlib.import_module("cli.crawl")

    def fake_status(tasks):
        res = Mock(returncode=0, stdout=json.dumps({"tasks": tasks}))
        return lambda *a, **k: res

    running = {"1": {"label": "scrapai:proj:a_org", "status": {"Running": {}}}}
    monkeypatch.setattr(crawl_mod.subprocess, "run", fake_status(running))
    assert crawl_mod._pueue_active_task("scrapai:proj:a_org") == "1"
    assert crawl_mod._pueue_active_task("scrapai:proj:b_org") is None

    finished = {"1": {"label": "scrapai:proj:a_org", "status": {"Done": {"result": "Success"}}}}
    monkeypatch.setattr(crawl_mod.subprocess, "run", fake_status(finished))
    assert crawl_mod._pueue_active_task("scrapai:proj:a_org") is None

    monkeypatch.setattr(
        crawl_mod.subprocess, "run", lambda *a, **k: Mock(returncode=1, stdout="")
    )
    assert crawl_mod._pueue_active_task("scrapai:proj:a_org") is None


def test_crawl_all_with_limit_stays_inline(monkeypatch):
    from unittest.mock import MagicMock, Mock, patch

    from click.testing import CliRunner

    import importlib

    crawl_mod = importlib.import_module("cli.crawl")
    calls = []
    monkeypatch.setattr(crawl_mod, "_run_spider", lambda *a, **k: calls.append(a))
    r = Mock()
    r.name = "a_org"
    with patch("core.db.get_db") as mock_get_db:
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = [r]
        cm = MagicMock()
        cm.__enter__.return_value = db
        mock_get_db.return_value = cm
        res = CliRunner().invoke(
            crawl_mod.crawl_all, ["--project", "proj", "--limit", "5"]
        )
    assert res.exit_code == 0, res.output
    assert calls[0][3] == 5  # limit threads through
    assert "queued in Pueue" not in res.output  # inline test mode
