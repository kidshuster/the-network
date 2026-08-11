from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.app.context import BotContext
from bot.features.channels.stickies.admin import NETWORK_ADMIN_SETTINGS_KEY
from bot.features.channels.stickies.join import HOW_TO_JOIN_SETTINGS_KEY
from bot.features.channels.stickies.rules import RULES_STICKY_SETTINGS_KEY

logger = logging.getLogger(__name__)

_HUB_STICKY_SETTINGS_KEYS = (
    HOW_TO_JOIN_SETTINGS_KEY,
    NETWORK_ADMIN_SETTINGS_KEY,
    RULES_STICKY_SETTINGS_KEY,
)


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


async def reset_hub_layout_data(context: BotContext, guild_id: int) -> HubDataResetResult:
    """Clear hub/network DB state for ``guild_id`` while preserving client rows."""
    deleted = await context.store.maintenance.reset_hub_layout(
        guild_id,
        setting_keys=_HUB_STICKY_SETTINGS_KEYS,
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


async def reset_hub_data(context: BotContext, guild_id: int) -> HubDataResetResult:
    """Backwards-compatible alias for :func:`reset_hub_layout_data`."""
    return await reset_hub_layout_data(context, guild_id)
