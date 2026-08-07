from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from bot.constants import SCHEMA_VERSION
from bot.db.connection import Database

logger = logging.getLogger(__name__)

MigrationFn = Callable[[Database], Awaitable[None]]


def _as_int(value: object | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return int(str(value))


async def _migration_v1(db: Database) -> None:
    await db.connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            key TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            feed_category_id INTEGER NOT NULL UNIQUE,
            output_channel_id INTEGER NOT NULL UNIQUE,
            concat_channel_id INTEGER,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            profile_thread_id INTEGER NOT NULL UNIQUE,
            profile_starter_message_id INTEGER NOT NULL UNIQUE,
            source_channel_id INTEGER NOT NULL UNIQUE,
            network_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            emoji_id INTEGER,
            emoji_name TEXT,
            image_hash TEXT,
            image_source_url TEXT,
            degraded_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (network_id) REFERENCES networks(id)
        );

        CREATE TABLE IF NOT EXISTS relay_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_message_id INTEGER NOT NULL UNIQUE,
            source_channel_id INTEGER NOT NULL,
            source_webhook_id INTEGER,
            profile_id INTEGER NOT NULL,
            network_id INTEGER NOT NULL,
            destination_channel_id INTEGER NOT NULL,
            destination_message_ids TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles(id),
            FOREIGN KEY (network_id) REFERENCES networks(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    await db.connection.commit()


async def _migration_v2(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(networks)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "profile_forum_channel_id" not in columns:
        await db.connection.execute(
            "ALTER TABLE networks ADD COLUMN profile_forum_channel_id INTEGER"
        )
        await db.connection.commit()


async def _migration_v3(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(profiles)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "partner_role_id" not in columns:
        await db.connection.execute("ALTER TABLE profiles ADD COLUMN partner_role_id INTEGER")
        await db.connection.commit()


async def _migration_v4(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(profiles)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "profile_forum_channel_id" not in columns:
        await db.connection.execute(
            "ALTER TABLE profiles ADD COLUMN profile_forum_channel_id INTEGER"
        )
        await db.connection.commit()


async def _migration_v5(db: Database) -> None:
    await db.connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS server_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            network_id INTEGER NOT NULL,
            requester_user_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            profile_image_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            moderator_message_id INTEGER,
            resolved_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (network_id) REFERENCES networks(id)
        );

        CREATE INDEX IF NOT EXISTS idx_server_requests_status
            ON server_requests(status);
        CREATE INDEX IF NOT EXISTS idx_server_requests_requester
            ON server_requests(network_id, requester_user_id, status);
        """
    )
    await db.connection.commit()


async def _migration_v6(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(server_requests)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "profile_image_data" not in columns:
        await db.connection.execute(
            "ALTER TABLE server_requests ADD COLUMN profile_image_data BLOB"
        )
        await db.connection.commit()


async def _migration_v7(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(networks)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "join_channel_id" not in columns:
        await db.connection.execute("ALTER TABLE networks ADD COLUMN join_channel_id INTEGER")
        await db.connection.commit()


async def _table_exists(db: Database, name: str) -> bool:
    row = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    )
    return row is not None


async def _column_not_null(db: Database, table: str, column: str) -> bool:
    cursor = await db.connection.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    await cursor.close()
    for row in rows:
        if str(row[1]) == column:
            return int(row[3]) == 1
    return False


async def _recreate_networks_with_nullable_channels(db: Database) -> None:
    if not await _column_not_null(db, "networks", "feed_category_id"):
        if await _table_exists(db, "networks_new"):
            await db.connection.execute("DROP TABLE networks_new")
            await db.connection.commit()
        return

    if await _table_exists(db, "networks_new"):
        await db.connection.execute("DROP TABLE networks_new")
        await db.connection.commit()

    await db.connection.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.connection.executescript(
            """
            CREATE TABLE networks_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                feed_category_id INTEGER,
                output_channel_id INTEGER,
                concat_channel_id INTEGER,
                profile_forum_channel_id INTEGER,
                join_channel_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO networks_new (
                id, guild_id, key, display_name, feed_category_id, output_channel_id,
                concat_channel_id, profile_forum_channel_id, join_channel_id, enabled,
                created_at, updated_at
            )
            SELECT
                id, guild_id, key, display_name, feed_category_id, output_channel_id,
                concat_channel_id, profile_forum_channel_id, join_channel_id, enabled,
                created_at, updated_at
            FROM networks;
            DROP TABLE networks;
            ALTER TABLE networks_new RENAME TO networks;
            """
        )
    finally:
        await db.connection.execute("PRAGMA foreign_keys = ON")
    await db.connection.commit()


async def _recreate_server_requests_with_nullable_network(db: Database) -> None:
    if not await _column_not_null(db, "server_requests", "network_id"):
        if await _table_exists(db, "server_requests_new"):
            await db.connection.execute("DROP TABLE server_requests_new")
            await db.connection.commit()
        return

    if await _table_exists(db, "server_requests_new"):
        await db.connection.execute("DROP TABLE server_requests_new")
        await db.connection.commit()

    await db.connection.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.connection.executescript(
            """
            CREATE TABLE server_requests_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                network_id INTEGER,
                requester_user_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                profile_image_url TEXT NOT NULL,
                profile_image_data BLOB,
                status TEXT NOT NULL DEFAULT 'pending',
                moderator_message_id INTEGER,
                resolved_by_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (network_id) REFERENCES networks(id)
            );
            INSERT INTO server_requests_new SELECT * FROM server_requests;
            DROP TABLE server_requests;
            ALTER TABLE server_requests_new RENAME TO server_requests;
            CREATE INDEX IF NOT EXISTS idx_server_requests_status
                ON server_requests(status);
            CREATE INDEX IF NOT EXISTS idx_server_requests_requester
                ON server_requests(requester_user_id, status);
            """
        )
    finally:
        await db.connection.execute("PRAGMA foreign_keys = ON")
    await db.connection.commit()


async def _recreate_relay_records_with_client_id(db: Database) -> None:
    if await _table_exists(db, "relay_records"):
        cursor = await db.connection.execute("PRAGMA table_info(relay_records)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        await cursor.close()
        if "client_id" in columns:
            if await _table_exists(db, "relay_records_new"):
                await db.connection.execute("DROP TABLE relay_records_new")
                await db.connection.commit()
            return

    if await _table_exists(db, "relay_records_new"):
        await db.connection.execute("DROP TABLE relay_records_new")
        await db.connection.commit()

    await db.connection.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.connection.executescript(
            """
            CREATE TABLE relay_records_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_message_id INTEGER NOT NULL UNIQUE,
                source_channel_id INTEGER NOT NULL,
                source_webhook_id INTEGER,
                profile_id INTEGER,
                client_id INTEGER,
                network_id INTEGER NOT NULL,
                destination_channel_id INTEGER NOT NULL,
                destination_message_ids TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (network_id) REFERENCES networks(id)
            );
            INSERT INTO relay_records_new (
                id, source_message_id, source_channel_id, source_webhook_id,
                profile_id, client_id, network_id, destination_channel_id,
                destination_message_ids, status, error_message, created_at, updated_at
            )
            SELECT
                id, source_message_id, source_channel_id, source_webhook_id,
                profile_id, profile_id, network_id, destination_channel_id,
                destination_message_ids, status, error_message, created_at, updated_at
            FROM relay_records;
            DROP TABLE relay_records;
            ALTER TABLE relay_records_new RENAME TO relay_records;
            """
        )
    finally:
        await db.connection.execute("PRAGMA foreign_keys = ON")
    await db.connection.commit()


async def _migration_v8(db: Database) -> None:
    await db.connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            category_id INTEGER NOT NULL UNIQUE,
            client_role_id INTEGER NOT NULL,
            profile_channel_id INTEGER NOT NULL UNIQUE,
            profile_message_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            emoji_id INTEGER,
            emoji_name TEXT,
            image_hash TEXT,
            degraded_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, server_name)
        );

        CREATE TABLE IF NOT EXISTS client_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            network_id INTEGER NOT NULL,
            publish_channel_id INTEGER NOT NULL UNIQUE,
            subscribe_channel_id INTEGER NOT NULL UNIQUE,
            moderation_message_id INTEGER,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (network_id) REFERENCES networks(id),
            UNIQUE(client_id, network_id)
        );

        CREATE TABLE IF NOT EXISTS client_blacklists (
            subscription_id INTEGER NOT NULL,
            blocked_client_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (subscription_id, blocked_client_id),
            FOREIGN KEY (subscription_id) REFERENCES client_subscriptions(id),
            FOREIGN KEY (blocked_client_id) REFERENCES clients(id)
        );

        CREATE INDEX IF NOT EXISTS idx_client_subscriptions_network
            ON client_subscriptions(network_id);
        CREATE INDEX IF NOT EXISTS idx_client_subscriptions_publish
            ON client_subscriptions(publish_channel_id);
        """
    )
    await db.connection.commit()

    await _recreate_networks_with_nullable_channels(db)
    await _recreate_server_requests_with_nullable_network(db)

    # Migrate profiles -> clients + subscriptions (one client per server_name per guild)
    cursor = await db.connection.execute("SELECT COUNT(*) FROM clients")
    client_count = (await cursor.fetchone())[0]
    await cursor.close()
    if client_count == 0:
        profile_cursor = await db.connection.execute("SELECT * FROM profiles")
        profiles = await profile_cursor.fetchall()
        await profile_cursor.close()
        client_by_name: dict[tuple[int, str], int] = {}
        now = datetime.now(tz=UTC).isoformat()
        for profile in profiles:
            guild_id = int(profile["guild_id"])
            server_name = str(profile["server_name"])
            key = (guild_id, server_name.casefold())
            client_id = client_by_name.get(key)
            if client_id is None:
                partner_role = profile["partner_role_id"]
                ins = await db.connection.execute(
                    """
                    INSERT INTO clients (
                        guild_id, server_name, display_name, category_id,
                        client_role_id, profile_channel_id, profile_message_id,
                        enabled, emoji_id, emoji_name, image_hash, degraded_reason,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        server_name,
                        str(profile["display_name"]),
                        int(profile["source_channel_id"]),
                        int(partner_role) if partner_role is not None else 0,
                        int(profile["profile_thread_id"]),
                        int(profile["profile_starter_message_id"]),
                        int(profile["enabled"]),
                        profile["emoji_id"],
                        profile["emoji_name"],
                        profile["image_hash"],
                        profile["degraded_reason"],
                        now,
                        now,
                    ),
                )
                client_id = ins.lastrowid
                client_by_name[key] = client_id
            if client_id is None:
                continue
            await db.connection.execute(
                """
                INSERT OR IGNORE INTO client_subscriptions (
                    client_id, network_id, publish_channel_id,
                    subscribe_channel_id, moderation_message_id,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    client_id,
                    int(profile["network_id"]),
                    int(profile["source_channel_id"]),
                    int(profile["source_channel_id"]),
                    int(profile["enabled"]),
                    now,
                    now,
                ),
            )
        await db.connection.commit()


