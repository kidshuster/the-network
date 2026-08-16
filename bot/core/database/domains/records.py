from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import aiosqlite

from bot.constants import RelayStatus
from bot.core.database.connection import Database
from bot.core.database.models import (
    ClientRow,
    ClientSubscriptionRow,
    NetworkRow,
    RelayRecordRow,
    ServerRequestRow,
)
from bot.core.models.client import Client
from bot.core.models.client_subscription import ClientSubscription
from bot.core.models.errors import NetworkValidationError, ProfileValidationError, RelayError
from bot.core.models.network import Network
from bot.core.models.relay_record import RelayRecord
from bot.core.models.server_request import ServerRequest, ServerRequestStatus

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


async def _fetch_row_by_id(
    db: Database,
    *,
    table: str,
    row_id: int,
    not_found_message: str,
) -> aiosqlite.Row:
    row = await db.fetchone(f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    if row is None:
        raise RuntimeError(not_found_message)
    return row


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _enable_flag(value: bool) -> int:
    return 1 if value else 0


async def _list_rows(
    db: Database,
    sql: str,
    params: tuple[object, ...] = (),
) -> list[aiosqlite.Row]:
    return await db.fetchall(sql, params)


def _require_present[T](value: T | None, *, not_found: str) -> T:
    if value is None:
        raise RuntimeError(not_found)
    return value


class NetworkStore:
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
        feed_category_id: int | None = None,
        output_channel_id: int | None = None,
        concat_channel_id: int | None = None,
        profile_forum_channel_id: int | None = None,
        join_channel_id: int | None = None,
    ) -> Network:
        normalized_key = self.validate_key(key)
        name = display_name.strip()
        if not name:
            raise NetworkValidationError("Display name cannot be empty.")

        now = _now_iso()
        try:
            row_id = await self._db.insert(
                """
                INSERT INTO networks (
                    guild_id, key, display_name, feed_category_id,
                    output_channel_id, concat_channel_id, profile_forum_channel_id,
                    join_channel_id, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    guild_id,
                    normalized_key,
                    name,
                    feed_category_id,
                    output_channel_id,
                    concat_channel_id,
                    profile_forum_channel_id,
                    join_channel_id,
                    now,
                    now,
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise NetworkValidationError("A network with that key already exists.") from exc
        row = await _fetch_row_by_id(
            self._db,
            table="networks",
            row_id=row_id,
            not_found_message="Created network row not found",
        )
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
        rows = await _list_rows(self._db, "SELECT * FROM networks ORDER BY key ASC")
        return [NetworkRow.from_row(row) for row in rows]

    async def set_enabled(self, key: str, enabled: bool) -> Network:
        normalized_key = self.validate_key(key)
        existing = await self.get_by_key(normalized_key)
        if existing is None:
            raise NetworkValidationError(f"Network '{normalized_key}' was not found.")

        now = _now_iso()
        await self._db.execute(
            "UPDATE networks SET enabled = ?, updated_at = ? WHERE key = ?",
            (_enable_flag(enabled), now, normalized_key),
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

    async def delete_with_relations(self, key: str) -> Network:
        """Atomically detach subscriptions and remove every network-owned row."""
        normalized_key = self.validate_key(key)
        async with self._db.transaction() as connection:
            row = await self._db.fetchone(
                "SELECT * FROM networks WHERE key = ?",
                (normalized_key,),
            )
            if row is None:
                raise NetworkValidationError(f"Network '{normalized_key}' was not found.")
            network = NetworkRow.from_row(row)
            await connection.execute(
                """
                UPDATE client_subscriptions
                SET network_id = NULL, network_key = ?, updated_at = ?
                WHERE network_id = ?
                """,
                (network.key, _now_iso(), network.id),
            )
            await connection.execute(
                "DELETE FROM relay_records WHERE network_id = ?",
                (network.id,),
            )
            await connection.execute(
                "DELETE FROM server_requests WHERE network_id = ?",
                (network.id,),
            )
            await connection.execute("DELETE FROM networks WHERE id = ?", (network.id,))
        return network


class RelayStore:
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
        profile_id: int | None = None,
        client_id: int | None = None,
        network_id: int,
        destination_channel_id: int,
    ) -> RelayRecord:
        now = _now_iso()
        try:
            row_id = await self._db.insert(
                """
                INSERT INTO relay_records (
                    source_message_id, source_channel_id, source_webhook_id,
                    profile_id, client_id, network_id, destination_channel_id,
                    destination_message_ids, status, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_message_id,
                    source_channel_id,
                    source_webhook_id,
                    profile_id,
                    client_id,
                    network_id,
                    destination_channel_id,
                    "[]",
                    RelayStatus.PENDING,
                    None,
                    now,
                    now,
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise RelayError(
                f"Relay record already exists for message {source_message_id}."
            ) from exc
        row = await _fetch_row_by_id(
            self._db,
            table="relay_records",
            row_id=row_id,
            not_found_message="Created relay record not found",
        )
        return RelayRecordRow.from_row(row)

    async def update_status(
        self,
        record_id: int,
        *,
        status: RelayStatus,
        destination_message_ids: tuple[int, ...] | None = None,
        error_message: str | None = None,
    ) -> RelayRecord:
        now = _now_iso()
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
        return RelayRecordRow.from_row(
            await _fetch_row_by_id(
                self._db,
                table="relay_records",
                row_id=record_id,
                not_found_message="Relay record disappeared after update",
            )
        )

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


class RequestStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        *,
        guild_id: int,
        network_id: int | None,
        requester_user_id: int,
        server_name: str,
        display_name: str,
        profile_image_url: str,
        profile_image_data: bytes | None = None,
        repair_client_id: int | None = None,
    ) -> ServerRequest:
        now = _now_iso()
        row_id = await self._db.insert(
            """
            INSERT INTO server_requests (
                guild_id, network_id, requester_user_id,
                server_name, display_name, profile_image_url, profile_image_data,
                status, created_at, updated_at, repair_client_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                network_id,
                requester_user_id,
                server_name.strip(),
                display_name.strip(),
                profile_image_url.strip(),
                profile_image_data,
                ServerRequestStatus.PENDING,
                now,
                now,
                repair_client_id,
            ),
        )
        row = await _fetch_row_by_id(
            self._db,
            table="server_requests",
            row_id=row_id,
            not_found_message="Created server request not found",
        )
        return ServerRequestRow.from_row(row)

    async def _require_by_id(
        self,
        request_id: int,
        *,
        not_found: str,
    ) -> ServerRequest:
        return _require_present(await self.get_by_id(request_id), not_found=not_found)

    async def get_by_id(self, request_id: int) -> ServerRequest | None:
        row = await self._db.fetchone(
            "SELECT * FROM server_requests WHERE id = ?",
            (request_id,),
        )
        return ServerRequestRow.from_row(row) if row else None

    async def list_pending(self) -> list[ServerRequest]:
        rows = await _list_rows(
            self._db,
            "SELECT * FROM server_requests WHERE status = ? ORDER BY id ASC",
            (ServerRequestStatus.PENDING,),
        )
        return [ServerRequestRow.from_row(row) for row in rows]

    async def get_pending_for_requester(
        self,
        requester_user_id: int,
        *,
        network_id: int | None = None,
    ) -> ServerRequest | None:
        if network_id is not None:
            row = await self._db.fetchone(
                """
                SELECT * FROM server_requests
                WHERE network_id = ? AND requester_user_id = ? AND status = ?
                ORDER BY id DESC LIMIT 1
                """,
                (network_id, requester_user_id, ServerRequestStatus.PENDING),
            )
        else:
            row = await self._db.fetchone(
                """
                SELECT * FROM server_requests
                WHERE network_id IS NULL AND requester_user_id = ? AND status = ?
                ORDER BY id DESC LIMIT 1
                """,
                (requester_user_id, ServerRequestStatus.PENDING),
            )
        return ServerRequestRow.from_row(row) if row else None

    async def get_pending_for_repair_client(self, client_id: int) -> ServerRequest | None:
        row = await self._db.fetchone(
            """
            SELECT * FROM server_requests
            WHERE repair_client_id = ? AND status = ?
            ORDER BY id DESC LIMIT 1
            """,
            (client_id, ServerRequestStatus.PENDING),
        )
        return ServerRequestRow.from_row(row) if row else None

    async def set_moderator_message_id(self, request_id: int, message_id: int) -> ServerRequest:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE server_requests
            SET moderator_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, request_id),
        )
        return await self._require_by_id(
            request_id,
            not_found="Server request disappeared after update",
        )

    async def resolve(
        self,
        request_id: int,
        *,
        status: ServerRequestStatus,
        resolved_by_user_id: int,
    ) -> ServerRequest:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE server_requests
            SET status = ?, resolved_by_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, resolved_by_user_id, now, request_id),
        )
        return await self._require_by_id(
            request_id,
            not_found="Server request disappeared after resolve",
        )

    async def delete_by_network_id(self, network_id: int) -> None:
        await self._db.execute(
            "DELETE FROM server_requests WHERE network_id = ?",
            (network_id,),
        )

    async def delete_by_id(self, request_id: int) -> None:
        await self._db.execute(
            "DELETE FROM server_requests WHERE id = ?",
            (request_id,),
        )

    async def list_by_server_name_prefix(self, prefix: str) -> list[ServerRequest]:
        rows = await _list_rows(
            self._db,
            """
            SELECT * FROM server_requests
            WHERE server_name LIKE ?
            ORDER BY id ASC
            """,
            (f"{prefix}%",),
        )
        return [ServerRequestRow.from_row(row) for row in rows]


class SettingsStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str) -> str | None:
        row = await self._db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return None
        return str(row["value"])

    async def set(self, key: str, value: str) -> None:
        now = _now_iso()
        await self._db.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )

    async def delete(self, key: str) -> None:
        await self._db.execute("DELETE FROM settings WHERE key = ?", (key,))


class ClientStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _require_by_id(self, client_id: int, *, not_found: str) -> Client:
        return _require_present(await self.get_by_id(client_id), not_found=not_found)

    async def _require_subscription_by_id(
        self,
        subscription_id: int,
        *,
        not_found: str,
    ) -> ClientSubscription:
        return _require_present(
            await self.get_subscription_by_id(subscription_id),
            not_found=not_found,
        )

    async def create(
        self,
        *,
        guild_id: int,
        server_name: str,
        display_name: str,
        category_id: int,
        client_role_id: int,
        profile_channel_id: int,
        profile_message_id: int,
        enabled: bool = True,
    ) -> Client:
        now = _now_iso()
        try:
            row_id = await self._db.insert(
                """
                INSERT INTO clients (
                    guild_id, server_name, display_name, category_id,
                    client_role_id, profile_channel_id, profile_message_id,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    server_name.strip(),
                    display_name.strip(),
                    category_id,
                    client_role_id,
                    profile_channel_id,
                    profile_message_id,
                    _enable_flag(enabled),
                    now,
                    now,
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise ProfileValidationError(f"A client named {server_name!r} already exists.") from exc
        row = await _fetch_row_by_id(
            self._db,
            table="clients",
            row_id=row_id,
            not_found_message="Created client row not found",
        )
        return ClientRow.from_row(row)

    async def get_by_id(self, client_id: int) -> Client | None:
        row = await self._db.fetchone("SELECT * FROM clients WHERE id = ?", (client_id,))
        return ClientRow.from_row(row) if row else None

    async def get_by_server_name(
        self,
        guild_id: int,
        server_name: str,
    ) -> Client | None:
        name = server_name.strip()
        if not name:
            return None
        row = await self._db.fetchone(
            """
            SELECT * FROM clients
            WHERE guild_id = ? AND server_name = ? COLLATE NOCASE
            """,
            (guild_id, name),
        )
        return ClientRow.from_row(row) if row else None

    async def get_by_profile_channel(self, channel_id: int) -> Client | None:
        row = await self._db.fetchone(
            "SELECT * FROM clients WHERE profile_channel_id = ?",
            (channel_id,),
        )
        return ClientRow.from_row(row) if row else None

    async def list_all(self) -> list[Client]:
        rows = await _list_rows(
            self._db,
            "SELECT * FROM clients ORDER BY server_name ASC",
        )
        return [ClientRow.from_row(row) for row in rows]

    async def update_profile_message_id(self, client_id: int, message_id: int) -> Client:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE clients SET profile_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after profile message update",
        )

    async def update_provisioned_resources(
        self,
        client_id: int,
        *,
        category_id: int,
        client_role_id: int,
        profile_channel_id: int,
        profile_message_id: int,
        display_name: str | None = None,
    ) -> Client:
        now = _now_iso()
        if display_name is not None:
            label = display_name.strip()
            if not label:
                raise ProfileValidationError("Display name cannot be empty.")
            await self._db.execute(
                """
                UPDATE clients SET
                    category_id = ?, client_role_id = ?, profile_channel_id = ?,
                    profile_message_id = ?, display_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    category_id,
                    client_role_id,
                    profile_channel_id,
                    profile_message_id,
                    label,
                    now,
                    client_id,
                ),
            )
        else:
            await self._db.execute(
                """
                UPDATE clients SET
                    category_id = ?, client_role_id = ?, profile_channel_id = ?,
                    profile_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    category_id,
                    client_role_id,
                    profile_channel_id,
                    profile_message_id,
                    now,
                    client_id,
                ),
            )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after provisioned-resource update",
        )

    async def clear_subscriptions_with_relations(self, client_id: int) -> int:
        """Remove subscription rows for a client without deleting the client row."""
        async with self._db.transaction() as connection:
            cursor = await connection.execute(
                "SELECT id FROM client_subscriptions WHERE client_id = ?",
                (client_id,),
            )
            subscription_ids = [int(row[0]) for row in await cursor.fetchall()]
            await cursor.close()
            if not subscription_ids:
                return 0
            placeholders = ", ".join("?" for _ in subscription_ids)
            await connection.execute(
                f"""
                DELETE FROM managed_resources
                WHERE owner_type = 'subscription' AND owner_id IN ({placeholders})
                """,
                tuple(subscription_ids),
            )
            await connection.execute(
                f"""
                DELETE FROM client_blacklists
                WHERE subscription_id IN ({placeholders})
                """,
                tuple(subscription_ids),
            )
            await connection.execute(
                "DELETE FROM client_blacklists WHERE blocked_client_id = ?",
                (client_id,),
            )
            await connection.execute(
                "DELETE FROM client_subscriptions WHERE client_id = ?",
                (client_id,),
            )
        return len(subscription_ids)

    async def update_display_name(self, client_id: int, display_name: str) -> Client:
        label = display_name.strip()
        if not label:
            raise ProfileValidationError("Display name cannot be empty.")
        now = _now_iso()
        await self._db.execute(
            "UPDATE clients SET display_name = ?, updated_at = ? WHERE id = ?",
            (label, now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after display name update",
        )

    async def update_emoji_fields(
        self,
        client_id: int,
        *,
        emoji_id: int | None,
        emoji_name: str | None,
        image_hash: str | None,
        degraded_reason: str | None,
    ) -> Client:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE clients SET
                emoji_id = ?, emoji_name = ?, image_hash = ?,
                degraded_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (emoji_id, emoji_name, image_hash, degraded_reason, now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after emoji update",
        )

    async def set_enabled(self, client_id: int, enabled: bool) -> Client:
        now = _now_iso()
        await self._db.execute(
            "UPDATE clients SET enabled = ?, updated_at = ? WHERE id = ?",
            (_enable_flag(enabled), now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after enable update",
        )

    async def set_timecode_enabled(self, client_id: int, enabled: bool) -> Client:
        now = _now_iso()
        await self._db.execute(
            "UPDATE clients SET timecode_enabled = ?, updated_at = ? WHERE id = ?",
            (_enable_flag(enabled), now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after timecode update",
        )

    async def set_read_only(self, client_id: int, read_only: bool) -> Client:
        now = _now_iso()
        await self._db.execute(
            "UPDATE clients SET read_only = ?, updated_at = ? WHERE id = ?",
            (_enable_flag(read_only), now, client_id),
        )
        return await self._require_by_id(
            client_id,
            not_found="Client disappeared after read-only update",
        )

    async def delete(self, client_id: int) -> Client | None:
        existing = await self.get_by_id(client_id)
        if existing is None:
            return None
        await self._db.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        return existing

    async def delete_with_relations(self, client_id: int) -> Client | None:
        """Atomically remove a client and every relation that can block deletion."""
        existing = await self.get_by_id(client_id)
        if existing is None:
            return None
        async with self._db.transaction() as connection:
            await connection.execute(
                """
                DELETE FROM managed_resources
                WHERE owner_type = 'subscription' AND owner_id IN (
                    SELECT id FROM client_subscriptions WHERE client_id = ?
                )
                """,
                (client_id,),
            )
            await connection.execute(
                "DELETE FROM managed_resources WHERE owner_type = 'client' AND owner_id = ?",
                (client_id,),
            )
            await connection.execute(
                "DELETE FROM client_blacklists WHERE blocked_client_id = ?",
                (client_id,),
            )
            await connection.execute(
                """
                DELETE FROM client_blacklists
                WHERE subscription_id IN (
                    SELECT id FROM client_subscriptions WHERE client_id = ?
                )
                """,
                (client_id,),
            )
            await connection.execute(
                "DELETE FROM client_subscriptions WHERE client_id = ?",
                (client_id,),
            )
            await connection.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        return existing

    async def create_subscription(
        self,
        *,
        client_id: int,
        network_id: int,
        network_key: str,
        publish_channel_id: int | None,
        subscribe_channel_id: int,
        moderation_message_id: int | None = None,
        enabled: bool = True,
    ) -> ClientSubscription:
        normalized_key = network_key.strip().lower()
        now = _now_iso()
        try:
            row_id = await self._db.insert(
                """
                INSERT INTO client_subscriptions (
                    client_id, network_id, network_key, publish_channel_id,
                    subscribe_channel_id, moderation_message_id,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    network_id,
                    normalized_key,
                    publish_channel_id,
                    subscribe_channel_id,
                    moderation_message_id,
                    _enable_flag(enabled),
                    now,
                    now,
                ),
            )
        except aiosqlite.IntegrityError as exc:
            raise ProfileValidationError(
                "This client is already subscribed to that network."
            ) from exc
        row = await _fetch_row_by_id(
            self._db,
            table="client_subscriptions",
            row_id=row_id,
            not_found_message="Created subscription row not found",
        )
        return ClientSubscriptionRow.from_row(row)

    async def get_subscription_by_id(self, subscription_id: int) -> ClientSubscription | None:
        row = await self._db.fetchone(
            "SELECT * FROM client_subscriptions WHERE id = ?",
            (subscription_id,),
        )
        return ClientSubscriptionRow.from_row(row) if row else None

    async def get_subscription_by_client_and_key(
        self,
        client_id: int,
        network_key: str,
    ) -> ClientSubscription | None:
        normalized_key = network_key.strip().lower()
        row = await self._db.fetchone(
            """
            SELECT * FROM client_subscriptions
            WHERE client_id = ? AND network_key = ?
            """,
            (client_id, normalized_key),
        )
        return ClientSubscriptionRow.from_row(row) if row else None

    async def detach_subscriptions_from_network(
        self,
        network_id: int,
        network_key: str,
    ) -> None:
        normalized_key = network_key.strip().lower()
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_id = NULL, network_key = ?, updated_at = ?
            WHERE network_id = ?
            """,
            (normalized_key, now, network_id),
        )

    async def relink_subscription(
        self,
        subscription_id: int,
        network_id: int,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (network_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after relink",
        )

    async def get_subscription(
        self,
        client_id: int,
        network_id: int,
    ) -> ClientSubscription | None:
        row = await self._db.fetchone(
            """
            SELECT * FROM client_subscriptions
            WHERE client_id = ? AND network_id = ?
            """,
            (client_id, network_id),
        )
        return ClientSubscriptionRow.from_row(row) if row else None

    async def get_subscription_by_publish_channel(
        self,
        publish_channel_id: int,
    ) -> ClientSubscription | None:
        if publish_channel_id <= 0:
            return None
        row = await self._db.fetchone(
            "SELECT * FROM client_subscriptions WHERE publish_channel_id = ?",
            (publish_channel_id,),
        )
        return ClientSubscriptionRow.from_row(row) if row else None

    async def update_publish_channel_id(
        self,
        subscription_id: int,
        publish_channel_id: int | None,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET publish_channel_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (publish_channel_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after publish channel update",
        )

    async def list_subscriptions_by_network(
        self,
        network_id: int,
    ) -> list[ClientSubscription]:
        rows = await _list_rows(
            self._db,
            """
            SELECT * FROM client_subscriptions
            WHERE network_id = ? ORDER BY id ASC
            """,
            (network_id,),
        )
        return [ClientSubscriptionRow.from_row(row) for row in rows]

    async def list_subscriptions_by_client(
        self,
        client_id: int,
    ) -> list[ClientSubscription]:
        rows = await _list_rows(
            self._db,
            """
            SELECT * FROM client_subscriptions
            WHERE client_id = ? ORDER BY id ASC
            """,
            (client_id,),
        )
        return [ClientSubscriptionRow.from_row(row) for row in rows]

    async def list_all_subscriptions(self) -> list[ClientSubscription]:
        rows = await _list_rows(
            self._db,
            "SELECT * FROM client_subscriptions ORDER BY id ASC",
        )
        return [ClientSubscriptionRow.from_row(row) for row in rows]

    async def update_moderation_message_id(
        self,
        subscription_id: int,
        message_id: int,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET moderation_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after moderation message update",
        )

    async def set_subscribe_confirmed(
        self,
        subscription_id: int,
        confirmed: bool = True,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET subscribe_confirmed = ?, updated_at = ?
            WHERE id = ?
            """,
            (_enable_flag(confirmed), now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after subscribe confirm update",
        )

    async def update_publish_setup_message_id(
        self,
        subscription_id: int,
        message_id: int | None,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET publish_setup_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after publish setup message update",
        )

    async def update_subscribe_setup_message_id(
        self,
        subscription_id: int,
        message_id: int | None,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET subscribe_setup_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after subscribe setup message update",
        )

    async def update_activation_welcome_message_id(
        self,
        subscription_id: int,
        message_id: int | None,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET activation_welcome_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after activation welcome update",
        )

    async def claim_network_welcome(self, subscription_id: int) -> ClientSubscription | None:
        """Atomically claim first-time network welcome posting.

        Sets ``network_welcome_message_id`` to ``0`` as an in-progress sentinel.
        Returns the updated row when this caller won the claim, otherwise ``None``.
        """
        now = _now_iso()
        updated = await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_welcome_message_id = 0, updated_at = ?
            WHERE id = ?
              AND network_welcome_complete = 0
              AND network_welcome_message_id IS NULL
            """,
            (now, subscription_id),
        )
        if updated == 0:
            return None
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after network welcome claim",
        )

    async def clear_network_welcome_claim(self, subscription_id: int) -> ClientSubscription:
        """Release an in-progress claim so a later activation can retry posting."""
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_welcome_message_id = NULL, updated_at = ?
            WHERE id = ?
              AND network_welcome_complete = 0
              AND network_welcome_message_id = 0
            """,
            (now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after network welcome claim clear",
        )

    async def update_network_welcome_message_id(
        self,
        subscription_id: int,
        message_id: int | None,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_welcome_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after network welcome message update",
        )

    async def mark_network_welcome_complete(
        self,
        subscription_id: int,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_welcome_complete = 1, updated_at = ?
            WHERE id = ?
            """,
            (now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after network welcome complete",
        )

    async def mark_silent_reconnect(self, subscription_id: int) -> ClientSubscription:
        """Adopt a rediscovered subscription without setup prompts or welcome spam.

        Used when publish/subscribe channels still exist after hub uninit/network
        recreate. ``activation_welcome_message_id = 0`` is a durable sentinel that
        means "already welcomed / do not post".
        """
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET subscribe_confirmed = 1,
                activation_welcome_message_id = 0,
                network_welcome_complete = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after silent reconnect",
        )

    async def clear_network_welcome(self, subscription_id: int) -> ClientSubscription:
        """Clear network welcome durable state so a later activation can announce again."""
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions
            SET network_welcome_message_id = NULL,
                network_welcome_complete = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after network welcome clear",
        )

    async def set_subscription_enabled(
        self,
        subscription_id: int,
        enabled: bool,
    ) -> ClientSubscription:
        now = _now_iso()
        await self._db.execute(
            """
            UPDATE client_subscriptions SET enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (_enable_flag(enabled), now, subscription_id),
        )
        return await self._require_subscription_by_id(
            subscription_id,
            not_found="Subscription disappeared after enable update",
        )

    async def delete_subscription(self, subscription_id: int) -> ClientSubscription | None:
        existing = await self.get_subscription_by_id(subscription_id)
        if existing is None:
            return None
        await self._db.execute(
            "DELETE FROM client_subscriptions WHERE id = ?",
            (subscription_id,),
        )
        return existing

    async def delete_subscription_with_relations(
        self,
        subscription_id: int,
    ) -> ClientSubscription | None:
        """Atomically remove a subscription and its dependent blacklist rows."""
        existing = await self.get_subscription_by_id(subscription_id)
        if existing is None:
            return None
        async with self._db.transaction() as connection:
            await connection.execute(
                "DELETE FROM managed_resources WHERE owner_type = 'subscription' AND owner_id = ?",
                (subscription_id,),
            )
            await connection.execute(
                "DELETE FROM client_blacklists WHERE subscription_id = ?",
                (subscription_id,),
            )
            await connection.execute(
                "DELETE FROM client_subscriptions WHERE id = ?",
                (subscription_id,),
            )
        return existing

    async def delete_subscriptions_by_network(self, network_id: int) -> None:
        await self._db.execute(
            "DELETE FROM client_subscriptions WHERE network_id = ?",
            (network_id,),
        )

    async def add_blacklist(
        self,
        subscription_id: int,
        blocked_client_id: int,
    ) -> None:
        now = _now_iso()
        try:
            await self._db.execute(
                """
                INSERT INTO client_blacklists (
                    subscription_id, blocked_client_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (subscription_id, blocked_client_id, now),
            )
        except aiosqlite.IntegrityError:
            return

    async def remove_blacklist(
        self,
        subscription_id: int,
        blocked_client_id: int,
    ) -> None:
        await self._db.execute(
            """
            DELETE FROM client_blacklists
            WHERE subscription_id = ? AND blocked_client_id = ?
            """,
            (subscription_id, blocked_client_id),
        )

    async def is_blacklisted(
        self,
        subscription_id: int,
        blocked_client_id: int,
    ) -> bool:
        row = await self._db.fetchone(
            """
            SELECT 1 FROM client_blacklists
            WHERE subscription_id = ? AND blocked_client_id = ?
            """,
            (subscription_id, blocked_client_id),
        )
        return row is not None

    async def is_relay_blocked(
        self,
        *,
        publisher_subscription_id: int,
        publisher_client_id: int,
        destination_subscription_id: int,
        destination_client_id: int,
    ) -> bool:
        """True when either party has blacklisted the other for relay delivery."""
        row = await self._db.fetchone(
            """
            SELECT 1 FROM client_blacklists
            WHERE (subscription_id = ? AND blocked_client_id = ?)
               OR (subscription_id = ? AND blocked_client_id = ?)
            LIMIT 1
            """,
            (
                destination_subscription_id,
                publisher_client_id,
                publisher_subscription_id,
                destination_client_id,
            ),
        )
        return row is not None

    async def list_blacklisted_client_ids(self, subscription_id: int) -> list[int]:
        rows = await _list_rows(
            self._db,
            """
            SELECT blocked_client_id FROM client_blacklists
            WHERE subscription_id = ?
            ORDER BY blocked_client_id ASC
            """,
            (subscription_id,),
        )
        return [int(row["blocked_client_id"]) for row in rows]

    async def delete_blacklists_for_subscription(self, subscription_id: int) -> None:
        await self._db.execute(
            "DELETE FROM client_blacklists WHERE subscription_id = ?",
            (subscription_id,),
        )

    async def delete_blacklists_for_client(self, client_id: int) -> None:
        await self._db.execute(
            """
            DELETE FROM client_blacklists
            WHERE subscription_id IN (
                SELECT id FROM client_subscriptions WHERE client_id = ?
            )
            """,
            (client_id,),
        )

    async def delete_blacklists_blocking_client(self, client_id: int) -> None:
        await self._db.execute(
            "DELETE FROM client_blacklists WHERE blocked_client_id = ?",
            (client_id,),
        )
