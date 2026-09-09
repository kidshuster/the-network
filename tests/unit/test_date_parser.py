from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bot.core.parsers import date_parser as date_parser_module
from bot.core.parsers.date_parser import (
    TemporalCandidate,
    add_strict_fallback_candidates,
    extract_timezone,
    find_strict_temporal_candidates,
    find_temporal_candidates,
    merge_temporal_candidates,
    parse_expression,
    protect_non_temporal_spans,
    replace_dates,
    sanitize_for_dates,
    validate_temporal_candidate,
)

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
            "We need 8 players",
            "version 1.2.3 is live",
            "v1.3.2",
            "See <#123456789012345678> for details",
            "Run </network status:123456789012345678> please",
            "https://example.com/path/2026-01-01",
        ],
    )
    def test_unchanged(self, text: str) -> None:
        _assert_unchanged(text)


class TestOrderIndependentPhrases:
    def test_date_then_time_matches_time_then_date(self) -> None:
        moment = datetime(2026, 8, 14, 12, 0, tzinfo=PT)
        with _freeze_now(moment):
            a = replace_dates("raid 9/11 at 5:30 pm pst")
            b = replace_dates("raid 5:30 pm pst on 9/11")
        assert TIMECODE.findall(a) == TIMECODE.findall(b)
        assert len(TIMECODE.findall(a)) == 1


class TestSofterNaturalLanguage:
    @pytest.mark.parametrize(
        "text",
        [
            "Can we do the raid around eight tomorrow night?",
            "Let's meet a little after 7 on Friday evening.",
            "I should be online by quarter past nine tonight.",
            "How about this coming Sunday around noon?",
            "The run is planned for the evening of September 14.",
            "Raid should start sometime around 8 tomorrow.",
            "Can everyone make next Friday at about 7 PM PST?",
            "We'll probably go Saturday evening around nine.",
            "Let's try the 14th at noon.",
            "Maybe tomorrow night at eight eastern.",
        ],
    )
    def test_converts(self, text: str) -> None:
        _assert_converts(text)


class TestProtectNonTemporalSpans:
    def test_discord_snowflake_is_protected(self) -> None:
        text = "my id is 1535347363604865105 thanks"
        protected = protect_non_temporal_spans(text)
        assert len(protected.text) == len(text)
        assert "1535347363604865105" not in protected.text
        assert any(
            text[start:end] == "1535347363604865105"
            for start, end in protected.protected_spans
        )

    def test_url_version_command_and_mirror_are_protected(self) -> None:
        text = (
            "see https://example.com/foo/2026/10/15 version 1.3.2 "
            "run </network status:123456789012345678> "
            "/mirror id:1535347363604865105 mirrorkey:stinghublive."
        )
        protected = protect_non_temporal_spans(text)
        assert "https://" not in protected.text
        assert "1.3.2" not in protected.text
        assert "</network" not in protected.text
        assert "mirrorkey" not in protected.text
        assert len(protected.text) == len(text)


class TestFindTemporalCandidates:
    def test_repeated_temporal_phrases_keep_distinct_offsets(self) -> None:
        text = "meet friday at 8, then friday at 10"
        candidates = find_temporal_candidates(text)
        assert len(candidates) >= 2
        spans = [(c.start, c.end) for c in candidates]
        assert spans[0] != spans[1]
        assert all(text[start:end] for start, end in spans)

    def test_extractor_finds_natural_weekday_phrase(self) -> None:
        text = "how about this coming sunday around noon?"
        candidates = find_temporal_candidates(text)
        assert candidates
        joined = " ".join(c.text for c in candidates)
        assert "sunday" in joined
        assert "noon" in joined


class TestValidateTemporalCandidate:
    def test_bare_player_count_is_rejected(self) -> None:
        context = "there are 8 players in the raid"
        candidate = TemporalCandidate(start=10, end=11, text="8", source="search_dates")
        assert not validate_temporal_candidate(candidate, 1, context=context)

    def test_clock_with_timezone_is_accepted(self) -> None:
        context = "raid at 8 pm pst"
        candidate = TemporalCandidate(start=8, end=16, text="8 pm pst", source="strict")
        assert validate_temporal_candidate(candidate, 1, context=context)


