from __future__ import annotations

from bot.ui.custom_ids import (
    delete_client_button,
    join_server_button,
    parse_delete_client_button,
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


def test_delete_client_custom_id_roundtrip() -> None:
    custom_id = delete_client_button(12345)
    assert parse_delete_client_button(custom_id) == 12345


def test_network_create_button() -> None:
    from bot.ui.custom_ids import network_create_button, network_delete_button

    assert network_create_button() == "tn:network_create"
    assert network_delete_button() == "tn:network_delete"


def test_request_action_custom_ids() -> None:
    assert parse_request_action_button(request_approve_button(9)) == ("approve", 9)
    assert parse_request_action_button(request_deny_button(9)) == ("deny", 9)
