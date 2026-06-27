"""Session store: save/load/list/remove a browser storage_state under
~/.scrapai/sessions/<name>.json (override the dir with SCRAPAI_SESSIONS_DIR).

A "session" is the cookies + localStorage captured AFTER a hand login. scrapai
never types a password; it reuses the saved session so a crawl reaches gated
pages. Files are owner-readable only.
"""

import os
import stat

import pytest

from core.sessions import (
    save_session,
    load_session,
    list_sessions,
    remove_session,
    session_path,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPAI_SESSIONS_DIR", str(tmp_path))
    return tmp_path


STATE = {"cookies": [{"name": "sess", "value": "abc"}], "origins": []}


def test_save_then_load_round_trips():
    save_session("nyt", STATE)
    assert load_session("nyt") == STATE


def test_load_missing_returns_none():
    assert load_session("nope") is None


def test_list_returns_sorted_names():
    save_session("b", STATE)
    save_session("a", STATE)
    assert list_sessions() == ["a", "b"]


def test_list_empty_when_no_sessions():
    assert list_sessions() == []


def test_remove_deletes_and_reports():
    save_session("x", STATE)
    assert remove_session("x") is True
    assert load_session("x") is None
    assert remove_session("x") is False  # already gone


def test_saved_file_is_owner_only():
    save_session("nyt", STATE)
    mode = stat.S_IMODE(os.stat(session_path("nyt")).st_mode)
    assert mode == 0o600


def test_invalid_name_rejected():
    for bad in ["../escape", "a/b", "", "has space", "dot.name"]:
        with pytest.raises(ValueError):
            save_session(bad, STATE)
