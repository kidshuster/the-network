"""Network domain recipes."""

from __future__ import annotations

from typing import Any

import discord

from bot.contracts.recipes import RecipeContext, recipe
from bot.core.models.errors import NetworkValidationError


@recipe("network.create")
async def create_network(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    key: str,
    display_name: str,
    view_registry: Any,
    moderator: discord.Member | None = None,
) -> tuple[Any, int, int]:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles
    from bot.features.recipes.hub.clients.subscription import resync_subscriptions_for_network
    from bot.features.widgets.guards import require_hub_guild, require_manage_guild

    require_hub_guild(recipe_context.bot, guild)
    if moderator is not None:
        require_manage_guild(moderator)
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
    guild: discord.Guild,
    key: str,
    view_registry: Any,
    moderator: discord.Member | None = None,
) -> Any:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles
    from bot.features.widgets.guards import require_hub_guild, require_manage_guild

    require_hub_guild(recipe_context.bot, guild)
    if moderator is not None:
        require_manage_guild(moderator)
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
