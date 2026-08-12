"""Network domain recipes."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.contracts.widgets import OpenModal, recipe_handler
from bot.core.models.errors import NetworkValidationError
from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.widgets.guards import (
    interaction_actor,
    interaction_guild,
    interaction_view_registry,
    require_actor,
    require_hub_guild,
    require_manage_guild,
)


def _network_context(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction | None,
    guild: discord.Guild | None,
    view_registry: Any,
    moderator: discord.abc.User | None,
) -> tuple[discord.Guild, Any, discord.abc.User]:
    if interaction is not None:
        guild = interaction_guild(recipe_context.bot, interaction)
        moderator = interaction_actor(interaction)
        view_registry = interaction_view_registry(interaction)
    else:
        guild = require_hub_guild(recipe_context.bot, guild)
        if view_registry is None:
            raise UserFacingError(render_text("bot_not_ready"), code="bot_not_ready")
        moderator = require_actor(moderator)
    require_manage_guild(moderator)
    return guild, view_registry, moderator


@recipe("network.create")
async def create_network(
    recipe_context: RecipeContext,
    *,
    key: str,
    display_name: str,
    interaction: discord.Interaction | None = None,
    guild: discord.Guild | None = None,
    view_registry: Any = None,
    moderator: discord.abc.User | None = None,
) -> tuple[Any, int, int]:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles
    from bot.features.recipes.hub.clients.subscription import resync_subscriptions_for_network

    guild, view_registry, _actor = _network_context(
        recipe_context,
        interaction=interaction,
        guild=guild,
        view_registry=view_registry,
        moderator=moderator,
    )
    core = recipe_context.core
    existing = await core.store.networks.get_by_key(key)
    if existing is not None:
        raise NetworkValidationError(f"Network `{existing.key}` already exists.")
    network = await core.store.networks.create(
        guild_id=guild.id, key=key, display_name=display_name
    )
    await core.refresh_network_counts()
    relinked = await resync_subscriptions_for_network(
        guild,
        recipe_context.bot,
        core,
        network,
        access_role_name=recipe_context.bot.settings.network_access_role_name,
        view_registry=view_registry,
    )
    updated = await refresh_all_client_profiles(
        recipe_context.bot, core, guild, view_registry=view_registry
    )
    await refresh_network_admin_sticky_from_settings(
        core,
        guild,
        view_registry.register_network_admin_view(),
    )
    return network, updated, relinked


@recipe("network.delete")
async def delete_network(
    recipe_context: RecipeContext,
    *,
    key: str,
    interaction: discord.Interaction | None = None,
    guild: discord.Guild | None = None,
    view_registry: Any = None,
    moderator: discord.abc.User | None = None,
) -> Any:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles

    guild, view_registry, _actor = _network_context(
        recipe_context,
        interaction=interaction,
        guild=guild,
        view_registry=view_registry,
        moderator=moderator,
    )
    core = recipe_context.core
    network = await core.store.networks.get_by_key(key)
    if network is None:
        raise NetworkValidationError(f"Network `{key.strip().lower()}` was not found.")
    await core.store.networks.delete_with_relations(key)
    await core.refresh_projections()
    await refresh_all_client_profiles(
        recipe_context.bot, core, guild, view_registry=view_registry
    )
    await refresh_network_admin_sticky_from_settings(
        core,
        guild,
        view_registry.register_network_admin_view(),
    )
    return network


@recipe("network.create.open")
async def open_create_network(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> OpenModal:
    interaction_guild(recipe_context.bot, interaction)
    require_manage_guild(interaction_actor(interaction))
    return OpenModal(
        template_id="create_network",
        submit=recipe_handler("network.create"),
    )


@recipe("network.delete.open")
async def open_delete_network(
    recipe_context: RecipeContext,
    *,
    interaction: discord.Interaction,
) -> OpenModal:
    interaction_guild(recipe_context.bot, interaction)
    require_manage_guild(interaction_actor(interaction))
    return OpenModal(
        template_id="delete_network",
        submit=recipe_handler("network.delete"),
    )
