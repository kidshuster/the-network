from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from pydantic import ValidationError
from widget_helpers import wire_widget_bot

from bot.app.widgets.custom_id import decode, encode
from bot.app.widgets.dispatch import RenderedView
from bot.app.widgets.drafts import view
from bot.app.widgets.errors import TemplateRenderError
from bot.app.widgets.loader import clear_widget_cache
from bot.app.widgets.schema import ModalTemplateSpec, ViewTemplateSpec
from bot.contracts.widgets import SelectOptionSpec, SelectSpec, recipe_handler
from bot.core.text import truncate_external_text
from bot.errors import UserFacingError

_FIXTURE_VIEWS = Path(__file__).parent / "fixtures" / "widgets" / "views"


def test_button_style_literal_rejects_invalid() -> None:
    with pytest.raises(ValidationError, match="style"):
        ViewTemplateSpec.model_validate(
            {
                "kind": "view",
                "id": "x",
                "components": [
                    {"type": "button", "tag": "a", "label": "A", "style": "rainbow"}
                ],
            }
        )


def test_button_row_bounds() -> None:
    with pytest.raises(ValidationError, match="row"):
        ViewTemplateSpec.model_validate(
            {
                "kind": "view",
                "id": "x",
                "components": [
                    {"type": "button", "tag": "a", "label": "A", "row": 5}
                ],
            }
        )


def test_modal_duplicate_field_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate modal field"):
        ModalTemplateSpec.model_validate(
            {
                "kind": "modal",
                "id": "x",
                "title": "Title",
                "fields": [
                    {"id": "a", "label": "A"},
                    {"id": "a", "label": "B"},
                ],
            }
        )


def test_modal_title_limit() -> None:
    ModalTemplateSpec.model_validate(
        {
            "kind": "modal",
            "id": "x",
            "title": "T" * 45,
            "fields": [{"id": "a", "label": "A"}],
        }
    )
    with pytest.raises(ValidationError):
        ModalTemplateSpec.model_validate(
            {
                "kind": "modal",
                "id": "x",
                "title": "T" * 46,
                "fields": [{"id": "a", "label": "A"}],
            }
        )


def test_substituted_button_label_overflow_rejected() -> None:
    bot = wire_widget_bot()
    # YAML label is "Timecodes: {timecode_state}" (11 chars prefix) → 70 X's => 81 chars.
    with pytest.raises(TemplateRenderError, match="exceeds Discord limit"):
        (
            view("network_profile", timecode_state="X" * 70)
            .fill("network_actions", [])
            .bind("timecode_button", recipe_handler("client.toggle_timecode", client_id=1))
            .bind("edit_button", recipe_handler("client.edit.open", client_id=1))
            .bind("delete_button", recipe_handler("client.delete.confirm", client_id=1))
            .build(bot)
        )


def test_disabled_static_yaml_button_requires_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    import bot.app.widgets.loader as loader

    monkeypatch.setattr(loader, "_VIEWS_DIR", _FIXTURE_VIEWS)
    clear_widget_cache()
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="unbound tags"):
        view("disabled_static").build(bot)
    built = (
        view("disabled_static")
        .bind("locked_button", recipe_handler("ui.dismiss"))
        .build(bot)
    )
    assert built.children[0].disabled is True
    assert built.children[0].custom_id.startswith("tn1:ui.dismiss")
    clear_widget_cache()


def test_custom_id_preserves_numeric_looking_strings() -> None:
    handler = recipe_handler("demo.x", code="001", flag="true", zero=0, empty="")
    restored = decode(encode(handler))
    assert restored.arguments["code"] == "001"
    assert restored.arguments["flag"] == "true"
    assert restored.arguments["zero"] == 0
    assert restored.arguments["empty"] == ""
    assert type(restored.arguments["zero"]) is int


def test_custom_id_rejects_empty_and_duplicate_keys() -> None:
    with pytest.raises(TemplateRenderError, match="empty"):
        encode(recipe_handler("x", **{"": 1}))
    with pytest.raises(TemplateRenderError, match="duplicate"):
        decode("tn1:demo.x:a=!i1:a=!i2")


def test_custom_id_rejects_reserved_key_and_malformed_marker() -> None:
    with pytest.raises(TemplateRenderError, match="reserved"):
        encode(recipe_handler("x", **{"a=b": 1}))
    with pytest.raises(TemplateRenderError, match="malformed typed"):
        decode("tn1:demo.x:a=!z9")
    with pytest.raises(TemplateRenderError, match="malformed int"):
        decode("tn1:demo.x:a=!i")


def test_custom_id_rejects_oversized_on_decode() -> None:
    oversized = "tn1:demo.x:payload=!" + ("s" + ("y" * 120))
    with pytest.raises(TemplateRenderError, match="exceeds"):
        decode(oversized)


def test_legacy_formats_still_decode() -> None:
    assert decode("tn:req_approve:9").recipe == "request.approve"
    assert decode("tn1:ui.modal:join_network").recipe == "request.join.open"


def test_truncate_external_text_visible() -> None:
    assert truncate_external_text("abcdef", limit=10) == "abcdef"
    assert truncate_external_text("abcdef", limit=4) == "abc…"
    assert truncate_external_text("a", limit=1) == "a"
    assert truncate_external_text("ab", limit=1) == "…"


async def test_migrate_confirm_blocks_incomplete() -> None:
    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.required_keys = {"admin", "rules"}
    view_obj.candidates = {"admin": {1, 2}, "rules": {3}}
    view_obj.resolutions = {"admin": 1}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    await bot.recipe_registry.run("ui.migrate.confirm", interaction=interaction)
    assert view_obj.decision is None
    interaction.response.send_message.assert_awaited()
    assert "unresolved" in interaction.response.send_message.await_args.args[0]


async def test_migrate_store_rejects_invalid_candidate() -> None:
    from bot.app.recipes.registry import RecipeRegistryError

    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.required_keys = {"admin"}
    view_obj.candidates = {"admin": {1, 2}}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    with pytest.raises(RecipeRegistryError) as raised:
        await bot.recipe_registry.run(
            "ui.migrate.store",
            interaction=interaction,
            resource_key="admin",
            select_values=["99"],
        )
    assert isinstance(raised.value.__cause__, UserFacingError)
    assert "not a candidate" in str(raised.value.__cause__)


async def test_migrate_store_and_confirm_complete() -> None:
    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.required_keys = {"admin"}
    view_obj.candidates = {"admin": {11}}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    await bot.recipe_registry.run(
        "ui.migrate.store",
        interaction=interaction,
        resource_key="admin",
        select_values=["11"],
    )
    assert view_obj.resolutions["admin"] == 11
    await bot.recipe_registry.run("ui.migrate.confirm", interaction=interaction)
    assert view_obj.decision == {"ok": True}


async def test_migrate_cancel_and_timeout_decision() -> None:
    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.decision = {}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    await bot.recipe_registry.run("ui.migrate.cancel", interaction=interaction)
    assert view_obj.decision is None


def test_select_range_validation() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="max_values"):
        view("blacklist_select").fill(
            "blacklist",
            [
                SelectSpec(
                    tag="select",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="A", value="1"),),
                    handler=recipe_handler("ui.dismiss"),
                    max_values=2,
                )
            ],
        ).build(bot)


def test_no_legacy_button_id_alias() -> None:
    with pytest.raises(ValidationError):
        ViewTemplateSpec.model_validate(
            {
                "kind": "view",
                "id": "x",
                "components": [{"type": "button", "id": "old", "label": "A"}],
            }
        )