async def _migration_v9(db: Database) -> None:
    await _recreate_relay_records_with_client_id(db)


async def _migration_v10(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(client_subscriptions)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "network_key" in columns:
        return

    await db.connection.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.connection.executescript(
            """
            CREATE TABLE client_subscriptions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                network_id INTEGER,
                network_key TEXT NOT NULL,
                publish_channel_id INTEGER NOT NULL UNIQUE,
                subscribe_channel_id INTEGER NOT NULL UNIQUE,
                moderation_message_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (network_id) REFERENCES networks(id),
                UNIQUE(client_id, network_key)
            );
            INSERT INTO client_subscriptions_new (
                id, client_id, network_id, network_key,
                publish_channel_id, subscribe_channel_id,
                moderation_message_id, enabled, created_at, updated_at
            )
            SELECT
                cs.id, cs.client_id, cs.network_id, n.key,
                cs.publish_channel_id, cs.subscribe_channel_id,
                cs.moderation_message_id, cs.enabled, cs.created_at, cs.updated_at
            FROM client_subscriptions cs
            JOIN networks n ON n.id = cs.network_id;
            DROP TABLE client_subscriptions;
            ALTER TABLE client_subscriptions_new RENAME TO client_subscriptions;
            CREATE INDEX IF NOT EXISTS idx_client_subscriptions_network
                ON client_subscriptions(network_id);
            CREATE INDEX IF NOT EXISTS idx_client_subscriptions_publish
                ON client_subscriptions(publish_channel_id);
            """
        )
    finally:
        await db.connection.execute("PRAGMA foreign_keys = ON")
    await db.connection.commit()


async def _migration_v12(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(client_subscriptions)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "activation_welcome_message_id" in columns:
        return

    await db.connection.execute(
        "ALTER TABLE client_subscriptions ADD COLUMN activation_welcome_message_id INTEGER"
    )
    await db.connection.commit()


async def _migration_v11(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(client_subscriptions)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "subscribe_confirmed" in columns:
        return

    await db.connection.execute(
        "ALTER TABLE client_subscriptions ADD COLUMN subscribe_confirmed INTEGER NOT NULL DEFAULT 0"
    )
    await db.connection.execute(
        "ALTER TABLE client_subscriptions ADD COLUMN publish_setup_message_id INTEGER"
    )
    await db.connection.execute(
        "ALTER TABLE client_subscriptions ADD COLUMN subscribe_setup_message_id INTEGER"
    )
    await db.connection.commit()


async def _migration_v13(db: Database) -> None:
    cursor = await db.connection.execute("PRAGMA table_info(clients)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    if "timecode_enabled" in columns:
        return

    await db.connection.execute(
        "ALTER TABLE clients ADD COLUMN timecode_enabled INTEGER NOT NULL DEFAULT 1"
    )
    await db.connection.commit()


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_v1,
    2: _migration_v2,
    3: _migration_v3,
    4: _migration_v4,
    5: _migration_v5,
    6: _migration_v6,
    7: _migration_v7,
    8: _migration_v8,
    9: _migration_v9,
    10: _migration_v10,
    11: _migration_v11,
    12: _migration_v12,
    13: _migration_v13,
}


async def run_migrations(db: Database) -> int:
    """Apply pending migrations. Returns the schema version after migration."""
    await db.connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    await db.connection.commit()

    current = await db.fetchval("SELECT MAX(version) FROM schema_migrations")
    current_version = _as_int(current)

    for version in sorted(MIGRATIONS):
        if version <= current_version:
            continue
        logger.info("Applying database migration", extra={"version": version})
        await MIGRATIONS[version](db)
        await db.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        current_version = version

    if current_version == 0 and SCHEMA_VERSION >= 1:
        raise RuntimeError("No migrations were applied")

    logger.info(
        "Database migrations complete",
        extra={"schema_version": current_version, "path": str(db.path)},
    )
    return current_version


async def count_networks(db: Database) -> int:
    value = await db.fetchval("SELECT COUNT(*) FROM networks")
    return _as_int(value)


async def count_profiles(db: Database) -> tuple[int, int]:
    total_raw = await db.fetchval("SELECT COUNT(*) FROM profiles")
    enabled_raw = await db.fetchval("SELECT COUNT(*) FROM profiles WHERE enabled = 1")
    return _as_int(total_raw), _as_int(enabled_raw)
