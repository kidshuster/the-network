from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from widget_helpers import wire_widget_bot

from bot.app.recipes.registry import RecipeRegistry, RecipeRegistryError, recipe
from bot.app.recipes.runtime import RecipeContext
from bot.app.widgets.custom_id import decode, encode
from bot.app.widgets.drafts import view
from bot.app.widgets.errors import TemplateRenderError
from bot.contracts.widgets import ButtonSpec, SelectOptionSpec, SelectSpec, recipe_handler
from bot.features.widgets.guards import require_actor


def test_disabled_static_button_requires_binding() -> None:
    bot = wire_widget_bot()
    # join_network has an enabled button; simulate disabled via dynamic fill path below.
    draft = view("blacklist_select").fill(
        "blacklist",
        [
            ButtonSpec(
                tag="x",
                label="X",
                disabled=True,
                handler=recipe_handler("ui.dismiss"),
            )
        ],
    )
    built = draft.build(bot)
    assert built.children[0].disabled is True
    assert built.children[0].custom_id.startswith("tn1:ui.dismiss")


def test_disabled_dynamic_without_handler_rejected() -> None:
    bot = wire_widget_bot()
    draft = view("blacklist_select").fill(
        "blacklist",
        [ButtonSpec(tag="x", label="X", disabled=True, handler=None)],
    )
    with pytest.raises(TemplateRenderError, match="missing handler"):
        draft.build(bot)


async def test_registry_rejects_unexpected_inputs() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.strict")
    async def operation(context: RecipeContext, *, value: int) -> int:
        del context
        return value

    registry.register(operation)
    with pytest.raises(RecipeRegistryError, match="Unexpected inputs"):
        await registry.run("test.strict", value=1, extra=True)


async def test_registry_rejects_missing_inputs() -> None:
    registry = RecipeRegistry(SimpleNamespace())

    @recipe("test.required")
    async def operation(context: RecipeContext, *, value: int) -> int:
        del context
        return value

    registry.register(operation)
    with pytest.raises(RecipeRegistryError, match="Invalid inputs"):
        await registry.run("test.required")


def test_typed_custom_id_round_trips() -> None:
    handler = recipe_handler(
        "demo.recipe",
        flag=True,
        off=False,
        count=0,
        name="alpha",
        empty=None,
    )
    assert decode(encode(handler)) == handler
    assert isinstance(decode(encode(handler)).arguments["flag"], bool)
    assert decode(encode(handler)).arguments["count"] == 0
    assert decode(encode(handler)).arguments["empty"] is None


def test_custom_id_rejects_oversized() -> None:
    with pytest.raises(TemplateRenderError, match="exceeds"):
        encode(recipe_handler("x", payload="y" * 120))


def test_select_label_limit_rejected() -> None:
    bot = wire_widget_bot()
    draft = view("blacklist_select").fill(
        "blacklist",
        [
            SelectSpec(
                tag="select",
                placeholder="Pick",
                options=(
                    SelectOptionSpec(label="L" * 101, value="1"),
                ),
                handler=recipe_handler("ui.dismiss"),
            )
        ],
    )
    with pytest.raises(TemplateRenderError, match="exceeds Discord limit 100"):
        draft.build(bot)


def test_select_label_at_limit_accepted() -> None:
    bot = wire_widget_bot()
    built = (
        view("blacklist_select")
        .fill(
            "blacklist",
            [
                SelectSpec(
                    tag="select",
                    placeholder="Pick",
                    options=(SelectOptionSpec(label="L" * 100, value="1"),),
                    handler=recipe_handler("ui.dismiss"),
                )
            ],
        )
        .build(bot)
    )
    assert built.children[0].options[0].label == "L" * 100


async def test_submitted_persistent_collision_rejected() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    with pytest.raises(TemplateRenderError, match="collide"):
        # handle_handler catches and reports — call payload path via private helper
        from bot.app.widgets.dispatch import _interaction_payload

        _interaction_payload(
            interaction,
            recipe_handler("blacklist.replace", subscription_id=1),
            {"subscription_id": ["2"]},
        )


async def test_migration_store_updates_resolutions_via_recipe() -> None:
    from bot.app.widgets.dispatch import RenderedView

    bot = wire_widget_bot()
    view_obj = RenderedView(bot, timeout=None, template_id="migration_review")
    interaction = MagicMock(spec=discord.Interaction)
    interaction.view = view_obj
    interaction.guild = None
    interaction.user = MagicMock()
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.defer = AsyncMock()
    await bot.recipe_registry.run(
        "ui.migrate.store",
        interaction=interaction,
        resource_key="admin",
        select_values=["99"],
    )
    assert view_obj.resolutions["admin"] == 99


def test_missing_actor_rejected() -> None:
    from bot.errors import UserFacingError

    with pytest.raises(UserFacingError, match="member"):
        require_actor(None)


async def test_network_create_requires_authorized_actor() -> None:
    from bot.app.features import build_recipe_registry
    from bot.app.recipes.registry import RecipeRegistryError

    bot = SimpleNamespace(
        bot_context=SimpleNamespace(store=SimpleNamespace(networks=MagicMock())),
        settings=SimpleNamespace(guild_id=100),
    )
    registry = build_recipe_registry(bot)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    unauthorized = MagicMock(spec=discord.Member)
    unauthorized.guild_permissions = SimpleNamespace(manage_guild=False)
    with pytest.raises(RecipeRegistryError):
        await registry.run(
            "network.create",
            guild=guild,
            key="a",
            display_name="A",
            view_registry=MagicMock(),
            moderator=unauthorized,
        )


async def test_presenter_failure_does_not_send_done() -> None:
    from bot.app.widgets.dispatch import _present

    bot = wire_widget_bot()

    async def _boom(_name: str, **_kwargs: object) -> None:
        raise RuntimeError("presenter exploded")

    bot.recipe_registry.has = MagicMock(return_value=True)
    bot.recipe_registry.run = _boom  # type: ignore[method-assign]
    response = MagicMock()
    response.send = AsyncMock()
    response.sent = False
    with pytest.raises(RuntimeError, match="presenter exploded"):
        await _present(bot, MagicMock(), response, "network.create", object())
    response.send.assert_not_awaited()
