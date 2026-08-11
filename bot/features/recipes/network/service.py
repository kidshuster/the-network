from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import discord

from bot.app.bot import NetworkRelayBot
from bot.app.context import BotContext
from bot.app.features import build_recipe_registry
from bot.app.recipes import RecipeRegistry, RecipeRegistryError
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
