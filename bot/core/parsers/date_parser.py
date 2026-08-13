from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib import resources
from pathlib import Path
from zoneinfo import ZoneInfo

import dateparser  # type: ignore[import-untyped]
import yaml

DEFAULT_TZ = ZoneInfo("America/New_York")

TZ_MAP = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mt": "America/Denver",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "ct": "America/Chicago",
    "est": "America/New_York",
    "edt": "America/New_York",
    "et": "America/New_York",
    "utc": "UTC",
    "gmt": "UTC",
}

_FRAGMENT_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_CATALOG_NAME = "timecode_patterns.yaml"

# Discord markdown markers stripped before date matching (lossy; mapped back).
_MARKDOWN_CHARS = frozenset("*_`~|")


@dataclass(frozen=True)
class TimecodePattern:
    id: str
    example: str
    match: str
    compiled: re.Pattern[str]


@dataclass(frozen=True)
class TimecodeCatalog:
    fragments: dict[str, str]
    patterns: tuple[TimecodePattern, ...]
    hints: tuple[str, ...]
    tz_pattern: str


@dataclass(frozen=True)
class SanitizedText:
    """Lowercased / de-markdowned text with a map back into the original string."""

    original: str
    text: str
    to_original: tuple[int, ...]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a ``[start, end)`` span in ``text`` back to ``original`` indices.

        Interstitial markdown between matched words is already included via the
        index map. Adjacent markdown markers hugging the span are absorbed so
        replacements do not leave dangling ``**`` / ``_`` / ``||`` wrappers.
        """
        if start < 0 or end < start or end > len(self.to_original):
            raise ValueError(f"sanitized span out of range: [{start}, {end})")
        if start == end:
            if start == 0:
                return (0, 0)
            return (self.to_original[start - 1] + 1, self.to_original[start - 1] + 1)
        orig_start = self.to_original[start]
        orig_end = self.to_original[end - 1] + 1
        while orig_start > 0 and self.original[orig_start - 1] in _MARKDOWN_CHARS:
            orig_start -= 1
        while orig_end < len(self.original) and self.original[orig_end] in _MARKDOWN_CHARS:
            orig_end += 1
        return (orig_start, orig_end)


@dataclass(frozen=True)
class _DateMatch:
    start: int
    end: int
    text: str
    length: int


def _expand_fragments(
    template: str,
    fragments: dict[str, str],
    *,
    stack: tuple[str, ...] = (),
) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in fragments:
            raise ValueError(f"unknown timecode fragment {{{key}}}")
        if key in stack:
            raise ValueError(f"cyclic timecode fragment {{{key}}}")
        return _expand_fragments(fragments[key], fragments, stack=(*stack, key))

    return _FRAGMENT_RE.sub(replace, template)


def _catalog_path() -> Path:
    return Path(__file__).with_name(_CATALOG_NAME)


def _read_catalog_yaml() -> str:
    path = _catalog_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    package = resources.files("bot.core.parsers")
    return (package / _CATALOG_NAME).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_timecode_catalog() -> TimecodeCatalog:
    """Load and compile ``timecode_patterns.yaml`` (fail fast on bad patterns)."""
    raw = yaml.safe_load(_read_catalog_yaml())
    if not isinstance(raw, dict):
        raise ValueError("timecode_patterns.yaml must be a mapping")

    fragments_raw = raw.get("fragments") or {}
    if not isinstance(fragments_raw, dict) or not fragments_raw:
        raise ValueError("timecode_patterns.yaml requires non-empty fragments")
    fragments = {str(key): str(value) for key, value in fragments_raw.items()}
    # Expand fragment values so callers can use fully-resolved snippets.
    expanded_fragments = {
        key: _expand_fragments(value, fragments) for key, value in fragments.items()
    }

    patterns_raw = raw.get("patterns") or []
    if not isinstance(patterns_raw, list) or not patterns_raw:
        raise ValueError("timecode_patterns.yaml requires a non-empty patterns list")

    patterns: list[TimecodePattern] = []
    seen_ids: set[str] = set()
    for item in patterns_raw:
        if not isinstance(item, dict):
            raise ValueError("each timecode pattern must be a mapping")
        pattern_id = str(item.get("id") or "").strip()
        example = str(item.get("example") or "").strip()
        match_template = str(item.get("match") or "")
        if not pattern_id or not example or not match_template:
            raise ValueError("timecode pattern requires id, example, and match")
        if pattern_id in seen_ids:
            raise ValueError(f"duplicate timecode pattern id {pattern_id!r}")
        seen_ids.add(pattern_id)
        expanded = _expand_fragments(match_template, fragments)
        try:
            compiled = re.compile(expanded)
        except re.error as exc:
            raise ValueError(f"invalid regex for pattern {pattern_id!r}: {exc}") from exc
        patterns.append(
            TimecodePattern(
                id=pattern_id,
                example=example,
                match=expanded,
                compiled=compiled,
            )
        )

    hints_raw = raw.get("hints") or []
    if not isinstance(hints_raw, list) or not hints_raw:
        raise ValueError("timecode_patterns.yaml requires a non-empty hints list")
    hints = tuple(_expand_fragments(str(item), fragments) for item in hints_raw)
    for index, hint in enumerate(hints):
        try:
            re.compile(hint)
        except re.error as exc:
            raise ValueError(f"invalid regex for hint[{index}]: {exc}") from exc

    tz_alt = expanded_fragments.get("tz")
    if not tz_alt:
        raise ValueError("timecode_patterns.yaml fragments.tz is required")
    tz_pattern = rf"(?:{tz_alt})"

    return TimecodeCatalog(
        fragments=expanded_fragments,
        patterns=tuple(patterns),
        hints=hints,
        tz_pattern=tz_pattern,
    )


def _catalog() -> TimecodeCatalog:
    return load_timecode_catalog()


# Eager load so import fails fast if the catalog is broken.
PATTERNS: tuple[str, ...] = tuple(item.match for item in _catalog().patterns)
DATE_HINTS: tuple[str, ...] = _catalog().hints
TZ_PATTERN: str = _catalog().tz_pattern


def sanitize_for_dates(text: str) -> SanitizedText:
    """Normalize message text for date matching while retaining original offsets.

    - Unicode-normalize and lowercase
    - Strip Discord markdown marker characters
    - Collapse whitespace runs to a single space

    Matching runs on the sanitized string; use :meth:`SanitizedText.original_span`
    to unsanitize match coordinates before mutating the original message.
    """
    normalized = unicodedata.normalize("NFKC", text)
    out_chars: list[str] = []
    to_original: list[int] = []
    pending_space_orig: int | None = None

    for index, char in enumerate(normalized):
        if char in _MARKDOWN_CHARS:
            continue
        if char.isspace():
            if not out_chars:
                continue
            if pending_space_orig is None:
                pending_space_orig = index
            continue
        if pending_space_orig is not None:
            out_chars.append(" ")
            to_original.append(pending_space_orig)
            pending_space_orig = None
        out_chars.append(char.lower())
        to_original.append(index)

    return SanitizedText(
        original=text if text == normalized else normalized,
        text="".join(out_chars),
        to_original=tuple(to_original),
    )


def has_explicit_date(text: str) -> bool:
    for pattern in DATE_HINTS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_timezone(text: str) -> ZoneInfo:
    match = re.search(rf"\b({TZ_PATTERN})\b", text, re.IGNORECASE)
    if not match:
        return DEFAULT_TZ
    return ZoneInfo(TZ_MAP[match.group(1).lower()])


def remove_timezone(text: str) -> str:
    return re.sub(
        rf"\b({TZ_PATTERN})\b",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


_ABBREV_WEEKDAY = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}


def _normalize_for_parse(text: str) -> str:
    """Map phrases dateparser handles poorly to equivalent ones it parses reliably."""
    normalized = re.sub(r"\btonight\b", "today", text, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\bnext\s+(?=(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b)",
        "",
        normalized,
        flags=re.IGNORECASE,
    )

    def _expand(match: re.Match[str]) -> str:
        return _ABBREV_WEEKDAY[match.group(0).lower()]

    return re.sub(
        r"\b(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
        _expand,
        normalized,
        flags=re.IGNORECASE,
    )


def next_occurrence(dt: datetime, tz: ZoneInfo) -> datetime:
    now = datetime.now(tz)
    candidate = dt.replace(
        year=now.year,
        month=now.month,
        day=now.day,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def parse_expression(expr: str) -> int | None:
    tz = extract_timezone(expr)
    cleaned = _normalize_for_parse(remove_timezone(expr))
    dt = dateparser.parse(
        cleaned,
        settings={
            "TIMEZONE": tz.key,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    if not has_explicit_date(expr):
        dt = next_occurrence(dt.astimezone(tz), tz)
    return int(dt.astimezone(UTC).timestamp())


def find_candidates(text: str) -> list[_DateMatch]:
    matches: list[_DateMatch] = []
    for pattern in _catalog().patterns:
        for match in pattern.compiled.finditer(text):
            matches.append(
                _DateMatch(
                    start=match.start(),
                    end=match.end(),
                    text=match.group(),
                    length=match.end() - match.start(),
                )
            )

    matches.sort(key=lambda item: (item.start, -item.length))

    final: list[_DateMatch] = []
    for candidate in matches:
        overlap = False
        for existing in final:
            if candidate.start < existing.end and candidate.end > existing.start:
                overlap = True
                break
        if not overlap:
            final.append(candidate)
    return final


def replace_dates(text: str) -> str:
    """Find dates on a sanitized view of ``text``, replace spans in the original."""
    sanitized = sanitize_for_dates(text)
    # Prefer the sanitized.original base when NFKC rewrote characters so spans align.
    source = sanitized.original
    replacements: list[tuple[int, int, str]] = []
    for match in find_candidates(sanitized.text):
        ts = parse_expression(match.text)
        if ts is None:
            continue
        start, end = sanitized.original_span(match.start, match.end)
        replacements.append((start, end, f"<t:{ts}>"))

    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result
