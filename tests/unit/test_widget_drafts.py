from __future__ import annotations

import pytest
from widget_helpers import wire_widget_bot

from bot.app.widgets.drafts import modal, view
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.schema import ViewTemplateSpec
from bot.contracts.widgets import ButtonSpec, recipe_handler


def test_unique_tags_validated_at_load() -> None:
    with pytest.raises(ValueError, match="duplicate tag"):
        ViewTemplateSpec.model_validate(
            {
                "kind": "view",
                "id": "dup",
                "components": [
                    {"type": "button", "tag": "a", "label": "A"},
                    {"type": "button", "tag": "a", "label": "B"},
                ],
            }
        )


def test_missing_and_unknown_bindings() -> None:
    bot = wire_widget_bot()
    draft = view("moderator_review")
    with pytest.raises(TemplateRenderError, match="unbound tags"):
        draft.build(bot)

    draft = (
        view("moderator_review")
        .bind("accept_button", recipe_handler("request.approve", request_id=1))
        .bind("deny_button", recipe_handler("request.deny", request_id=1))
        .bind("extra", recipe_handler("ui.dismiss"))
    )
    with pytest.raises(TemplateRenderError, match="unknown tags"):
        draft.build(bot)


def test_duplicate_bind_rejected() -> None:
    draft = view("join_network").bind("join_button", recipe_handler("request.join.open"))
    with pytest.raises(TemplateRenderError, match="tag bound twice"):
        draft.bind("join_button", recipe_handler("request.join.open"))


def test_missing_and_unknown_slots() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="missing slots"):
        view("blacklist_select").build(bot)

    draft = view("blacklist_select").fill(
        "blacklist",
        [
            ButtonSpec(
                tag="x",
                label="X",
                handler=recipe_handler("ui.dismiss"),
            )
        ],
    )
    draft.fill("nope", [])
    with pytest.raises(TemplateRenderError, match="unknown slots"):
        draft.build(bot)


def test_unregistered_recipe_rejected() -> None:
    bot = wire_widget_bot()
    draft = view("join_network").bind("join_button", recipe_handler("does.not.exist"))
    with pytest.raises(TemplateRenderError, match="unregistered recipe"):
        draft.build(bot)


def test_dynamic_without_handler_rejected() -> None:
    bot = wire_widget_bot()
    draft = view("blacklist_select").fill(
        "blacklist",
        [ButtonSpec(tag="x", label="X", handler=None)],
    )
    with pytest.raises(TemplateRenderError, match="missing handler"):
        draft.build(bot)


def test_unresolved_placeholder_rejected() -> None:
    bot = wire_widget_bot()
    draft = (
        view("network_profile")
        .fill("network_actions", [])
        .bind("timecode_button", recipe_handler("client.toggle_timecode", client_id=1))
        .bind("read_only_button", recipe_handler("client.toggle_read_only", client_id=1))
        .bind("edit_button", recipe_handler("client.edit.open", client_id=1))
        .bind("delete_button", recipe_handler("client.delete.confirm", client_id=1))
    )
    with pytest.raises(TemplateRenderError, match="unresolved placeholder"):
        draft.build(bot)


def test_modal_requires_submit_recipe() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="modal requires submit recipe"):
        modal("join_network").build(bot)


def test_built_view_has_tn1_custom_ids() -> None:
    bot = wire_widget_bot()
    built = (
        view("join_network")
        .bind("join_button", recipe_handler("request.join.open"))
        .build(bot)
    )
    assert built.children[0].custom_id.startswith("tn1:request.join.open")
