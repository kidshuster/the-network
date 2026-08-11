from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from bot.app.recipes import RecipeRegistryError
from bot.core.models.errors import NetworkValidationError
from bot.core.models.network import Network
from bot.features.channels.stickies.admin import build_network_admin_embed
from bot.features.recipes.hub.network.service import create_network, delete_network


def _network() -> Network:
    return Network(
        id=1,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )


async def test_network_service_maps_recipe_outputs_to_public_result() -> None:
    network = _network()
    registry = MagicMock()
    registry.run = AsyncMock(return_value=(network, 2, 3))
    bot = MagicMock()
    bot.recipe_registry = registry
    context = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    view_registry = MagicMock()

    result = await create_network(
        context,
        bot,
        guild,
        key="stingers",
        display_name="Stingers",
        view_registry=view_registry,
    )

    assert result.success
    assert result.network is network
    assert result.updated_profile_count == 2
    assert result.relinked_subscription_count == 3
    registry.run.assert_awaited_once_with(
        "network.create",
        guild=guild,
        key="stingers",
        display_name="Stingers",
        view_registry=view_registry,
    )


async def test_network_service_preserves_validation_message() -> None:
    validation = NetworkValidationError("Network `stingers` already exists.")
    wrapped = RecipeRegistryError("network.create failed")
    wrapped.__cause__ = validation
    registry = MagicMock()
    registry.run = AsyncMock(side_effect=wrapped)
    bot = MagicMock()
    bot.recipe_registry = registry

    result = await create_network(
        MagicMock(),
        bot,
        MagicMock(spec=discord.Guild),
        key="stingers",
        display_name="Stingers",
        view_registry=MagicMock(),
    )

    assert not result.success
    assert result.error == "Network `stingers` already exists."


async def test_delete_network_maps_recipe_output() -> None:
    network = _network()
    registry = MagicMock()
    registry.run = AsyncMock(return_value=network)
    bot = MagicMock()
    bot.recipe_registry = registry

    result = await delete_network(
        MagicMock(),
        bot,
        MagicMock(spec=discord.Guild),
        key="stingers",
        view_registry=MagicMock(),
    )

    assert result.success
    assert result.network_key == "stingers"


async def test_network_admin_embed_lists_networks() -> None:
    context = MagicMock()
    context.store.networks.list_all = AsyncMock(return_value=[_network()])
    context.store.clients.list_subscriptions_by_network = AsyncMock(return_value=[])

    embed = await build_network_admin_embed(context)

    assert embed.title == "Network Administration"
    assert len(embed.fields) == 1
    assert "stingers" in embed.fields[0].name
