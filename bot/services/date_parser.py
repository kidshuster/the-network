from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser  # type: ignore[import-untyped]

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

TZ_PATTERN = r"(?:pst|pdt|pt|mst|mdt|mt|cst|cdt|ct|est|edt|et|utc|gmt)"

PATTERNS = [
    r"\b\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?(?:\s+\w+)?\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}(?:\s+\d{1,2}:\d{2})?(?:\s*(?:am|pm))?(?:\s+\w+)?\b",
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"[a-z]*\.?\s+\d{1,2}"
    r"(?:,?\s+\d{2,4})?"
    r"(?:\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?"
    r"(?:\s+\w+)?\b",
    r"\b(?:today|tomorrow|tonight)(?:\s+at\s+\S+(?:\s+\S+)*)?",
    r"\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+at\s+\S+(?:\s+\S+)*)?",
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"(?:\s+at\s+\S+(?:\s+\S+)*)?",
    r"\b(?:noon|midnight)\b",
    rf"\b\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)\s*(?:{TZ_PATTERN})?\b",
    rf"\b\d{{1,2}}:\d{{2}}\s*(?:{TZ_PATTERN})?\b",
]

DATE_HINTS = [
    r"\d{4}-\d{1,2}-\d{1,2}",
    r"\d{1,2}/\d{1,2}/\d{2,4}",
    r"\bjan\b|\bfeb\b|\bmar\b|\bapr\b|\bmay\b|\bjun\b|\bjul\b|\baug\b|\bsep\b|\bsept\b|\boct\b|\bnov\b|\bdec\b",
    r"\bmonday\b|\btuesday\b|\bwednesday\b|\bthursday\b|\bfriday\b|\bsaturday\b|\bsunday\b",
    r"\btoday\b|\btomorrow\b|\btonight\b|\bnext\b",
]


@dataclass(frozen=True)
class _DateMatch:
    start: int
    end: int
    text: str
    length: int


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
    cleaned = remove_timezone(expr)
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
    for pattern in PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
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
    replacements: list[tuple[int, int, str]] = []
    for match in find_candidates(text):
        ts = parse_expression(match.text)
        if ts is None:
            continue
        replacements.append((match.start, match.end, f"<t:{ts}>"))

    result = text
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result
