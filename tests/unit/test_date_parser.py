from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bot.core.parsers import date_parser as date_parser_module
from bot.core.parsers.date_parser import parse_expression, replace_dates, sanitize_for_dates

TIMECODE = re.compile(r"<t:\d+>")
PT = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")


def _freeze_now(moment: datetime):
    """Patch date_parser.datetime so now()/parsing anchor at ``moment``."""

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: ZoneInfo | None = None) -> datetime:
            if tz is None:
                return moment.astimezone(UTC).replace(tzinfo=None)
            return moment.astimezone(tz)

    return patch.object(date_parser_module, "datetime", FrozenDateTime)


def _assert_timestamp_local(ts: int | None, expected: datetime) -> None:
    assert ts is not None
    got = datetime.fromtimestamp(ts, expected.tzinfo)
    assert got == expected


def _assert_converts(input_text: str, *, preserved: tuple[str, ...] = ()) -> str:
    result = replace_dates(input_text)
    assert TIMECODE.search(result) is not None, f"expected timecode in {result!r}"
    assert result != input_text, f"expected conversion for {input_text!r}"
    for fragment in preserved:
        assert fragment in result, f"expected {fragment!r} to remain in {result!r}"
    return result


def _assert_unchanged(input_text: str) -> None:
    assert replace_dates(input_text) == input_text


class TestNextOccurrenceUsesParsedTimezone:
    """Relative 'next time' / today / tomorrow must use the parsed TZ, not server local."""

    def test_time_only_uses_pst_now_across_utc_midnight(self) -> None:
        # 02:00 UTC Aug 15 == 19:00 PDT Aug 14 — 8pm PST is still later tonight.
        moment = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
        with _freeze_now(moment):
            ts = parse_expression("8 pm pst")
        _assert_timestamp_local(ts, datetime(2026, 8, 14, 20, 0, tzinfo=PT))

    def test_today_uses_pst_calendar_day_not_utc(self) -> None:
        moment = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
        with _freeze_now(moment):
            ts = parse_expression("today at 8 pm pst")
        _assert_timestamp_local(ts, datetime(2026, 8, 14, 20, 0, tzinfo=PT))

    def test_tomorrow_uses_pst_calendar_day_not_utc(self) -> None:
        moment = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)
        with _freeze_now(moment):
            ts = parse_expression("tomorrow at 5 pm pst")
        _assert_timestamp_local(ts, datetime(2026, 8, 15, 17, 0, tzinfo=PT))

    def test_ambiguous_hhmm_picks_sooner_twelve_hour_slot_in_pst(self) -> None:
        # 16:47 PDT — next "5:30" in PST is 5:30pm today, not 5:30am tomorrow.
        moment = datetime(2026, 8, 14, 16, 47, tzinfo=PT)
        with _freeze_now(moment):
            ts = parse_expression("5:30 pst")
        _assert_timestamp_local(ts, datetime(2026, 8, 14, 17, 30, tzinfo=PT))

    def test_explicit_meridiem_not_flipped(self) -> None:
        moment = datetime(2026, 8, 14, 16, 47, tzinfo=PT)
        with _freeze_now(moment):
            ts = parse_expression("5:30 am pst")
        _assert_timestamp_local(ts, datetime(2026, 8, 15, 5, 30, tzinfo=PT))


