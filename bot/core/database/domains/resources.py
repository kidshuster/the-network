from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from bot.core.database.connection import Database
from bot.core.database.errors import StoreConflict


@dataclass(frozen=True)
class ManagedResource:
    guild_id: int
    resource_key: str
    discord_type: str
    discord_id: int
    owner_type: str | None = None
    owner_id: int | None = None


class ResourceStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _map(row: aiosqlite.Row) -> ManagedResource:
        return ManagedResource(
            guild_id=int(row["guild_id"]),
            resource_key=str(row["resource_key"]),
            owner_type=str(row["owner_type"]) if row["owner_type"] is not None else None,
            owner_id=int(row["owner_id"]) if row["owner_id"] is not None else None,
            discord_type=str(row["discord_type"]),
            discord_id=int(row["discord_id"]),
        )

    async def get(self, guild_id: int, resource_key: str) -> ManagedResource | None:
        row = await self._db.fetchone(
            "SELECT * FROM managed_resources WHERE guild_id = ? AND resource_key = ?",
            (guild_id, resource_key),
        )
        return self._map(row) if row is not None else None

    async def list_for_guild(self, guild_id: int) -> tuple[ManagedResource, ...]:
        rows = await self._db.fetchall(
            "SELECT * FROM managed_resources WHERE guild_id = ? ORDER BY resource_key",
            (guild_id,),
        )
        return tuple(self._map(row) for row in rows)

    async def upsert(self, resource: ManagedResource) -> ManagedResource:
        try:
            await self._db.execute(
                """
                INSERT INTO managed_resources (
                    guild_id, resource_key, owner_type, owner_id,
                    discord_type, discord_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, resource_key) DO UPDATE SET
                    owner_type = excluded.owner_type,
                    owner_id = excluded.owner_id,
                    discord_type = excluded.discord_type,
                    discord_id = excluded.discord_id,
                    updated_at = excluded.updated_at
                """,
                (
                    resource.guild_id,
                    resource.resource_key,
                    resource.owner_type,
                    resource.owner_id,
                    resource.discord_type,
                    resource.discord_id,
                    datetime.now(tz=UTC).isoformat(),
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise StoreConflict("Discord resource identity is already registered.") from exc
        return resource

    async def delete_owner(self, guild_id: int, owner_type: str, owner_id: int) -> int:
        return await self._db.execute(
            "DELETE FROM managed_resources WHERE guild_id = ? AND owner_type = ? AND owner_id = ?",
            (guild_id, owner_type, owner_id),
        )
