from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import discord

from bot.app.bot import NetworkRelayBot
from bot.app.context import BotContext
from bot.app.features import build_recipe_registry
from bot.app.recipes import RecipeRegistry, RecipeRegistryError
from bot.app.recipes.registry import recipe
from bot.app.recipes.runtime import RecipeContext
from bot.core.models.errors import NetworkValidationError
from bot.core.models.network import Network
from bot.core.views import ViewRegistry


def _registry_for(bot: NetworkRelayBot, context: BotContext) -> RecipeRegistry:
    registry = getattr(bot, "recipe_registry", None)
    if callable(getattr(registry, "run", None)):
        return cast(RecipeRegistry, registry)
    bot.bot_context = context
    return build_recipe_registry(bot)


@dataclass(frozen=True)
class CreateNetworkResult:
    success: bool
    network: Network | None = None
    updated_profile_count: int = 0
    relinked_subscription_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class DeleteNetworkResult:
    success: bool
    network_key: str | None = None
    error: str | None = None


@recipe("network.create")
async def create_network_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    key: str,
    display_name: str,
    view_registry: Any,
) -> tuple[Any, int, int]:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles
    from bot.features.recipes.hub.clients.subscription import resync_subscriptions_for_network

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
async def delete_network_recipe(
    recipe_context: RecipeContext,
    *,
    guild: discord.Guild,
    key: str,
    view_registry: Any,
) -> Any:
    from bot.features.channels.stickies.admin import refresh_network_admin_sticky_from_settings
    from bot.features.recipes.hub.clients.profile_sync import refresh_all_client_profiles

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


async def create_network(
    context: BotContext,
    bot: NetworkRelayBot,
    guild: discord.Guild,
    *,
    key: str,
    display_name: str,
    view_registry: ViewRegistry,
) -> CreateNetworkResult:
    try:
        network, updated_count, relinked_count = await _registry_for(bot, context).run(
            "network.create",
            guild=guild,
            key=key,
            display_name=display_name,
            view_registry=view_registry,
        )
        return CreateNetworkResult(
            success=True,
            network=network,
            updated_profile_count=updated_count,
            relinked_subscription_count=relinked_count,
        )
    except RecipeRegistryError as exc:
        cause = exc.__cause__
        if isinstance(cause, NetworkValidationError):
            return CreateNetworkResult(success=False, error=str(cause))
        return CreateNetworkResult(
            success=False,
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
        )
    except NetworkValidationError as exc:
        return CreateNetworkResult(success=False, error=str(exc))
    except Exception as exc:
        return CreateNetworkResult(
            success=False,
            error=f"Unexpected error: {type(exc).__name__}: {exc}",
        )


async def delete_network(
    context: BotContext,
    bot: NetworkRelayBot,
    guild: discord.Guild,
    *,
    key: str,
    view_registry: ViewRegistry,
) -> DeleteNetworkResult:
    try:
        network = await _registry_for(bot, context).run(
            "network.delete",
            guild=guild,
            key=key,
            view_registry=view_registry,
        )
        return DeleteNetworkResult(success=True, network_key=network.key)
    except RecipeRegistryError as exc:
        cause = exc.__cause__
        if isinstance(cause, NetworkValidationError):
            return DeleteNetworkResult(success=False, error=str(cause))
        return DeleteNetworkResult(success=False, error="Network delete failed. Check bot logs.")
    except NetworkValidationError as exc:
        return DeleteNetworkResult(success=False, error=str(exc))
    except Exception:
        return DeleteNetworkResult(success=False, error="Network delete failed. Check bot logs.")
