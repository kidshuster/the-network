from __future__ import annotations

from dataclasses import dataclass

from bot.core.database.connection import Database


@dataclass(frozen=True)
class HubDataResetRecord:
    networks_deleted: int = 0
    clients_deleted: int = 0
    server_requests_deleted: int = 0
    relay_records_deleted: int = 0
    subscriptions_deleted: int = 0
    blacklists_deleted: int = 0
    profiles_deleted: int = 0


class MaintenanceStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def reset_hub_layout(
        self,
        guild_id: int,
        *,
        setting_keys: tuple[str, ...] = (),
    ) -> HubDataResetRecord:
        """Atomically clear one guild's hub data while preserving client rows."""
        async with self._db.transaction() as connection:
            counts = await self._db.fetchone(
                """
                SELECT
                    (SELECT COUNT(*) FROM networks WHERE guild_id = ?) AS networks,
                    (SELECT COUNT(*) FROM server_requests WHERE guild_id = ?) AS requests,
                    (SELECT COUNT(*) FROM client_subscriptions cs
                     WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                        OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                    ) AS subscriptions,
                    (SELECT COUNT(*) FROM client_blacklists cb
                     WHERE cb.subscription_id IN (
                         SELECT cs.id FROM client_subscriptions cs
                         WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                            OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                     )) AS blacklists,
                    (SELECT COUNT(*) FROM relay_records rr
                     WHERE rr.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                        OR rr.client_id IN (SELECT id FROM clients WHERE guild_id = ?)) AS relays,
                    (SELECT COUNT(*) FROM profiles WHERE guild_id = ?) AS profiles
                """,
                (guild_id,) * 9,
            )
            if counts is None:
                raise RuntimeError("Could not count hub reset rows")
            await connection.execute(
                """
                DELETE FROM managed_resources
                WHERE guild_id = ? AND owner_type = 'subscription' AND owner_id IN (
                    SELECT cs.id FROM client_subscriptions cs
                    WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                       OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                )
                """,
                (guild_id, guild_id, guild_id),
            )
            await connection.execute(
                """
                DELETE FROM client_blacklists WHERE subscription_id IN (
                    SELECT cs.id FROM client_subscriptions cs
                    WHERE cs.network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                       OR cs.client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                )
                """,
                (guild_id, guild_id),
            )
            await connection.execute(
                """
                DELETE FROM client_subscriptions
                WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                   OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                """,
                (guild_id, guild_id),
            )
            await connection.execute(
                """
                DELETE FROM relay_records
                WHERE network_id IN (SELECT id FROM networks WHERE guild_id = ?)
                   OR client_id IN (SELECT id FROM clients WHERE guild_id = ?)
                """,
                (guild_id, guild_id),
            )
            await connection.execute("DELETE FROM profiles WHERE guild_id = ?", (guild_id,))
            await connection.execute("DELETE FROM server_requests WHERE guild_id = ?", (guild_id,))
            await connection.execute("DELETE FROM networks WHERE guild_id = ?", (guild_id,))
            for key in setting_keys:
                await connection.execute("DELETE FROM settings WHERE key = ?", (key,))
        return HubDataResetRecord(
            networks_deleted=int(counts["networks"]),
            server_requests_deleted=int(counts["requests"]),
            subscriptions_deleted=int(counts["subscriptions"]),
            blacklists_deleted=int(counts["blacklists"]),
            relay_records_deleted=int(counts["relays"]),
            profiles_deleted=int(counts["profiles"]),
        )
