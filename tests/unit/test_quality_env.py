"""Unit tests for core/quality/_env.py — the repo-anchored CLI/DB access layer.

The contract under test: db_query returns [] ONLY for a genuinely empty result set
and raises ScrapaiCliError for every failure shape the `scrapai db query` command
actually produces (non-zero exit, an error printed to stdout with exit 0, garbage).
"""

import subprocess

import pytest

from core.quality import _env

pytestmark = pytest.mark.unit


def _proc(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_db_query_parses_json_after_log_lines(monkeypatch):
    # log lines containing '[' must not mis-anchor the JSON scan
    out = '[INFO] connecting to db\n[{"name": "rmi_org"}, {"name": "iea_org"}]\n'
    monkeypatch.setattr(_env, "run_scrapai", lambda args, timeout=None: _proc(out))
    assert _env.db_query("SELECT name FROM spiders") == [
        {"name": "rmi_org"},
        {"name": "iea_org"},
    ]


def test_db_query_empty_result(monkeypatch):
    monkeypatch.setattr(
        _env, "run_scrapai", lambda args, timeout=None: _proc("(no results)\n")
    )
    assert _env.db_query("SELECT 1 FROM spiders WHERE 0") == []


def test_db_query_error_on_stdout_exit_zero(monkeypatch):
    # cli/db.py prints errors to stdout and exits 0 — this must raise, never return []
    monkeypatch.setattr(
        _env,
        "run_scrapai",
        lambda args, timeout=None: _proc("❌ Query failed: no such table: spiders\n"),
    )
    with pytest.raises(_env.ScrapaiCliError):
        _env.db_query("SELECT 1 FROM spiders")


def test_db_query_nonzero_exit(monkeypatch):
    monkeypatch.setattr(
        _env, "run_scrapai", lambda args, timeout=None: _proc("", "boom", returncode=1)
    )
    with pytest.raises(_env.ScrapaiCliError):
        _env.db_query("SELECT 1")


def test_db_query_unparseable(monkeypatch):
    monkeypatch.setattr(
        _env, "run_scrapai", lambda args, timeout=None: _proc("[not json at all\n")
    )
    with pytest.raises(_env.ScrapaiCliError):
        _env.db_query("SELECT 1")


def test_db_query_pretty_printed_json(monkeypatch):
    out = '[\n  {\n    "name": "x"\n  }\n]\n'
    monkeypatch.setattr(_env, "run_scrapai", lambda args, timeout=None: _proc(out))
    assert _env.db_query("SELECT name FROM spiders") == [{"name": "x"}]


def test_paths_are_repo_anchored():
    # never relative — the whole point of the module
    import os

    for p in (_env.SCRAPAI, _env.SETTINGS_PY, _env.SCRAPY_DIR):
        assert os.path.isabs(p), p
