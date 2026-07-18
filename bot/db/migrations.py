from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

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


MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_v1,
    2: _migration_v2,
    3: _migration_v3,
    4: _migration_v4,
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
