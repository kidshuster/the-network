from __future__ import annotations

import pytest

from bot.app.widgets.custom_id import decode, encode
from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import recipe_handler


def test_action_custom_id_roundtrip() -> None:
    handler = recipe_handler(
        "subscription.create",
        client_id=12,
        network_key="stingers",
    )
    assert decode(encode(handler)) == handler


def test_open_recipe_custom_id_roundtrip() -> None:
    handler = recipe_handler("request.join.open")
    assert decode(encode(handler)).recipe == "request.join.open"


def test_legacy_ui_modal_custom_ids_map_to_open_recipes() -> None:
    assert decode("tn1:ui.modal:join_network").recipe == "request.join.open"
    assert decode("tn1:ui.modal:create_network").recipe == "network.create.open"


def test_legacy_request_custom_ids() -> None:
    approve = decode("tn:req_approve:9")
    deny = decode("tn:req_deny:9")
    assert approve.recipe == "request.approve"
    assert approve.arguments["request_id"] == 9
    assert deny.recipe == "request.deny"


def test_legacy_profile_and_delete() -> None:
    assert decode("tn:profile_edit:123").recipe == "client.edit.open"
    assert decode("tn:delete_client:123").recipe == "client.delete.confirm"
    assert decode("tn:network_create").recipe == "network.create.open"


def test_custom_id_rejects_reserved_characters() -> None:
    with pytest.raises(TemplateRenderError):
        encode(recipe_handler("x", bad="a=b"))
