"""Unit tests for field processors."""

from datetime import datetime
from core.processors import (
    strip_processor,
    replace_processor,
    regex_processor,
    cast_processor,
    join_processor,
    default_processor,
    lowercase_processor,
    parse_datetime_processor,
    apply_processors,
    PROCESSORS,
)


class TestStripProcessor:
    def test_strip_string(self):
        assert strip_processor("  hello  ") == "hello"
        assert strip_processor("\n\tworld\t\n") == "world"

    def test_strip_list(self):
        result = strip_processor(["  a  ", "  b  "])
        assert result == ["a", "b"]

    def test_strip_non_string(self):
        assert strip_processor(123) == 123
        assert strip_processor(None) is None


class TestReplaceProcessor:
    def test_replace_string(self):
        assert (
            replace_processor("hello world", old="world", new="python")
            == "hello python"
        )
        assert replace_processor("foo-bar-baz", old="-", new="_") == "foo_bar_baz"

    def test_replace_list(self):
        result = replace_processor(["hello world", "foo bar"], old=" ", new="_")
        assert result == ["hello_world", "foo_bar"]

    def test_replace_non_string(self):
        assert replace_processor(123, old="1", new="2") == 123


class TestRegexProcessor:
    def test_regex_extract_default_group(self):
        result = regex_processor("Price: $99.99", pattern=r"\$(\d+\.\d+)")
        assert result == "99.99"

    def test_regex_extract_specific_group(self):
        result = regex_processor(
            "Name: John Doe", pattern=r"Name: (\w+) (\w+)", group=2
        )
        assert result == "Doe"

    def test_regex_no_match(self):
        result = regex_processor("hello", pattern=r"\d+")
        assert result == "hello"  # Returns original if no match

    def test_regex_non_string(self):
        assert regex_processor(123, pattern=r"\d+") == 123


class TestCastProcessor:
    def test_cast_to_int(self):
        assert cast_processor("42", to="int") == 42
        assert cast_processor("100", to="int") == 100
        # Note: int("3.7") fails - use float cast first if needed

    def test_cast_to_float(self):
        assert cast_processor("3.14", to="float") == 3.14
        assert cast_processor("42", to="float") == 42.0

    def test_cast_to_bool(self):
        assert cast_processor("true", to="bool") is True
        assert cast_processor("false", to="bool") is False
        assert cast_processor("1", to="bool") is True
        assert cast_processor("0", to="bool") is False

    def test_cast_to_str(self):
        assert cast_processor(42, to="str") == "42"

    def test_cast_failure(self):
        # Invalid cast returns None
        assert cast_processor("not a number", to="int") is None
        assert cast_processor("not a number", to="float") is None

    def test_cast_none(self):
        assert cast_processor(None, to="int") is None
        assert cast_processor("", to="int") is None


class TestJoinProcessor:
    def test_join_list(self):
        assert join_processor(["a", "b", "c"], separator=", ") == "a, b, c"
        assert join_processor(["foo", "bar"], separator="-") == "foo-bar"

    def test_join_with_none(self):
        # None values are filtered out
        assert join_processor([1, None, 2], separator=",") == "1,2"

    def test_join_non_list(self):
        # Returns original if not a list
        assert join_processor("hello", separator=",") == "hello"


class TestDefaultProcessor:
    def test_default_when_none(self):
        assert default_processor(None, default="N/A") == "N/A"

    def test_default_when_empty_string(self):
        assert default_processor("", default="N/A") == "N/A"

    def test_default_when_empty_list(self):
        assert default_processor([], default="N/A") == "N/A"

    def test_default_when_has_value(self):
        assert default_processor("hello", default="N/A") == "hello"
        assert default_processor(0, default="N/A") == 0


class TestLowercaseProcessor:
    def test_lowercase_string(self):
        assert lowercase_processor("HELLO") == "hello"
        assert lowercase_processor("MiXeD") == "mixed"

    def test_lowercase_list(self):
        result = lowercase_processor(["HELLO", "WORLD"])
        assert result == ["hello", "world"]

    def test_lowercase_non_string(self):
        assert lowercase_processor(123) == 123


class TestParseDatetimeProcessor:
    def test_parse_iso_format(self):
        result = parse_datetime_processor("2024-02-24T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 24

    def test_parse_with_format(self):
        result = parse_datetime_processor("24/02/2024", format="%d/%m/%Y")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 2
        assert result.day == 24

    def test_parse_natural_language(self):
        # dateutil parser handles various formats
        result = parse_datetime_processor("February 24, 2024")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 2

    def test_parse_invalid(self):
        assert parse_datetime_processor("not a date") is None
        assert parse_datetime_processor("") is None
        assert parse_datetime_processor(None) is None


class TestApplyProcessors:
    def test_single_processor(self):
        configs = [{"type": "strip"}]
        result = apply_processors("  hello  ", configs)
        assert result == "hello"

    def test_processor_chain(self):
        # Strip, then replace, then lowercase
        configs = [
            {"type": "strip"},
            {"type": "replace", "old": " ", "new": "_"},
            {"type": "lowercase"},
        ]
        result = apply_processors("  Hello World  ", configs)
        assert result == "hello_world"

    def test_cast_chain(self):
        # Extract number with regex, then cast to float
        configs = [
            {"type": "regex", "pattern": r"(\d+\.\d+)"},
            {"type": "cast", "to": "float"},
        ]
        result = apply_processors("Price: $99.99", configs)
        assert result == 99.99

    def test_unknown_processor(self):
        # Unknown processors are skipped
        configs = [
            {"type": "strip"},
            {"type": "unknown_processor"},
            {"type": "lowercase"},
        ]
        result = apply_processors("  HELLO  ", configs)
        assert result == "hello"

    def test_missing_type(self):
        # Config without 'type' is skipped
        configs = [{"type": "strip"}, {"old": "x", "new": "y"}]
        result = apply_processors("  hello  ", configs)
        assert result == "hello"

    def test_default_processor_in_chain(self):
        # If value becomes None, default processor catches it
        configs = [
            {"type": "cast", "to": "int"},
            {"type": "default", "default": 0},
        ]
        result = apply_processors("not a number", configs)
        assert result == 0


class TestProcessorRegistry:
    def test_all_processors_registered(self):
        expected = {
            "strip",
            "replace",
            "regex",
            "cast",
            "join",
            "default",
            "lowercase",
            "parse_datetime",
        }
        assert set(PROCESSORS.keys()) == expected

    def test_processors_are_callable(self):
        for name, func in PROCESSORS.items():
            assert callable(func), f"Processor {name} is not callable"
