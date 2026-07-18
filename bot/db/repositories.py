from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import aiosqlite

from bot.constants import RelayStatus
from bot.db.connection import Database
from bot.db.models import NetworkRow, ProfileRow, RelayRecordRow
from bot.domain.errors import NetworkValidationError, ProfileValidationError, RelayError
from bot.domain.network import Network
from bot.domain.profile import ServerProfile
from bot.domain.relay_record import RelayRecord

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class NetworkRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def validate_key(key: str) -> str:
        normalized = key.strip().lower()
        if not _KEY_PATTERN.match(normalized):
            raise NetworkValidationError(
                "Network key must start with a letter and use only lowercase letters, "
                "numbers, hyphens, or underscores (max 32 characters)."
            )
        return normalized

    async def create(
        self,
        *,
        guild_id: int,
        key: str,
        display_name: str,
        feed_category_id: int,
        output_channel_id: int,
        concat_channel_id: int | None,
        profile_forum_channel_id: int | None = None,
    ) -> Network:
        normalized_key = self.validate_key(key)
        name = display_name.strip()
        if not name:
            raise NetworkValidationError("Display name cannot be empty.")

        now = datetime.now(tz=UTC).isoformat()
        try:
            cursor = await self._db.connection.execute(
                """
                INSERT INTO networks (
                    guild_id, key, display_name, feed_category_id,
                    output_channel_id, concat_channel_id, profile_forum_channel_id,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    guild_id,
                    normalized_key,
                    name,
                    feed_category_id,
                    output_channel_id,
                    concat_channel_id,
                    profile_forum_channel_id,
                    now,
                    now,
                ),
            )
            await self._db.connection.commit()
        except aiosqlite.IntegrityError as exc:
            raise NetworkValidationError(
                "A network with that key, feed category, or output channel already exists."
            ) from exc
        network_id = cursor.lastrowid
        if network_id is None:
            raise RuntimeError("Failed to create network row")
        row = await self._db.fetchone("SELECT * FROM networks WHERE id = ?", (network_id,))
        if row is None:
            raise RuntimeError("Created network row not found")
        return NetworkRow.from_row(row)

    async def get_by_key(self, key: str) -> Network | None:
        normalized_key = self.validate_key(key)
        row = await self._db.fetchone(
            "SELECT * FROM networks WHERE key = ?",
            (normalized_key,),
        )
        return NetworkRow.from_row(row) if row else None

    async def get_by_id(self, network_id: int) -> Network | None:
        row = await self._db.fetchone(
            "SELECT * FROM networks WHERE id = ?",
            (network_id,),
        )
        return NetworkRow.from_row(row) if row else None

    async def get_by_feed_category(self, category_id: int) -> Network | None:
        row = await self._db.fetchone(
            "SELECT * FROM networks WHERE feed_category_id = ?",
            (category_id,),
        )
        return NetworkRow.from_row(row) if row else None

    async def list_all(self) -> list[Network]:
        cursor = await self._db.connection.execute("SELECT * FROM networks ORDER BY key ASC")
        rows = await cursor.fetchall()
        await cursor.close()
        return [NetworkRow.from_row(row) for row in rows]

    async def set_enabled(self, key: str, enabled: bool) -> Network:
        normalized_key = self.validate_key(key)
        existing = await self.get_by_key(normalized_key)
        if existing is None:
            raise NetworkValidationError(f"Network '{normalized_key}' was not found.")

        now = datetime.now(tz=UTC).isoformat()
        await self._db.execute(
            "UPDATE networks SET enabled = ?, updated_at = ? WHERE key = ?",
            (1 if enabled else 0, now, normalized_key),
        )
        updated = await self.get_by_key(normalized_key)
        if updated is None:
            raise RuntimeError("Network disappeared after update")
        return updated

    async def delete(self, key: str) -> Network:
        normalized_key = self.validate_key(key)
        existing = await self.get_by_key(normalized_key)
        if existing is None:
            raise NetworkValidationError(f"Network '{normalized_key}' was not found.")

        await self._db.execute("DELETE FROM networks WHERE key = ?", (normalized_key,))
        deleted = await self.get_by_key(normalized_key)
        if deleted is not None:
            raise RuntimeError("Network still present after delete")
        return existing


class ProfileRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_by_thread_id(self, thread_id: int) -> ServerProfile | None:
        row = await self._db.fetchone(
            "SELECT * FROM profiles WHERE profile_thread_id = ?",
            (thread_id,),
        )
        return ProfileRow.from_row(row) if row else None

    async def get_by_source_channel(self, source_channel_id: int) -> ServerProfile | None:
        row = await self._db.fetchone(
            "SELECT * FROM profiles WHERE source_channel_id = ?",
            (source_channel_id,),
        )
        return ProfileRow.from_row(row) if row else None

    async def list_all(self) -> list[ServerProfile]:
        cursor = await self._db.connection.execute(
            "SELECT * FROM profiles ORDER BY server_name ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [ProfileRow.from_row(row) for row in rows]

    async def list_by_network_id(self, network_id: int) -> list[ServerProfile]:
        cursor = await self._db.connection.execute(
            "SELECT * FROM profiles WHERE network_id = ? ORDER BY server_name ASC",
            (network_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [ProfileRow.from_row(row) for row in rows]

    async def get_by_network_and_server_name(
        self,
        network_id: int,
        server_name: str,
    ) -> ServerProfile | None:
        name = server_name.strip()
        if not name:
            return None
        row = await self._db.fetchone(
            """
            SELECT * FROM profiles
            WHERE network_id = ? AND server_name = ? COLLATE NOCASE
            """,
            (network_id, name),
        )
        return ProfileRow.from_row(row) if row else None

    async def set_enabled_by_network_and_server_name(
        self,
        network_id: int,
        server_name: str,
        enabled: bool,
    ) -> ServerProfile:
        profile = await self.get_by_network_and_server_name(network_id, server_name)
        if profile is None:
            raise ProfileValidationError(
                f"No server {server_name!r} found on this network."
            )
        return await self.set_enabled_by_thread(profile.profile_thread_id, enabled)

    async def upsert(
        self,
        *,
        guild_id: int,
        profile_thread_id: int,
        profile_starter_message_id: int,
        source_channel_id: int,
        network_id: int,
        server_name: str,
        display_name: str,
        enabled: bool,
        partner_role_id: int | None = None,
        profile_forum_channel_id: int | None = None,
    ) -> ServerProfile:
        existing = await self.get_by_thread_id(profile_thread_id)
        other = await self.get_by_source_channel(source_channel_id)
        if other is not None and other.profile_thread_id != profile_thread_id:
            raise ProfileValidationError(
                f"Source channel <#{source_channel_id}> is already used by profile "
                f"'{other.server_name}' (thread {other.profile_thread_id})."
            )

        now = datetime.now(tz=UTC).isoformat()
        if existing is None:
            try:
                cursor = await self._db.connection.execute(
                    """
                    INSERT INTO profiles (
                        guild_id, profile_thread_id, profile_starter_message_id,
                        source_channel_id, network_id, server_name, display_name,
                        enabled, partner_role_id, profile_forum_channel_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        profile_thread_id,
                        profile_starter_message_id,
                        source_channel_id,
                        network_id,
                        server_name,
                        display_name,
                        1 if enabled else 0,
                        partner_role_id,
                        profile_forum_channel_id,
                        now,
                        now,
                    ),
                )
                await self._db.connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise ProfileValidationError(
                    "Profile thread or source channel is already registered."
                ) from exc
            profile_id = cursor.lastrowid
            if profile_id is None:
                raise RuntimeError("Failed to create profile row")
            row = await self._db.fetchone("SELECT * FROM profiles WHERE id = ?", (profile_id,))
        else:
            await self._db.execute(
                """
                UPDATE profiles SET
                    profile_starter_message_id = ?,
                    source_channel_id = ?,
                    network_id = ?,
                    server_name = ?,
                    display_name = ?,
                    enabled = ?,
                    partner_role_id = COALESCE(?, partner_role_id),
                    profile_forum_channel_id = COALESCE(?, profile_forum_channel_id),
                    updated_at = ?
                WHERE profile_thread_id = ?
                """,
                (
                    profile_starter_message_id,
                    source_channel_id,
                    network_id,
                    server_name,
                    display_name,
                    1 if enabled else 0,
                    partner_role_id,
                    profile_forum_channel_id,
                    now,
                    profile_thread_id,
                ),
            )
            row = await self._db.fetchone(
                "SELECT * FROM profiles WHERE profile_thread_id = ?",
                (profile_thread_id,),
            )

        if row is None:
            raise RuntimeError("Profile row not found after upsert")
        return ProfileRow.from_row(row)

    async def set_enabled_by_thread(self, thread_id: int, enabled: bool) -> ServerProfile:
        existing = await self.get_by_thread_id(thread_id)
        if existing is None:
            raise ProfileValidationError(f"Profile thread {thread_id} was not found.")

        now = datetime.now(tz=UTC).isoformat()
        await self._db.execute(
            "UPDATE profiles SET enabled = ?, updated_at = ? WHERE profile_thread_id = ?",
            (1 if enabled else 0, now, thread_id),
        )
        updated = await self.get_by_thread_id(thread_id)
        if updated is None:
            raise RuntimeError("Profile disappeared after update")
        return updated

    async def update_emoji_fields(
        self,
        thread_id: int,
        *,
        emoji_id: int | None,
        emoji_name: str | None,
        image_hash: str | None,
        degraded_reason: str | None,
    ) -> ServerProfile:
        existing = await self.get_by_thread_id(thread_id)
        if existing is None:
            raise ProfileValidationError(f"Profile thread {thread_id} was not found.")

        now = datetime.now(tz=UTC).isoformat()
        await self._db.execute(
            """
            UPDATE profiles SET
                emoji_id = ?,
                emoji_name = ?,
                image_hash = ?,
                degraded_reason = ?,
                updated_at = ?
            WHERE profile_thread_id = ?
            """,
            (emoji_id, emoji_name, image_hash, degraded_reason, now, thread_id),
        )
        updated = await self.get_by_thread_id(thread_id)
        if updated is None:
            raise RuntimeError("Profile disappeared after emoji update")
        return updated

    async def delete_by_thread_id(self, thread_id: int) -> ServerProfile | None:
        existing = await self.get_by_thread_id(thread_id)
        if existing is None:
            return None
        await self._db.execute(
            "DELETE FROM profiles WHERE profile_thread_id = ?",
            (thread_id,),
        )
        return existing

    async def list_by_profile_forum_channel(self, forum_channel_id: int) -> list[ServerProfile]:
        cursor = await self._db.connection.execute(
            "SELECT * FROM profiles WHERE profile_forum_channel_id = ?",
            (forum_channel_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [ProfileRow.from_row(row) for row in rows]


class RelayRecordRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def exists(self, source_message_id: int) -> bool:
        row = await self._db.fetchone(
            "SELECT 1 FROM relay_records WHERE source_message_id = ?",
            (source_message_id,),
        )
        return row is not None

    async def get_by_source_message(self, source_message_id: int) -> RelayRecord | None:
        row = await self._db.fetchone(
            "SELECT * FROM relay_records WHERE source_message_id = ?",
            (source_message_id,),
        )
        return RelayRecordRow.from_row(row) if row else None

    async def create_pending(
        self,
        *,
        source_message_id: int,
        source_channel_id: int,
        source_webhook_id: int | None,
        profile_id: int,
        network_id: int,
        destination_channel_id: int,
    ) -> RelayRecord:
        now = datetime.now(tz=UTC).isoformat()
        try:
            cursor = await self._db.connection.execute(
                """
                INSERT INTO relay_records (
                    source_message_id, source_channel_id, source_webhook_id,
                    profile_id, network_id, destination_channel_id,
                    destination_message_ids, status, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_message_id,
                    source_channel_id,
                    source_webhook_id,
                    profile_id,
                    network_id,
                    destination_channel_id,
                    "[]",
                    RelayStatus.PENDING,
                    None,
                    now,
                    now,
                ),
            )
            await self._db.connection.commit()
        except aiosqlite.IntegrityError as exc:
            raise RelayError(
                f"Relay record already exists for message {source_message_id}."
            ) from exc
        record_id = cursor.lastrowid
        if record_id is None:
            raise RuntimeError("Failed to create relay record")
        row = await self._db.fetchone("SELECT * FROM relay_records WHERE id = ?", (record_id,))
        if row is None:
            raise RuntimeError("Created relay record not found")
        return RelayRecordRow.from_row(row)

    async def update_status(
        self,
        record_id: int,
        *,
        status: RelayStatus,
        destination_message_ids: tuple[int, ...] | None = None,
        error_message: str | None = None,
    ) -> RelayRecord:
        now = datetime.now(tz=UTC).isoformat()
        if destination_message_ids is not None:
            ids_json = json.dumps(list(destination_message_ids))
            await self._db.execute(
                """
                UPDATE relay_records SET
                    status = ?,
                    destination_message_ids = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, ids_json, error_message, now, record_id),
            )
        else:
            await self._db.execute(
                """
                UPDATE relay_records SET
                    status = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, now, record_id),
            )
        row = await self._db.fetchone("SELECT * FROM relay_records WHERE id = ?", (record_id,))
        if row is None:
            raise RuntimeError("Relay record disappeared after update")
        return RelayRecordRow.from_row(row)

    async def delete_by_profile_id(self, profile_id: int) -> None:
        await self._db.execute(
            "DELETE FROM relay_records WHERE profile_id = ?",
            (profile_id,),
        )

    async def delete_by_network_id(self, network_id: int) -> None:
        await self._db.execute(
            "DELETE FROM relay_records WHERE network_id = ?",
            (network_id,),
        )


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str) -> str | None:
        row = await self._db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return None
        return str(row["value"])

    async def set(self, key: str, value: str) -> None:
        now = datetime.now(tz=UTC).isoformat()
        await self._db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
