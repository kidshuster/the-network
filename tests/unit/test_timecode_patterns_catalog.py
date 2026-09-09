"""Former YAML catalog + corpus fixtures driven from test data."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from bot.core.parsers.date_parser import replace_dates

TIMECODE = re.compile(r"<t:\d+>")
CASES_PATH = Path(__file__).parent / "data" / "date_parser_cases.yaml"


def _load_cases() -> dict:
    return yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))


_CASES = _load_cases()


@pytest.mark.parametrize("example", _CASES["valid"])
def test_corpus_valid_converts(example: str) -> None:
    result = replace_dates(example)
    assert TIMECODE.search(result), f"{example!r} -> {result!r}"


@pytest.mark.parametrize("example", _CASES["invalid"])
def test_corpus_invalid_unchanged(example: str) -> None:
    assert replace_dates(example) == example


@pytest.mark.parametrize("case", _CASES["multi_match"])
def test_corpus_multi_match(case: dict) -> None:
    result = replace_dates(case["input"])
    assert len(TIMECODE.findall(result)) == case["count"], result


@pytest.mark.parametrize("example", _CASES["formatting"])
def test_corpus_formatting_converts(example: str) -> None:
    result = replace_dates(example)
    assert TIMECODE.search(result), f"{example!r} -> {result!r}"
    assert len(TIMECODE.findall(result)) == 1, result


@pytest.mark.parametrize("case", _CASES["documented_soft"])
def test_documented_soft_phrases(case: dict) -> None:
    phrase = case["phrase"]
    status = case["status"]
    result = replace_dates(phrase)
    converted = TIMECODE.search(result) is not None
    if status == "converts":
        assert converted, f"expected convert for {phrase!r} -> {result!r}"
    elif status == "extractor_failure":
        assert not converted
    elif status == "interpretation_failure":
        assert not converted
    else:
        raise AssertionError(f"unknown status {status!r}")
