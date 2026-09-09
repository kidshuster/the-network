"""Former YAML catalog examples kept as data-driven positive fixtures."""

from __future__ import annotations

import re

import pytest

from bot.core.parsers.date_parser import replace_dates

TIMECODE = re.compile(r"<t:\d+>")

# Examples migrated from the retired timecode_patterns.yaml production catalog.
CATALOG_EXAMPLES = (
    "2026-08-07 14:30",
    "3/15/2026 4:00 pm",
    "march 3 2026 6 pm",
    "today at 8 pm pst",
    "next friday at 7 pm cst",
    "saturday at 10am pst",
    "noon",
    "4 pm pst",
    "16:00 utc",
)


@pytest.mark.parametrize("example", CATALOG_EXAMPLES)
def test_former_catalog_examples_convert(example: str) -> None:
    result = replace_dates(example)
    assert TIMECODE.search(result), f"{example!r} -> {result!r}"
