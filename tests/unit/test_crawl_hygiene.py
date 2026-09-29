"""Same-day reset re-runs supersede TODAY's crawl file only (docs/requests/18).

A same-day --reset-deltafetch is a repair: today's file would otherwise receive
an appended duplicate copy. Older days' files are the version history (and may
hold the only copy of since-removed pages) — they must never be touched.
"""

from datetime import datetime

import pytest

from cli.crawl import _supersede_todays_crawl_file

pytestmark = pytest.mark.unit


def test_only_todays_file_superseded(tmp_path):
    today = datetime.now().strftime("%d%m%Y")
    (tmp_path / f"crawl_{today}.jsonl").write_text("{}\n")
    (tmp_path / "crawl_01011999.jsonl").write_text("{}\n")  # history
    (tmp_path / "robots_01011999.txt").write_text("x")  # witness file

    got = _supersede_todays_crawl_file(tmp_path)

    assert got is not None and got.name == f"crawl_{today}.jsonl"
    assert (tmp_path / f"crawl_{today}.jsonl.superseded").exists()
    assert not (tmp_path / f"crawl_{today}.jsonl").exists()
    assert (tmp_path / "crawl_01011999.jsonl").exists()  # untouched
    assert (tmp_path / "robots_01011999.txt").exists()


def test_no_todays_file_is_noop(tmp_path):
    (tmp_path / "crawl_01011999.jsonl").write_text("{}\n")
    assert _supersede_todays_crawl_file(tmp_path) is None
    assert (tmp_path / "crawl_01011999.jsonl").exists()


def test_missing_dir_is_noop(tmp_path):
    assert _supersede_todays_crawl_file(tmp_path / "nope") is None
