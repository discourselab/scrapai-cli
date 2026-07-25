"""db query safety gate + CSV output correctness.

Pins two fixes:
- prefix-only SQL gate let multi-statement SQL through
  (``SELECT 1; DROP TABLE spiders``)
- CSV output was hand-joined with ','.join, corrupting values
  containing commas, quotes, or newlines
"""

from cli.db import _sql_error, _format_results


class TestSqlGate:
    def test_select_allowed(self):
        assert _sql_error("SELECT * FROM spiders") is None

    def test_update_allowed(self):
        assert _sql_error("UPDATE spiders SET name='x' WHERE id=1") is None

    def test_delete_allowed(self):
        assert _sql_error("DELETE FROM scraped_items WHERE id=5") is None

    def test_trailing_semicolon_allowed(self):
        assert _sql_error("SELECT 1;") is None

    def test_drop_rejected(self):
        assert _sql_error("DROP TABLE spiders") is not None

    def test_insert_rejected(self):
        assert _sql_error("INSERT INTO spiders VALUES (1)") is not None

    def test_multi_statement_rejected(self):
        assert _sql_error("SELECT 1; DROP TABLE spiders") is not None

    def test_multi_statement_with_whitespace_rejected(self):
        assert _sql_error("  SELECT 1 ;  DELETE FROM spiders  ") is not None


class FakeResult:
    def __init__(self, columns):
        self._columns = columns

    def keys(self):
        return self._columns


class TestCsvOutput:
    def test_value_with_comma_is_quoted(self, capsys):
        import csv
        import io
        import json

        rows = [("hello, world", 'say "hi"', "line1\nline2")]
        _format_results(rows, FakeResult(["a", "b", "c"]), "csv", json)

        out = capsys.readouterr().out
        parsed = list(csv.reader(io.StringIO(out)))
        assert parsed[0] == ["a", "b", "c"]
        assert parsed[1] == ["hello, world", 'say "hi"', "line1\nline2"]
