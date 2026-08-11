from __future__ import annotations

from bot.app.widgets.custom_id import decode, encode
from bot.app.widgets.models import ActionBinding


def test_action_custom_id_roundtrip() -> None:
    binding = ActionBinding(
        action="subscription.create",
        arguments={"client_id": 12, "network_key": "stingers"},
    )
    assert decode(encode(binding)) == binding


def test_ui_modal_custom_id_roundtrip() -> None:
    binding = ActionBinding(action="ui.modal:join_network")
    assert decode(encode(binding)).action == "ui.modal:join_network"


def test_legacy_request_custom_ids() -> None:
    approve = decode("tn:req_approve:9")
    deny = decode("tn:req_deny:9")
    assert approve.action == "request.approve"
    assert approve.arguments["request_id"] == 9
    assert deny.action == "request.deny"


def test_legacy_profile_and_delete() -> None:
    assert decode("tn:profile_edit:123").action == "ui.modal:edit_client_profile"
    assert decode("tn:delete_client:123").action == "ui.view:delete_client_confirm"
    assert decode("tn:network_create").action == "ui.modal:create_network"
