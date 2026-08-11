from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.contracts.recipes import RecipeContext, recipe
from bot.features.recipes.hub.installs import hub_sticky_settings_keys

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HubDataResetResult:
    networks_deleted: int = 0
    clients_deleted: int = 0
    server_requests_deleted: int = 0
    relay_records_deleted: int = 0
    subscriptions_deleted: int = 0
    blacklists_deleted: int = 0
    profiles_deleted: int = 0

    def summary_note(self) -> str | None:
        parts: list[str] = []
        if self.networks_deleted:
            parts.append(f"{self.networks_deleted} network(s)")
        if self.subscriptions_deleted:
            parts.append(f"{self.subscriptions_deleted} subscription(s)")
        if self.server_requests_deleted:
            parts.append(f"{self.server_requests_deleted} join request(s)")
        if self.relay_records_deleted:
            parts.append(f"{self.relay_records_deleted} relay record(s)")
        if not parts:
            return None
        return f"Cleared hub layout data: {', '.join(parts)} (clients preserved)."


async def reset_hub_layout_data(context: Any, guild_id: int) -> HubDataResetResult:
    """Clear hub/network DB state for ``guild_id`` while preserving client rows."""
    deleted = await context.store.maintenance.reset_hub_layout(
        guild_id,
        setting_keys=hub_sticky_settings_keys(),
    )

    await context.refresh_projections()

    logger.info(
        "Hub layout data reset for guild",
        extra={
            "guild_id": guild_id,
            "networks_deleted": deleted.networks_deleted,
            "subscriptions_deleted": deleted.subscriptions_deleted,
        },
    )

    return HubDataResetResult(
        networks_deleted=deleted.networks_deleted,
        clients_deleted=deleted.clients_deleted,
        server_requests_deleted=deleted.server_requests_deleted,
        relay_records_deleted=deleted.relay_records_deleted,
        subscriptions_deleted=deleted.subscriptions_deleted,
        blacklists_deleted=deleted.blacklists_deleted,
        profiles_deleted=deleted.profiles_deleted,
    )


async def reset_hub_data(context: Any, guild_id: int) -> HubDataResetResult:
    """Backwards-compatible alias for :func:`reset_hub_layout_data`."""
    return await reset_hub_layout_data(context, guild_id)


@recipe("hub.reset_data")
async def reset_hub_data_recipe(
    recipe_context: RecipeContext,
    *,
    guild_id: int,
) -> HubDataResetResult:
    return await reset_hub_layout_data(recipe_context.core, guild_id)
