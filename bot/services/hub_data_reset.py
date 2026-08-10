from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.context import BotContext
from bot.db.connection import Database
from bot.services.join_requests_sticky import HOW_TO_JOIN_SETTINGS_KEY
from bot.services.network_admin_sticky import NETWORK_ADMIN_SETTINGS_KEY
from bot.services.rules_sticky import RULES_STICKY_SETTINGS_KEY

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


def _as_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(str(value))


async def _table_exists(db: Database, name: str) -> bool:
    row = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    )
    return row is not None


async def reset_hub_layout_data(context: BotContext, guild_id: int) -> HubDataResetResult:
    """Clear hub/network DB state for ``guild_id`` while preserving client rows."""
    db = context.db

    blacklists_deleted = _as_int(
        await db.fetchval(
            """
            SELECT COUNT(*) FROM client_blacklists WHERE subscription_id IN (
                SELECT cs.id FROM client_subscriptions cs
                WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                   OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            )
            """,
            (guild_id, guild_id),
        )
    )
    subscriptions_deleted = _as_int(
        await db.fetchval(
            """
            SELECT COUNT(*) FROM client_subscriptions
            WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
               OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            """,
            (guild_id, guild_id),
        )
    )
    relay_records_deleted = _as_int(
        await db.fetchval(
            """
            SELECT COUNT(*) FROM relay_records
            WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
               OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            """,
            (guild_id, guild_id),
        )
    )
    server_requests_deleted = _as_int(
        await db.fetchval(
            "SELECT COUNT(*) FROM server_requests WHERE guild_id = ?",
            (guild_id,),
        )
    )
    networks_deleted = _as_int(
        await db.fetchval(
            "SELECT COUNT(*) FROM networks WHERE guild_id = ?",
            (guild_id,),
        )
    )
    profiles_deleted = 0
    if await _table_exists(db, "profiles"):
        profiles_deleted = _as_int(
            await db.fetchval(
                "SELECT COUNT(*) FROM profiles WHERE guild_id = ?",
                (guild_id,),
            )
        )

    conn = db.connection
    await conn.execute("BEGIN")
    try:
        await conn.execute(
            """
            DELETE FROM client_blacklists WHERE subscription_id IN (
                SELECT cs.id FROM client_subscriptions cs
                WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                   OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            )
            """,
            (guild_id, guild_id),
        )
        await conn.execute(
            """
            DELETE FROM client_subscriptions
            WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
               OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            """,
            (guild_id, guild_id),
        )
        await conn.execute(
            """
            DELETE FROM relay_records
            WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
               OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
            """,
            (guild_id, guild_id),
        )
        if profiles_deleted:
            await conn.execute("DELETE FROM profiles WHERE guild_id = ?", (guild_id,))
        await conn.execute(
            "DELETE FROM server_requests WHERE guild_id = ?",
            (guild_id,),
        )
        await conn.execute(
            "DELETE FROM networks WHERE guild_id = ?",
            (guild_id,),
        )
        for key in _HUB_STICKY_SETTINGS_KEYS:
            await conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise

    await context.routing_service.load_cache()
    await context.client_cache.load_cache()
    await context.refresh_network_counts()
    await context.refresh_client_counts()

    logger.info(
        "Hub layout data reset for guild",
        extra={
            "guild_id": guild_id,
            "networks_deleted": networks_deleted,
            "subscriptions_deleted": subscriptions_deleted,
        },
    )

    return HubDataResetResult(
        networks_deleted=networks_deleted,
        clients_deleted=0,
        server_requests_deleted=server_requests_deleted,
        relay_records_deleted=relay_records_deleted,
        subscriptions_deleted=subscriptions_deleted,
        blacklists_deleted=blacklists_deleted,
        profiles_deleted=profiles_deleted,
    )


async def reset_hub_data(context: BotContext, guild_id: int) -> HubDataResetResult:
    """Backwards-compatible alias for :func:`reset_hub_layout_data`."""
    return await reset_hub_layout_data(context, guild_id)
