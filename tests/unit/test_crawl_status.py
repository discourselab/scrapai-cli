"""`scrapai crawl-status` — joins pueue run-state with crawl-file data quality.
The two pure bits are: counting downloaded/non-empty items in a crawl jsonl,
and turning pueue's nested status dict into one human word.
"""

import json

import pytest

from cli.crawl import _crawl_stats, _pueue_state, _pueue_times, _short_ts

pytestmark = pytest.mark.unit


def test_crawl_stats_counts_total_and_non_empty(tmp_path):
    f = tmp_path / "crawl.jsonl"
    f.write_text(
        json.dumps({"url": "a", "content": "real text"})
        + "\n"
        + json.dumps({"url": "b", "content": ""})
        + "\n"
        + json.dumps({"url": "c", "content": "   "})
        + "\n"
        + json.dumps({"url": "d"})
        + "\n"
        + json.dumps({"url": "e", "content": "more"})
        + "\n"
        + "not json at all\n"
    )
    assert _crawl_stats(str(f)) == (5, 2)


def test_crawl_stats_missing_file_is_zero():
    assert _crawl_stats("/no/such/file.jsonl") == (0, 0)


@pytest.mark.parametrize(
    "status,expected",
    [
        ({"Running": {}}, "running"),
        ({"Queued": {}}, "queued"),
        ({"Paused": {}}, "paused"),
        ({"Done": {"result": "Success"}}, "done"),
        ({"Done": {"result": "Killed"}}, "killed"),
        ({"Done": {"result": {"Failed": 1}}}, "failed"),
    ],
)
def test_pueue_state(status, expected):
    assert _pueue_state(status) == expected


def test_pueue_times_done_has_both():
    status = {
        "Done": {
            "start": "2026-06-29T13:46:11+01:00",
            "end": "2026-06-29T13:53:23+01:00",
        }
    }
    assert _pueue_times(status) == (
        "2026-06-29T13:46:11+01:00",
        "2026-06-29T13:53:23+01:00",
    )


def test_pueue_times_running_has_start_only():
    assert _pueue_times({"Running": {"start": "2026-06-29T13:46:11+01:00"}}) == (
        "2026-06-29T13:46:11+01:00",
        None,
    )


def test_pueue_times_queued_has_neither():
    assert _pueue_times({"Queued": {}}) == (None, None)


def test_short_ts_compacts_iso():
    assert _short_ts("2026-06-29T13:46:11.619180+01:00") == "06-29 13:46"


def test_short_ts_none():
    assert _short_ts(None) == "-"
