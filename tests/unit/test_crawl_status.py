"""`scrapai crawl-status` — joins pueue run-state with crawl-file data quality.
The two pure bits are: counting downloaded/non-empty items in a crawl jsonl,
and turning pueue's nested status dict into one human word.
"""

import json

import pytest

from cli.crawl import _crawl_stats, _pueue_state, _pueue_times, _short_ts, _ago

pytestmark = pytest.mark.unit


def test_crawl_stats_counts_downloaded_with_content_and_eligible(tmp_path):
    # PDF URLs (links_only mode has no content) are downloaded but NOT content-
    # eligible, so they don't drag the with-content % down.
    f = tmp_path / "crawl.jsonl"
    f.write_text(
        json.dumps({"url": "https://x/a", "content": "real text"})
        + "\n"
        + json.dumps({"url": "https://x/b", "content": ""})
        + "\n"
        + json.dumps({"url": "https://x/c", "content": "   "})
        + "\n"
        + json.dumps({"url": "https://x/d"})
        + "\n"
        + json.dumps({"url": "https://x/e", "content": "more"})
        + "\n"
        + json.dumps({"url": "https://x/doc.pdf", "content": ""})  # PDF, ignored
        + "\n"
        + json.dumps({"url": "https://x/report.pdf?v=2"})  # PDF w/ query, ignored
        + "\n"
        + "not json at all\n"
    )
    # downloaded=7 (incl 2 pdfs), with_content=2 (a,e), eligible=5 (non-pdf)
    assert _crawl_stats(str(f)) == (7, 2, 5)


def test_crawl_stats_missing_file_is_zero():
    assert _crawl_stats("/no/such/file.jsonl") == (0, 0, 0)


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
    assert _short_ts("2026-06-29T13:46:11.619180+01:00") == "13:46 29-06-26"


def test_short_ts_none():
    assert _short_ts(None) == "-"


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-5, "0s"),  # clock skew -> clamp
        (0, "0s"),
        (4, "4s"),
        (59, "59s"),
        (60, "1m"),
        (300, "5m"),
        (3600, "1h"),
        (7200, "2h"),
        (86400, "1d"),
    ],
)
def test_ago(seconds, expected):
    assert _ago(seconds) == expected
