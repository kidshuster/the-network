from __future__ import annotations

from bot.services.join_requests_sticky import (
    build_how_to_join_embed,
    build_how_to_join_footer,
    format_how_to_join_sticky_location,
    parse_how_to_join_sticky_location,
)


def test_build_how_to_join_embed_covers_setup_and_subscribe() -> None:
    embed = build_how_to_join_embed()
    body = (embed.description or "") + " ".join(field.value or "" for field in embed.fields)
    assert "Enable Community" in body
    assert "Announcement" in body
    assert "Join Network" in body
    assert "network-profile" in body
    assert "Blacklist" in body
    assert embed.footer is not None
    assert embed.footer.text == build_how_to_join_footer()


def test_parse_how_to_join_sticky_location_supports_channel_message_pair() -> None:
    location = parse_how_to_join_sticky_location("123:456")
    assert location is not None
    assert location.channel_id == 123
    assert location.message_id == 456


def test_parse_how_to_join_sticky_location_supports_legacy_message_only() -> None:
    location = parse_how_to_join_sticky_location("456", fallback_channel_id=123)
    assert location is not None
    assert location.channel_id == 123
    assert location.message_id == 456


def test_format_how_to_join_sticky_location() -> None:
    assert format_how_to_join_sticky_location(123, 456) == "123:456"