class TestStrictFallback:
    def test_strict_fallback_recovers_24_hour_utc_time(self) -> None:
        # Mask the whole string as "used" for search, then strict should still fire
        # when called on an empty used mask for a form search_dates sometimes skips.
        text = "reset 20:30 utc please"
        strict = find_strict_temporal_candidates(text)
        assert any("20:30" in c.text.lower() for c in strict)
        assert replace_dates(text) != text


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

    def test_friday_saturday_alternatives(self) -> None:
        result = replace_dates("Friday at 8 works, otherwise Saturday at 9")
        assert len(TIMECODE.findall(result)) == 2

    def test_two_clock_times_same_day(self) -> None:
        result = replace_dates("Doors open at 7 PM and the event starts at 8 PM")
        assert len(TIMECODE.findall(result)) == 2

    def test_slash_command_with_nearby_time(self) -> None:
        text = "Raid at 8 pm pst — run </network status:123456789012345678> after"
        _assert_converts(text, preserved=("</network status:123456789012345678>",))

    def test_time_only_phrase_in_sentence(self) -> None:
        _assert_converts("we are grouping at 4 pm pst")


class TestTimezoneAliasInterpretation:
    """parse_expression owns Network TZ aliases — search_dates must not redefine them."""

    @pytest.mark.parametrize(
        ("expr", "tz_key", "local_hour"),
        [
            ("8 pm pst", "America/Los_Angeles", 20),
            ("8 pm pdt", "America/Los_Angeles", 20),
            ("8 pm pt", "America/Los_Angeles", 20),
            ("8 pm mst", "America/Denver", 20),
            ("8 pm mdt", "America/Denver", 20),
            ("8 pm mt", "America/Denver", 20),
            ("8 pm cst", "America/Chicago", 20),
            ("8 pm cdt", "America/Chicago", 20),
            ("8 pm ct", "America/Chicago", 20),
            ("8 pm est", "America/New_York", 20),
            ("8 pm edt", "America/New_York", 20),
            ("8 pm et", "America/New_York", 20),
            ("20:00 utc", "UTC", 20),
            ("20:00 gmt", "UTC", 20),
        ],
    )
    def test_alias_maps_to_expected_zone(
        self, expr: str, tz_key: str, local_hour: int
    ) -> None:
        tz = ZoneInfo(tz_key)
        moment = datetime(2026, 9, 9, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        with _freeze_now(moment):
            ts = parse_expression(expr)
        assert extract_timezone(expr).key == tz_key
        _assert_timestamp_local(
            ts, datetime(2026, 9, 9, local_hour, 0, tzinfo=tz)
        )


class TestParseExpressionExactness:
    def test_default_timezone_is_eastern(self) -> None:
        moment = datetime(2026, 9, 9, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        with _freeze_now(moment):
            ts = parse_expression("8 pm")
        _assert_timestamp_local(
            ts, datetime(2026, 9, 9, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        )

    def test_quarter_past_tonight_is_evening(self) -> None:
        moment = datetime(2026, 9, 9, 15, 0, tzinfo=ZoneInfo("America/New_York"))
        with _freeze_now(moment):
            ts = parse_expression("quarter past nine tonight")
        _assert_timestamp_local(
            ts, datetime(2026, 9, 9, 21, 15, tzinfo=ZoneInfo("America/New_York"))
        )

    def test_half_past_tonight_is_evening(self) -> None:
        moment = datetime(2026, 9, 9, 15, 0, tzinfo=ZoneInfo("America/New_York"))
        with _freeze_now(moment):
            ts = parse_expression("half past eight tonight")
        _assert_timestamp_local(
            ts, datetime(2026, 9, 9, 20, 30, tzinfo=ZoneInfo("America/New_York"))
        )

    def test_eastern_zone_word(self) -> None:
        moment = datetime(2026, 9, 9, 12, 0, tzinfo=ZoneInfo("America/New_York"))
        with _freeze_now(moment):
            ts = parse_expression("tomorrow night at eight eastern")
        _assert_timestamp_local(
            ts, datetime(2026, 9, 10, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        )

    def test_empty_expression_returns_none(self) -> None:
        assert parse_expression("") is None
        assert parse_expression("   ") is None


class TestMergeTemporalCandidates:
    def test_prefers_broader_bridged_span(self) -> None:
        text = "saturday at 10am pst"
        fragments = [
            TemporalCandidate(0, 8, "saturday", "search_dates"),
            TemporalCandidate(12, 20, "10am pst", "strict"),
        ]
        merged = merge_temporal_candidates(text, fragments)
        assert len(merged) == 1
        assert merged[0].text == "saturday at 10am pst"
        assert merged[0].source == "merged"

    def test_does_not_merge_across_clause_boundary(self) -> None:
        text = "friday at 8 then saturday at 9"
        fragments = [
            TemporalCandidate(0, 11, "friday at 8", "search_dates"),
            TemporalCandidate(17, 30, "saturday at 9", "search_dates"),
        ]
        merged = merge_temporal_candidates(text, fragments)
        assert len(merged) == 2


class TestAddStrictFallback:
    def test_fills_gap_when_search_misses_iso_datetime(self) -> None:
        text = "maintenance window 2026-09-14 18:30"
        # Simulate search returning nothing useful.
        filled = add_strict_fallback_candidates(text, [], protected=text)
        assert any("2026-09-14" in c.text for c in filled)
        assert any(c.source == "strict" for c in filled)


class TestExtractionIgnoresSearchDatetime:
    def test_search_dates_datetime_is_not_authoritative(self) -> None:
        """Even if search_dates invents a bizarre datetime, Network parse wins."""
        bogus = datetime(1999, 1, 1, 0, 0, tzinfo=UTC)

        def _fake_search(*_args, **_kwargs):
            return [("8 pm pst", bogus)]

        moment = datetime(2026, 9, 9, 12, 0, tzinfo=PT)
        with (
            patch.object(date_parser_module, "search_dates", _fake_search),
            _freeze_now(moment),
        ):
            result = replace_dates("raid at 8 pm pst")
        match = TIMECODE.search(result)
        assert match is not None
        ts = int(match.group(0)[3:-1])
        _assert_timestamp_local(ts, datetime(2026, 9, 9, 20, 0, tzinfo=PT))


class TestProtectNearbyRealTime:
    def test_url_date_masked_but_nearby_schedule_converts(self) -> None:
        text = "See https://example.com/2026/09/14 then raid tomorrow at noon"
        result = _assert_converts(text, preserved=("https://example.com/2026/09/14",))
        assert len(TIMECODE.findall(result)) == 1

    def test_version_masked_but_nearby_clock_converts(self) -> None:
        text = "Patch 1.4.2 drops Friday at 7 pm pst"
        result = _assert_converts(text, preserved=("1.4.2",))
        assert len(TIMECODE.findall(result)) == 1


class TestValidateRejectsMachineNoise:
    @pytest.mark.parametrize(
        "phrase",
        ["2026", "1.3.2", "v1.4.2", "8.8.8.8", "42", "###", "we", "now"],
    )
    def test_rejects_non_temporal_tokens(self, phrase: str) -> None:
        candidate = TemporalCandidate(0, len(phrase), phrase, "search_dates")
        assert not validate_temporal_candidate(candidate, 1, context=phrase)

    def test_rejects_masked_residue(self) -> None:
        candidate = TemporalCandidate(0, 5, "8 ##", "search_dates")
        assert not validate_temporal_candidate(candidate, 1, context="8 ##")


class TestReplaceDatesEdgeCases:
    def test_empty_and_whitespace_unchanged(self) -> None:
        assert replace_dates("") == ""
        assert replace_dates("   ") == "   "

    def test_three_times_replaced_in_reverse_order(self) -> None:
        text = "A at 1 pm pst, B at 2 pm pst, C at 3 pm pst"
        result = replace_dates(text)
        codes = TIMECODE.findall(result)
        assert len(codes) == 3
        # Spans must remain left-to-right after reverse-apply stitching.
        assert result.index(codes[0]) < result.index(codes[1]) < result.index(codes[2])

    def test_inline_code_and_spoiler_together(self) -> None:
        text = "Raid ||Saturday at 10am pst|| and backup `Sunday at noon`"
        result = replace_dates(text)
        assert len(TIMECODE.findall(result)) == 2
        assert "|" not in result
        assert "`" not in result


class TestCandidateSourceTags:
    def test_search_candidates_tagged(self) -> None:
        candidates = find_temporal_candidates("friday at 3 pm")
        assert candidates
        assert all(c.source == "search_dates" for c in candidates)

    def test_strict_candidates_tagged(self) -> None:
        candidates = find_strict_temporal_candidates("reset 20:30 utc")
        assert candidates
        assert all(c.source == "strict" for c in candidates)