class TestTimeWithTimezone:
    @pytest.mark.parametrize(
        "text",
        [
            "we are grouping at 4 pm pst",
            "Raid at 8 PM PST",
            "Server reset at 16:00 utc",
            "Doors at 9:30 pm est",
            "Match starts at 7 pm cdt",
            "Queue at 18:00 gmt",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)


class TestTimeWithoutTimezone:
    @pytest.mark.parametrize(
        "text",
        [
            "Raid starts at 8 PM",
            "Doors open at 18:30",
            "Roll call at 9:15 am",
            "Practice at 4pm",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)


class TestRelativeDateAndTime:
    @pytest.mark.parametrize(
        "text",
        [
            "Garden of Corpses today at 8 pm pst!",
            "Reminder tomorrow at noon",
            "Stream tonight at 9 pm est",
            "Meeting friday at 3 pm",
            "Event next friday at 7 pm cst",
            "Official end time will be Saturday at 10am pst.",
            "Official end time will be Saturday, at 10am pst.",
            "Official end time will be Saturday 10am pst.",
            "Official end time will be Sat at 10am pst.",
            "Official end time will be this Saturday at 10am pst.",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)

    def test_weekday_time_is_single_timecode(self) -> None:
        for text in (
            "Official end time will be Saturday at 10am pst.",
            "Official end time will be Saturday, at 10am pst.",
            "Official end time will be Saturday 10am pst.",
            "Official end time will be Sat at 10am pst.",
        ):
            result = replace_dates(text)
            assert len(TIMECODE.findall(result)) == 1, result
            assert "Saturday" not in result and "Sat" not in result


class TestCalendarDateAndTime:
    @pytest.mark.parametrize(
        "text",
        [
            "Launch Jan 15, 2026 at 8 pm",
            "Signup by 3/15/2026 4:00 pm",
            "Maintenance 2026-08-07 14:30",
            "Party March 3 2026 6 pm",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)


class TestNamedDayparts:
    @pytest.mark.parametrize(
        "text",
        [
            "Break at noon then continue",
            "Reset at midnight",
            "Daily cap at midnight pst",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)


class TestPlainTextUnchanged:
    @pytest.mark.parametrize(
        "text",
        [
            "Welcome to the server!",
            "See you at never o'clock",
            "/mirror id:1535347363604865105 mirrorkey:stinghublive.",
            "Use /lfg to sign up — no schedule yet",
            "Check the pinned message for rules",
        ],
    )
    def test_unchanged(self, text: str) -> None:
        _assert_unchanged(text)


class TestSanitizeForDates:
    def test_lowercase_and_collapse_whitespace(self) -> None:
        sanitized = sanitize_for_dates("Saturday   at\t10AM   PST")
        assert sanitized.text == "saturday at 10am pst"
        start, end = sanitized.original_span(0, len(sanitized.text))
        assert sanitized.original[start:end] == "Saturday   at\t10AM   PST"

    def test_strips_markdown_markers_but_maps_back(self) -> None:
        original = "Ends **Saturday at 10am pst**."
        sanitized = sanitize_for_dates(original)
        assert "saturday at 10am pst" in sanitized.text
        assert "*" not in sanitized.text
        # Unsanitize absorbs hugging markdown wrappers so replacements stay balanced.
        match_start = sanitized.text.index("saturday at 10am pst")
        match_end = match_start + len("saturday at 10am pst")
        start, end = sanitized.original_span(match_start, match_end)
        assert original[start:end] == "**Saturday at 10am pst**"


class TestFormattingResilience:
    @pytest.mark.parametrize(
        "text",
        [
            "Official end time will be **Saturday at 10am pst**.",
            "Official end time will be **Saturday** at 10AM PST.",
            "Official end time will be _Saturday at 10am pst_.",
            "Official end time will be ||Saturday at 10am pst||.",
            "Official end time will be Saturday   at   10AM   pst.",
            "Official end time will be SATURDAY AT 10AM PST.",
        ],
    )
    def test_converts_despite_formatting(self, text: str) -> None:
        result = _assert_converts(text)
        assert len(TIMECODE.findall(result)) == 1, result
        assert "Saturday" not in result and "SATURDAY" not in result
        # Hugging markdown wrappers are absorbed with the match (no dangling ** / _).
        assert "*" not in result
        assert "_" not in result
        assert "|" not in result
        assert result.startswith("Official end time will be <t:")
        assert result.endswith("> .")


class TestRealWorldSmoke:
    def test_garden_of_corpses_with_mirror_command(self) -> None:
        text = (
            "Garden of Corpses today at 8 pm pst!\n\n"
            "/mirror id:1535347363604865105 mirrorkey:stinghublive."
        )
        result = _assert_converts(
            text,
            preserved=("/mirror id:1535347363604865105 mirrorkey:stinghublive.",),
        )
        assert result.startswith("Garden of Corpses <t:")
        assert "> !" in result
        assert "mirrorkey" not in result.split("!\n\n")[0]

    def test_injects_space_after_timestamp_before_glued_chars(self) -> None:
        result = _assert_converts("raid today at 8 pm pst!")
        assert TIMECODE.search(result) is not None
        assert result.endswith("> !")
        # Already-spaced followers must not get a double space.
        spaced = _assert_converts("raid today at 8 pm pst tonight")
        assert ">  " not in spaced

    def test_multiple_times_in_one_message(self) -> None:
        result = replace_dates("Meet at 4 pm pst and again tomorrow at noon")
        assert len(TIMECODE.findall(result)) == 2

    def test_slash_command_with_nearby_time(self) -> None:
        text = "Raid at 8 pm pst — run </network status:123456789012345678> after"
        _assert_converts(text, preserved=("</network status:123456789012345678>",))

    def test_time_only_phrase_in_sentence(self) -> None:
        _assert_converts("we are grouping at 4 pm pst")
