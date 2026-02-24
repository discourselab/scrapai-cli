"""Field processors for custom extraction.

Processors transform extracted values (strip whitespace, cast types, apply regex, etc.).
Each processor is a pure function registered in the PROCESSORS dict.
"""

import re
import logging
from typing import Any, List, Dict, Optional
from datetime import datetime
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)


def strip_processor(value: Any, **kwargs) -> Any:
    """Remove leading/trailing whitespace from string values."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [v.strip() if isinstance(v, str) else v for v in value]
    return value


def replace_processor(value: Any, old: str, new: str, **kwargs) -> Any:
    """Replace substring in string values.

    Args:
        value: Input value
        old: Substring to replace
        new: Replacement string
    """
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [v.replace(old, new) if isinstance(v, str) else v for v in value]
    return value


def regex_processor(value: Any, pattern: str, group: int = 1, **kwargs) -> Any:
    """Extract substring using regex pattern.

    Args:
        value: Input value
        pattern: Regex pattern to match
        group: Capture group to extract (default: 1)
    """
    if not isinstance(value, str):
        return value

    try:
        match = re.search(pattern, value)
        if match:
            return match.group(group)
    except (re.error, IndexError) as e:
        logger.warning(f"Regex processor failed: {e}")

    return value


def cast_processor(value: Any, to: str, **kwargs) -> Any:
    """Cast value to specified type.

    Args:
        value: Input value
        to: Target type ("int", "float", "bool", "str")

    Returns None if casting fails.
    """
    if value is None or value == "":
        return None

    try:
        if to == "int":
            return int(value)
        elif to == "float":
            return float(value)
        elif to == "bool":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        elif to == "str":
            return str(value)
        else:
            logger.warning(f"Unknown cast type: {to}")
            return value
    except (ValueError, TypeError) as e:
        logger.warning(f"Cast to {to} failed for value '{value}': {e}")
        return None


def join_processor(value: Any, separator: str = " ", **kwargs) -> Any:
    """Join list values into a string.

    Args:
        value: Input value (must be list)
        separator: String to join with (default: " ")
    """
    if isinstance(value, list):
        # Convert all items to strings first
        str_values = [str(v) for v in value if v is not None]
        return separator.join(str_values)
    return value


def default_processor(value: Any, default: Any, **kwargs) -> Any:
    """Return default value if input is None or empty.

    Args:
        value: Input value
        default: Value to return if input is None/empty
    """
    if value is None or value == "" or value == []:
        return default
    return value


def lowercase_processor(value: Any, **kwargs) -> Any:
    """Convert string values to lowercase."""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, list):
        return [v.lower() if isinstance(v, str) else v for v in value]
    return value


def parse_datetime_processor(value: Any, format: Optional[str] = None, **kwargs) -> Any:
    """Parse datetime string into datetime object.

    Args:
        value: Input datetime string
        format: Optional strptime format string (if None, uses dateutil parser)

    Returns datetime object or None if parsing fails.
    """
    if not isinstance(value, str) or not value:
        return None

    try:
        if format:
            # Use strptime with explicit format
            return datetime.strptime(value, format)
        else:
            # Use dateutil for flexible parsing
            return dateutil_parser.parse(value)
    except (ValueError, TypeError, dateutil_parser.ParserError) as e:
        logger.warning(f"Failed to parse datetime '{value}': {e}")
        return None


# Registry of all processors
PROCESSORS: Dict[str, callable] = {
    "strip": strip_processor,
    "replace": replace_processor,
    "regex": regex_processor,
    "cast": cast_processor,
    "join": join_processor,
    "default": default_processor,
    "lowercase": lowercase_processor,
    "parse_datetime": parse_datetime_processor,
}


def apply_processors(value: Any, processor_configs: List[Dict[str, Any]]) -> Any:
    """Apply a chain of processors to a value.

    Args:
        value: Input value
        processor_configs: List of processor configs (e.g., [{"type": "strip"}, {"type": "cast", "to": "int"}])

    Returns:
        Transformed value after applying all processors in sequence.
    """
    result = value

    for config in processor_configs:
        processor_type = config.get("type")
        if not processor_type:
            logger.warning("Processor config missing 'type' field")
            continue

        processor_func = PROCESSORS.get(processor_type)
        if not processor_func:
            logger.warning(f"Unknown processor type: {processor_type}")
            continue

        # Pass all config params to processor (except 'type')
        params = {k: v for k, v in config.items() if k != "type"}
        result = processor_func(result, **params)

    return result
