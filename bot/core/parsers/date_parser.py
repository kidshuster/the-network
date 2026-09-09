"""Discord message timecode conversion.

Architecture (extract → interpret → validate → replace):

1. ``sanitize_for_dates`` — normalize text; keep an index map to the original
2. ``protect_non_temporal_spans`` — mask IDs, URLs, versions, slash commands
3. ``find_temporal_candidates`` — broad extraction via ``dateparser.search``
4. ``find_strict_temporal_candidates`` — tiny high-precision regex fallback
5. ``merge_temporal_candidates`` — prefer broader spans; drop overlaps
6. ``parse_expression`` — Network timezone / next-occurrence interpretation
7. ``validate_temporal_candidate`` — drop false positives
8. ``replace_dates`` — map spans back and stitch ``<t:UNIX>`` chips

Extraction locates likely temporal substrings. Interpretation decides what
they mean. Validation decides whether to trust them. Keep those separate so
the extractor stays swappable (e.g. ctparse) without rewriting Network rules.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser  # type: ignore[import-untyped]
from dateparser.search import search_dates  # type: ignore[import-untyped]

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

TZ_PATTERN = "(?:pst|pdt|pt|mst|mdt|mt|cst|cdt|ct|est|edt|et|utc|gmt)"

# Explicit-date cues for next_occurrence gating (interpretation only).
_EXPLICIT_DATE_HINTS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),
    re.compile(r"\d{1,2}/\d{1,2}(?:/\d{2,4})?"),
    re.compile(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:today|tomorrow|tonight|next)\b", re.IGNORECASE),
)

# Tiny high-precision fallback when search_dates misses reliable clock/ISO forms.
_STRICT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\b\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)(?:\s+{TZ_PATTERN})?\b",
        re.IGNORECASE,
    ),
    re.compile(rf"\b\d{{1,2}}:\d{{2}}\s*(?:{TZ_PATTERN})?\b", re.IGNORECASE),
    re.compile(
        r"\b\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b",
    ),
)

# Mask before search so snowflakes / versions / URLs are not treated as dates.
_PROTECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"</[^>]+>"),
    re.compile(r"<a?:\w+:\d+>"),
    re.compile(r"<(?:@[!&]?|#)\d+>"),
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)+\b", re.IGNORECASE),
    re.compile(r"\b\d{17,20}\b"),
    re.compile(r"/mirror\b[^\n]*", re.IGNORECASE),
)

_WEEKDAY_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
_MERIDIEM_RE = re.compile(r"(?<![a-z])(?:am|pm)\b", re.IGNORECASE)
_TZ_WORD_RE = re.compile(rf"\b(?:{TZ_PATTERN})\b", re.IGNORECASE)
_RELATIVE_DAY_RE = re.compile(
    r"\b(?:today|tomorrow|tonight|noon|midnight)\b",
    re.IGNORECASE,
)
_COLON_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_PREPOSITION_RE = re.compile(r"\b(?:at|around|by|after|before|on)\b", re.IGNORECASE)
_THIS_NEXT_WEEKDAY_RE = re.compile(
    r"\b(?:this|next|coming)\s+(?:monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
    re.IGNORECASE,
)
_QUANTITY_UNIT_RE = re.compile(
    r"\b\d+\s+(?:players?|members?|people|million|billion|morale|kills?|"
    r"deaths?|levels?|slots?|seats?|tickets?)\b",
    re.IGNORECASE,
)

_EXPAND_TOKEN = re.compile(
    r"^(?:"
    r"quarter|half|past|to|after|before|at|on|of|around|about|"
    r"evening|morning|night|tonight|today|tomorrow|noon|midnight|"
    r"am|pm|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
    r"jan[a-z]*|feb[a-z]*|mar[a-z]*|apr[a-z]*|may|jun[a-z]*|jul[a-z]*|"
    r"aug[a-z]*|sep[a-z]*|oct[a-z]*|nov[a-z]*|dec[a-z]*|"
    r"next|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"eastern|pacific|central|mountain|"
    r"\d{1,2}(?::\d{2})?|"
    r"pst|pdt|pt|mst|mdt|mt|cst|cdt|ct|est|edt|et|utc|gmt"
    r")$",
    re.IGNORECASE,
)

_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_TRAIL_PUNCT = frozenset(".,;:!?\"')]}>")
_LEAD_PUNCT = frozenset("\"'([{<")

_BARE_INTEGER = re.compile(r"^\d{1,4}$")
_VERSION_LIKE = re.compile(r"^v?\d+\.\d+(?:\.\d+)*$", re.IGNORECASE)
_IP_LIKE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_ISOLATED_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_DENYLIST_PHRASES = frozenset(
    {
        "we",
        "me",
        "you",
        "a",
        "an",
        "the",
        "to",
        "for",
        "on",
        "at",
        "in",
        "of",
        "and",
        "or",
        "by",
        "is",
        "be",
        "now",
    }
)

# Discord markdown markers stripped before date matching (lossy; mapped back).
_MARKDOWN_CHARS = frozenset("*_`~|")

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

_SOURCE_SEARCH = "search_dates"
_SOURCE_STRICT = "strict"
_SOURCE_MERGED = "merged"


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
class ProtectedText:
    """Length-preserving mask of non-temporal machine syntax."""

    text: str
    protected_spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class TemporalCandidate:
    """A candidate temporal phrase located in sanitized/protected text."""

    start: int
    end: int
    text: str
    source: str

    @property
    def length(self) -> int:
        return self.end - self.start


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


def protect_non_temporal_spans(text: str) -> ProtectedText:
    """Mask non-temporal syntax with same-length placeholders (index-preserving)."""

    chars = list(text)
    occupied = [False] * len(chars)
    spans: list[tuple[int, int]] = []

    def _mask_span(start: int, end: int) -> None:
        for index in range(start, end):
            if 0 <= index < len(chars) and not occupied[index]:
                chars[index] = "#"
                occupied[index] = True
        spans.append((start, end))

    for pattern in _PROTECT_PATTERNS:
        for match in pattern.finditer(text):
            _mask_span(match.start(), match.end())
    return ProtectedText(text="".join(chars), protected_spans=tuple(spans))


def has_explicit_date(text: str) -> bool:
    return any(pattern.search(text) for pattern in _EXPLICIT_DATE_HINTS)


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


def _has_meridiem(text: str) -> bool:
    return _MERIDIEM_RE.search(text) is not None


def next_occurrence(
    dt: datetime,
    tz: ZoneInfo,
    *,
    allow_twelve_hour: bool = False,
) -> datetime:
    """Pick the next future clock time in ``tz`` (not the server local zone).

    When ``allow_twelve_hour`` is set (time had no am/pm), also consider the
    opposite meridiem and take the sooner future instant — e.g. at 4:47pm PST,
    ``5:30`` means 5:30pm today, not 5:30am tomorrow.
    """
    now = datetime.now(tz)
    local = dt.astimezone(tz)
    today = local.replace(
        year=now.year,
        month=now.month,
        day=now.day,
        second=0,
        microsecond=0,
    )
    options = [today]
    if allow_twelve_hour and 0 < today.hour < 12:
        options.append(today + timedelta(hours=12))
    future = [option + timedelta(days=1) if option <= now else option for option in options]
    return min(future)


def _hour_token_to_int(token: str) -> int | None:
    lowered = token.lower()
    if lowered in _NUM_WORDS:
        return _NUM_WORDS[lowered]
    if re.fullmatch(r"\d{1,2}", token):
        value = int(token)
        if 1 <= value <= 23:
            return value
    return None


def _soft_normalize(text: str) -> str:
    """Rewrite softer natural-language time phrases into dateparser-friendly forms."""
    normalized = text.strip()
    # Zone names before filler stripping so they stay attached to the phrase.
    normalized = re.sub(r"\beastern\b", "et", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bpacific\b", "pt", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bcentral\b", "ct", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bmountain\b", "mt", normalized, flags=re.IGNORECASE)

    def _quarter_past(match: re.Match[str]) -> str:
        hour = _hour_token_to_int(match.group(1))
        if hour is None:
            return match.group(0)
        return f"{hour}:15"

    def _half_past(match: re.Match[str]) -> str:
        hour = _hour_token_to_int(match.group(1))
        if hour is None:
            return match.group(0)
        return f"{hour}:30"

    normalized = re.sub(
        r"\bquarter\s+past\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        _quarter_past,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bhalf\s+past\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        _half_past,
        normalized,
        flags=re.IGNORECASE,
    )
    # Clock produced by quarter/half past still needs night → evening meridiem.
    normalized = re.sub(
        r"\b(\d{1,2}:\d{2})\s+(?:tonight|evening|night)\b",
        r"today at \1 pm",
        normalized,
        flags=re.IGNORECASE,
    )

    # "saturday evening around nine" → "saturday at 9 pm"
    def _weekday_evening_clock(match: re.Match[str]) -> str:
        weekday = match.group(1)
        hour = _hour_token_to_int(match.group(2))
        if hour is None:
            return match.group(0)
        meridiem = "pm" if hour < 12 else ""
        return f"{weekday} at {hour} {meridiem}".strip()

    normalized = re.sub(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"
        r"\s+(?:evening|night)(?:\s+(?:around|about))?\s+"
        r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
        r"(?!\s*(?:am|pm|:))",
        _weekday_evening_clock,
        normalized,
        flags=re.IGNORECASE,
    )

    # "tomorrow night at eight" / "tonight at eight"
    def _day_night_at_clock(match: re.Match[str]) -> str:
        day = match.group(1).lower()
        if day == "tonight":
            day = "today"
        hour = _hour_token_to_int(match.group(2))
        if hour is None:
            return match.group(0)
        meridiem = "pm" if hour < 12 else ""
        return f"{day} at {hour} {meridiem}".strip()

    normalized = re.sub(
        r"\b(today|tomorrow|tonight)(?:\s+(?:night|evening))?\s+at\s+"
        r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
        r"(?!\s*(?:am|pm|:))",
        _day_night_at_clock,
        normalized,
        flags=re.IGNORECASE,
    )

    normalized = re.sub(
        r"\b(?:evening|morning|night)\s+of\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\baround\s+(noon|midnight)\b",
        r"at \1",
        normalized,
        flags=re.IGNORECASE,
    )

    def _word_clock_relative(match: re.Match[str]) -> str:
        hour = _hour_token_to_int(match.group(1))
        day = match.group(2).lower()
        if hour is None:
            return match.group(0)
        meridiem = "pm" if hour < 12 else ""
        clock = f"{hour} {meridiem}".strip()
        return f"{day} at {clock}"

    normalized = re.sub(
        r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+(today|tomorrow)(?:\s+(?:night|evening))?\b",
        _word_clock_relative,
        normalized,
        flags=re.IGNORECASE,
    )

    def _after_on_weekday(match: re.Match[str]) -> str:
        hour = _hour_token_to_int(match.group(1))
        weekday = match.group(2)
        if hour is None:
            return match.group(0)
        meridiem = "pm" if hour < 12 else ""
        return f"{weekday} at {hour} {meridiem}".strip()

    normalized = re.sub(
        r"\bafter\s+(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)"
        r"(?:\s+evening)?\b",
        _after_on_weekday,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\s+around\s+(noon|midnight)\b",
        r"\1 at \2",
        normalized,
        flags=re.IGNORECASE,
    )

    def _ordinal_day(match: re.Match[str]) -> str:
        day = int(match.group(1))
        now = datetime.now(DEFAULT_TZ)
        month = now.strftime("%B")
        year = now.year
        return f"{month} {day} {year}"

    normalized = re.sub(
        r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\b",
        _ordinal_day,
        normalized,
        flags=re.IGNORECASE,
    )

    # Drop filler words last so earlier rewrites still see "around" / "about".
    normalized = re.sub(
        r"\b(?:this|coming|a|an|the|about|around|little|by|for|sometime)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def parse_expression(expr: str) -> int | None:
    """Interpret a temporal phrase into a UTC unix timestamp using Network rules."""
    cleaned_source = expr.strip()
    if not cleaned_source:
        return None
    softened = _soft_normalize(cleaned_source)
    candidates = [cleaned_source]
    if softened and softened.lower() != cleaned_source.lower():
        candidates.append(softened)

    for candidate in candidates:
        tz = extract_timezone(candidate)
        cleaned = _normalize_for_parse(remove_timezone(candidate))
        if not cleaned:
            continue
        relative_base = datetime.now(tz).replace(tzinfo=None)
        dt = dateparser.parse(
            cleaned,
            settings={
                "TIMEZONE": tz.key,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": relative_base,
            },
        )
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        if not has_explicit_date(candidate) and not has_explicit_date(cleaned_source):
            dt = next_occurrence(
                dt.astimezone(tz),
                tz,
                allow_twelve_hour=not _has_meridiem(cleaned),
            )
        return int(dt.astimezone(UTC).timestamp())
    return None


def validate_temporal_candidate(
    candidate: TemporalCandidate,
    timestamp: int,
    *,
    context: str,
) -> bool:
    """Reject false-positive search hits before replacement.

    ``timestamp`` is produced by ``parse_expression``; this layer does not
    re-interpret the phrase. ``context`` is the sanitized (unprotected) message.
    """
    del timestamp  # Reserved for future absolute-range checks; keep signature stable.
    text = candidate.text.strip().strip(".,;:!?\"'()[]{}")
    if not text:
        return False
    lowered = text.lower()
    if lowered in _DENYLIST_PHRASES:
        return False
    if _BARE_INTEGER.fullmatch(text):
        return False
    if _ISOLATED_YEAR.fullmatch(text):
        return False
    if _VERSION_LIKE.fullmatch(text):
        return False
    if _IP_LIKE.fullmatch(text):
        return False
    if re.fullmatch(r"#+", text):
        return False
    if "#" in text:
        return False
    if _QUANTITY_UNIT_RE.search(context) and _BARE_INTEGER.search(text):
        # "8 players" / "15 million" — numeric token alone is not temporal.
        window_start = max(0, candidate.start - 24)
        window_end = min(len(context), candidate.end + 24)
        window = context[window_start:window_end]
        if _QUANTITY_UNIT_RE.search(window):
            return False

    score = 0
    if _WEEKDAY_RE.search(text):
        score += 3
    if _MONTH_RE.search(text):
        score += 3
    if _MERIDIEM_RE.search(text):
        score += 2
    if _TZ_WORD_RE.search(text):
        score += 2
    if _RELATIVE_DAY_RE.search(text):
        score += 3
    if _COLON_TIME_RE.search(text):
        score += 2
    if _THIS_NEXT_WEEKDAY_RE.search(text):
        score += 3
    if _PREPOSITION_RE.search(text):
        score += 1
    if re.search(
        r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        text,
        re.IGNORECASE,
    ):
        score += 1
    if _BARE_INTEGER.fullmatch(text):
        score -= 5
    if re.fullmatch(r"\d{1,2}", text):
        score -= 3

    return score >= 2


def _locate_phrase(
    haystack: str,
    needle: str,
    *,
    used: list[bool],
    search_from: int = 0,
) -> tuple[int, int] | None:
    """Find the next unused occurrence of ``needle`` starting at ``search_from``."""
    if not needle:
        return None
    start = max(0, search_from)
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return None
        end = index + len(needle)
        if not any(used[index:end]):
            return (index, end)
        start = index + 1


def _trim_candidate_bounds(text: str, protected: str, start: int, end: int) -> tuple[int, int]:
    """Drop masked placeholders and hugging punctuation from a candidate span."""
    while start < end and start < len(protected) and protected[start] == "#":
        start += 1
    while end > start and end - 1 < len(protected) and protected[end - 1] == "#":
        end -= 1
    while start < end and (text[start].isspace() or text[start] in _LEAD_PUNCT):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] in _TRAIL_PUNCT):
        end -= 1
    return start, end


def _token_spans(text: str) -> list[tuple[int, int, str]]:
    return [(match.start(), match.end(), match.group(0)) for match in re.finditer(r"\S+", text)]


def _expand_candidate(text: str, start: int, end: int) -> tuple[int, int]:
    """Grow a weak hit across adjacent temporal/connector tokens."""
    tokens = _token_spans(text)
    if not tokens:
        return start, end
    left = 0
    right = 0
    for index, (tok_start, tok_end, _) in enumerate(tokens):
        if tok_start <= start < tok_end:
            left = index
        if tok_start < end <= tok_end or tok_start <= end - 1 < tok_end:
            right = index

    punct = "".join(_TRAIL_PUNCT | _LEAD_PUNCT)
    while left > 0 and _EXPAND_TOKEN.match(tokens[left - 1][2].strip(punct)):
        left -= 1
    while right + 1 < len(tokens) and _EXPAND_TOKEN.match(
        tokens[right + 1][2].strip(punct)
    ):
        right += 1
    return tokens[left][0], tokens[right][1]


def _normalize_search_phrase(phrase: str) -> str:
    """Strip mask placeholders that search_dates may absorb from protected text."""
    cleaned = re.sub(r"#+", " ", phrase)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip("".join(_TRAIL_PUNCT | _LEAD_PUNCT))


def merge_temporal_candidates(
    text: str,
    candidates: list[TemporalCandidate],
) -> list[TemporalCandidate]:
    """Merge connector-separated fragments, then keep non-overlapping broader spans."""
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda item: item.start)
    bridged: list[TemporalCandidate] = [ordered[0]]
    punct = "".join(_TRAIL_PUNCT | _LEAD_PUNCT)
    for candidate in ordered[1:]:
        prev = bridged[-1]
        gap = text[prev.end : candidate.start].strip()
        gap_tokens = [token.strip(punct) for token in gap.split() if token.strip(punct)]
        if gap_tokens and all(_EXPAND_TOKEN.match(token) for token in gap_tokens):
            start, end = prev.start, candidate.end
            bridged[-1] = TemporalCandidate(
                start=start,
                end=end,
                text=text[start:end],
                source=_SOURCE_MERGED,
            )
        else:
            bridged.append(candidate)

    bridged.sort(key=lambda item: (item.start, -item.length))
    final: list[TemporalCandidate] = []
    for candidate in bridged:
        overlap = False
        for existing in final:
            if candidate.start < existing.end and candidate.end > existing.start:
                overlap = True
                break
        if not overlap:
            final.append(candidate)
    return final


def find_strict_temporal_candidates(
    text: str,
    *,
    protected: str | None = None,
    used: list[bool] | None = None,
) -> list[TemporalCandidate]:
    """Tiny deterministic fallback for clock/ISO forms search_dates may miss."""
    masked = protected if protected is not None else protect_non_temporal_spans(text).text
    occupied = list(used) if used is not None else [False] * len(text)
    raw: list[TemporalCandidate] = []
    for pattern in _STRICT_PATTERNS:
        for match in pattern.finditer(text):
            start, end = _trim_candidate_bounds(text, masked, match.start(), match.end())
            if start >= end:
                continue
            if any(occupied[start:end]):
                continue
            if masked[start:end] and set(masked[start:end]) <= {"#"}:
                continue
            raw.append(
                TemporalCandidate(
                    start=start,
                    end=end,
                    text=text[start:end],
                    source=_SOURCE_STRICT,
                )
            )
    # Prefer broader spans when patterns nest (ISO date+time over bare HH:MM).
    raw.sort(key=lambda item: (item.start, -item.length))
    found: list[TemporalCandidate] = []
    for candidate in raw:
        if any(occupied[candidate.start : candidate.end]):
            continue
        for index in range(candidate.start, candidate.end):
            occupied[index] = True
        found.append(candidate)
    return found


def find_temporal_candidates(
    text: str,
    *,
    protected: str | None = None,
) -> list[TemporalCandidate]:
    """Broad candidate extraction via ``search_dates`` (ngram).

    Operates on protected text for matching; phrase ``text`` is sliced from the
    unprotected ``text`` argument so interpretation sees real words.
    """
    if not text.strip():
        return []

    masked = protected if protected is not None else protect_non_temporal_spans(text).text
    used = [False] * len(masked)
    found: list[TemporalCandidate] = []
    cursor = 0

    try:
        hits = search_dates(
            masked,
            languages=["en"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": True,
            },
            strategy="ngram",
        )
    except Exception:
        hits = None

    for item in hits or ():
        # Intentionally ignore item[1] (search_dates datetime) — interpretation
        # stays in parse_expression so Network TZ / next-occurrence rules win.
        raw_phrase = str(item[0]).strip()
        phrase = _normalize_search_phrase(raw_phrase)
        if not phrase:
            continue
        located = _locate_phrase(masked, phrase, used=used, search_from=cursor)
        if located is None:
            located = _locate_phrase(text, phrase, used=used, search_from=cursor)
        if located is None and raw_phrase != phrase:
            head = raw_phrase.split("#", 1)[0].strip()
            head = _normalize_search_phrase(head)
            if head:
                located = _locate_phrase(masked, head, used=used, search_from=cursor)
                if located is None:
                    located = _locate_phrase(text, head, used=used, search_from=cursor)
        if located is None:
            # Fall back to a full-string scan for this phrase only.
            located = _locate_phrase(masked, phrase, used=used, search_from=0)
            if located is None:
                located = _locate_phrase(text, phrase, used=used, search_from=0)
        if located is None:
            continue
        start, end = _trim_candidate_bounds(text, masked, *located)
        start, end = _expand_candidate(text, start, end)
        start, end = _trim_candidate_bounds(text, masked, start, end)
        if start >= end:
            continue
        if any(used[start:end]):
            continue
        for index in range(start, end):
            used[index] = True
        cursor = end
        found.append(
            TemporalCandidate(
                start=start,
                end=end,
                text=text[start:end],
                source=_SOURCE_SEARCH,
            )
        )

    return found


def add_strict_fallback_candidates(
    text: str,
    candidates: list[TemporalCandidate],
    *,
    protected: str,
) -> list[TemporalCandidate]:
    """Append strict regex hits for spans the broad extractor missed."""
    used = [False] * len(text)
    for candidate in candidates:
        for index in range(candidate.start, candidate.end):
            if 0 <= index < len(used):
                used[index] = True
    strict = find_strict_temporal_candidates(text, protected=protected, used=used)
    return merge_temporal_candidates(text, [*candidates, *strict])


def replace_dates(text: str) -> str:
    """Find dates on a sanitized view of ``text``, replace spans in the original."""
    sanitized = sanitize_for_dates(text)
    source = sanitized.original
    protected = protect_non_temporal_spans(sanitized.text)

    candidates = find_temporal_candidates(sanitized.text, protected=protected.text)
    candidates = add_strict_fallback_candidates(
        sanitized.text,
        candidates,
        protected=protected.text,
    )

    replacements: list[tuple[int, int, str]] = []
    for candidate in candidates:
        timestamp = parse_expression(candidate.text)
        if timestamp is None:
            continue
        if not validate_temporal_candidate(
            candidate,
            timestamp,
            context=sanitized.text,
        ):
            continue
        start, end = sanitized.original_span(candidate.start, candidate.end)
        # Discord timestamp chips need a trailing space when the next character
        # would otherwise glue (e.g. ``<t:…>!`` / ``<t:…>.``), or rendering breaks.
        suffix = " " if end < len(source) and not source[end].isspace() else ""
        replacements.append((start, end, f"<t:{timestamp}>{suffix}"))

    result = source
    for start, end, replacement in sorted(replacements, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result
