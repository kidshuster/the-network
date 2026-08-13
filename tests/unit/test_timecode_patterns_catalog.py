from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from bot.core.parsers.date_parser import (
    load_timecode_catalog,
    replace_dates,
    sanitize_for_dates,
)


def test_catalog_loads_and_compiles() -> None:
    catalog = load_timecode_catalog()
    assert catalog.patterns
    assert catalog.hints
    assert "tz" in catalog.fragments
    assert catalog.tz_pattern.startswith("(?:")


def test_every_pattern_example_matches_its_regex() -> None:
    catalog = load_timecode_catalog()
    for pattern in catalog.patterns:
        sanitized = sanitize_for_dates(pattern.example).text
        match = pattern.compiled.search(sanitized)
        assert match is not None, (
            f"pattern {pattern.id!r} example {pattern.example!r} did not match"
        )
        assert match.group(0)


def test_catalog_examples_convert_through_replace_dates() -> None:
    catalog = load_timecode_catalog()
    for pattern in catalog.patterns:
        result = replace_dates(pattern.example)
        assert re.search(r"<t:\d+>", result), (
            f"pattern {pattern.id!r} example {pattern.example!r} -> {result!r}"
        )


def test_unknown_fragment_fails_at_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bot.core.parsers import date_parser as module

    bad = {
        "fragments": {"tz": "pst"},
        "patterns": [
            {
                "id": "broken",
                "example": "saturday",
                "match": r"\b(?:{missing})\b",
            }
        ],
        "hints": [r"\b(?:{tz})\b"],
    }
    path = tmp_path / "timecode_patterns.yaml"
    path.write_text(yaml.safe_dump(bad), encoding="utf-8")
    monkeypatch.setattr(module, "_catalog_path", lambda: path)
    module.load_timecode_catalog.cache_clear()
    with pytest.raises(ValueError, match="unknown timecode fragment"):
        module.load_timecode_catalog()
    module.load_timecode_catalog.cache_clear()
