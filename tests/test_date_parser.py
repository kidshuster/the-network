from __future__ import annotations

import re

from bot.services.date_parser import replace_dates


def test_replace_dates_converts_time_with_timezone() -> None:
    result = replace_dates("we are grouping at 4 pm pst")
    assert re.fullmatch(r"we are grouping at <t:\d+>", result)


def test_replace_dates_leaves_plain_text_unchanged() -> None:
    text = "No schedule here."
    assert replace_dates(text) == text


def test_replace_dates_converts_multiple_candidates() -> None:
    result = replace_dates("Meet at 4 pm pst and again tomorrow at noon")
    assert result.count("<t:") == 2


def test_replace_dates_skips_unparseable_fragments() -> None:
    text = "See you at never o'clock"
    assert replace_dates(text) == text
