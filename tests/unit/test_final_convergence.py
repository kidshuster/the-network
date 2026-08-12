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
from bot.contracts.widgets import ButtonSpec, SelectOptionSpec, SelectSpec, recipe_handler
from bot.core.channels.migration import AmbiguousMatch
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


def _ambiguous(key: str, *ids: int) -> AmbiguousMatch:
    return AmbiguousMatch(
        resource_key=key,
        candidate_ids=tuple(ids),
        candidate_names=tuple(f"ch-{discord_id}" for discord_id in ids),
    )


def test_migration_rejects_more_than_four_ambiguities() -> None:
    from bot.app.widgets.migration import _require_reviewable_ambiguities
    from bot.core.channels.migration import MigrationPlan

    plan = MigrationPlan(
        ambiguous=tuple(_ambiguous(f"r{i}", i + 1) for i in range(5)),
    )
    with pytest.raises(UserFacingError, match="5.*ambiguous") as raised:
        _require_reviewable_ambiguities(plan)
    assert raised.value.code == "migration_too_many_ambiguous"


def test_migration_allows_zero_to_four_ambiguities() -> None:
    from bot.app.widgets.migration import _require_reviewable_ambiguities
    from bot.core.channels.migration import MigrationPlan

    _require_reviewable_ambiguities(MigrationPlan())
    _require_reviewable_ambiguities(
        MigrationPlan(ambiguous=(_ambiguous("admin", 1),))
    )
    _require_reviewable_ambiguities(
        MigrationPlan(ambiguous=tuple(_ambiguous(f"r{i}", i + 1) for i in range(4)))
    )


def test_migration_review_builds_all_four_ambiguities() -> None:
    """All plan ambiguities (≤4) become required_keys — none are sliced away."""
    from bot.app.widgets.migration import _MAX_AMBIGUOUS_SELECTS, _require_reviewable_ambiguities
    from bot.core.channels.migration import MigrationPlan

    plan = MigrationPlan(
        ambiguous=tuple(_ambiguous(f"r{i}", 10 + i) for i in range(_MAX_AMBIGUOUS_SELECTS)),
    )
    _require_reviewable_ambiguities(plan)
    bot = wire_widget_bot()
    selects = [
        SelectSpec(
            tag=item.resource_key,
            placeholder=item.resource_key,
            options=tuple(
                SelectOptionSpec(label=name, value=str(discord_id))
                for discord_id, name in zip(
                    item.candidate_ids, item.candidate_names, strict=True
                )
            ),
            handler=recipe_handler("ui.migrate.store", resource_key=item.resource_key),
        )
        for item in plan.ambiguous
    ]
    built = (
        bot.templates_view("migration_review")
        .fill("ambiguous", selects)
        .fill(
            "actions",
            (
                ButtonSpec(
                    tag="confirm",
                    label="Confirm",
                    handler=recipe_handler("ui.migrate.confirm"),
                ),
                ButtonSpec(
                    tag="cancel",
                    label="Cancel",
                    handler=recipe_handler("ui.migrate.cancel"),
                ),
            ),
        )
        .build(bot)
    )
    assert len([c for c in built.children if isinstance(c, discord.ui.Select)]) == 4


async def test_migrate_store_replaces_previous_selection() -> None:
    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.required_keys = {"admin"}
    view_obj.candidates = {"admin": {1, 2}}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    await bot.recipe_registry.run(
        "ui.migrate.store",
        interaction=interaction,
        resource_key="admin",
        select_values=["1"],
    )
    await bot.recipe_registry.run(
        "ui.migrate.store",
        interaction=interaction,
        resource_key="admin",
        select_values=["2"],
    )
    assert view_obj.resolutions["admin"] == 2


async def test_migrate_store_rejects_unknown_resource_key() -> None:
    from bot.app.recipes.registry import RecipeRegistryError

    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    view_obj.required_keys = {"admin"}
    view_obj.candidates = {"admin": {1}}
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    with pytest.raises(RecipeRegistryError) as raised:
        await bot.recipe_registry.run(
            "ui.migrate.store",
            interaction=interaction,
            resource_key="rules",
            select_values=["1"],
        )
    assert isinstance(raised.value.__cause__, UserFacingError)


def test_resolved_layout_valid_static_and_mixed() -> None:
    bot = wire_widget_bot()
    static = (
        view("join_network")
        .bind("join_button", recipe_handler("request.join.open"))
        .build(bot)
    )
    assert len(static.children) == 1
    mixed = (
        view("blacklist_select")
        .fill(
            "blacklist",
            [
                SelectSpec(
                    tag="select",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="A", value="1"),),
                    handler=recipe_handler("ui.dismiss"),
                )
            ],
        )
        .build(bot)
    )
    assert len(mixed.children) == 1


def test_resolved_layout_rejects_six_buttons_one_row() -> None:
    bot = wire_widget_bot()
    buttons = [
        ButtonSpec(
            tag=f"b{i}",
            label=str(i),
            handler=recipe_handler("ui.dismiss"),
            row=0,
        )
        for i in range(6)
    ]
    with pytest.raises(TemplateRenderError, match="row 0 exceeds") as raised:
        view("blacklist_select").fill("blacklist", buttons).build(bot)
    assert raised.value.template_id == "blacklist_select"
    assert raised.value.element_id == "b5"


def test_resolved_layout_rejects_select_sharing_row_with_button() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="share row") as raised:
        view("blacklist_select").fill(
            "blacklist",
            [
                ButtonSpec(
                    tag="b",
                    label="B",
                    handler=recipe_handler("ui.dismiss"),
                    row=1,
                ),
                SelectSpec(
                    tag="s",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="A", value="1"),),
                    handler=recipe_handler("ui.dismiss"),
                    row=1,
                ),
            ],
        ).build(bot)
    assert raised.value.template_id == "blacklist_select"
    assert raised.value.element_id == "s"


def test_resolved_layout_rejects_two_selects_same_row() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="share row"):
        view("blacklist_select").fill(
            "blacklist",
            [
                SelectSpec(
                    tag="s1",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="A", value="1"),),
                    handler=recipe_handler("ui.dismiss"),
                    row=2,
                ),
                SelectSpec(
                    tag="s2",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="B", value="2"),),
                    handler=recipe_handler("ui.dismiss"),
                    row=2,
                ),
            ],
        ).build(bot)


def test_resolved_layout_rejects_invalid_dynamic_row() -> None:
    bot = wire_widget_bot()
    with pytest.raises(TemplateRenderError, match="outside Discord range") as raised:
        view("blacklist_select").fill(
            "blacklist",
            [
                ButtonSpec(
                    tag="b",
                    label="B",
                    handler=recipe_handler("ui.dismiss"),
                    row=5,
                )
            ],
        ).build(bot)
    assert raised.value.element_id == "b"


def test_resolved_layout_rejects_too_many_components() -> None:
    bot = wire_widget_bot()
    buttons = [
        ButtonSpec(tag=f"b{i}", label=str(i % 10), handler=recipe_handler("ui.dismiss"))
        for i in range(26)
    ]
    with pytest.raises(TemplateRenderError, match="component limit") as raised:
        view("blacklist_select").fill("blacklist", buttons).build(bot)
    assert raised.value.template_id == "blacklist_select"
