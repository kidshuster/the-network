from __future__ import annotations

from bot.ui.custom_ids import (
    join_server_button,
    parse_join_server_button,
    parse_profile_edit_button,
    parse_request_action_button,
    profile_edit_button,
    request_approve_button,
    request_deny_button,
)


def test_join_server_custom_id_roundtrip() -> None:
    custom_id = join_server_button("stingers")
    assert parse_join_server_button(custom_id) == "stingers"


def test_profile_edit_custom_id_roundtrip() -> None:
    custom_id = profile_edit_button(12345)
    assert parse_profile_edit_button(custom_id) == 12345


def test_request_action_custom_ids() -> None:
    assert parse_request_action_button(request_approve_button(9)) == ("approve", 9)
    assert parse_request_action_button(request_deny_button(9)) == ("deny", 9)
