"""`scrapai session` CLI — list / remove / login.

(The `login` browser flow needs a real window + a hand login, so it's verified
manually; here we cover the parts that don't open a browser.)
"""

import pytest
from click.testing import CliRunner

from core.sessions import save_session, load_session
from cli.session_cmd import session

pytestmark = pytest.mark.unit

STATE = {"cookies": [{"name": "s", "value": "v"}], "origins": []}


@pytest.fixture(autouse=True)
def _isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPAI_SESSIONS_DIR", str(tmp_path))


def test_list_shows_saved_sessions():
    save_session("alpha", STATE)
    save_session("beta", STATE)
    out = CliRunner().invoke(session, ["list"]).output
    assert "alpha" in out and "beta" in out


def test_list_empty():
    r = CliRunner().invoke(session, ["list"])
    assert r.exit_code == 0
    assert "No saved sessions" in r.output


def test_remove_deletes_session():
    save_session("gone", STATE)
    r = CliRunner().invoke(session, ["remove", "gone"])
    assert r.exit_code == 0
    assert load_session("gone") is None


def test_remove_missing_reports_cleanly():
    r = CliRunner().invoke(session, ["remove", "nope"])
    assert r.exit_code == 0
    assert "No session" in r.output


def test_login_rejects_bad_name_without_launching_a_browser():
    # An invalid name must fail fast (before any browser launch).
    r = CliRunner().invoke(session, ["login", "../escape"])
    assert r.exit_code != 0


def test_check_missing_session_errors_without_launching():
    r = CliRunner().invoke(session, ["check", "nope", "https://example.com/secure"])
    assert r.exit_code != 0
    assert "No session named 'nope'" in r.output
