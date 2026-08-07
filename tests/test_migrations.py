from __future__ import annotations

from pathlib import Path

import pytest

from bot.db.connection import Database
from bot.db.migrations import count_networks, count_profiles, run_migrations


@pytest.mark.asyncio
async def test_run_migrations_creates_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "relay.db"
    db = Database(db_path)
    await db.connect()

    version = await run_migrations(db)

    assert version == 13
    assert db_path.exists()

    cursor = await db.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    tables = {row[0] for row in rows}
    assert {
        "schema_migrations",
        "networks",
        "profiles",
        "relay_records",
        "server_requests",
        "settings",
        "clients",
        "client_subscriptions",
        "client_blacklists",
    }.issubset(tables)

    cursor = await db.connection.execute("PRAGMA table_info(client_subscriptions)")
    columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    assert "activation_welcome_message_id" in columns

    cursor = await db.connection.execute("PRAGMA table_info(clients)")
    client_columns = {str(row[1]) for row in await cursor.fetchall()}
    await cursor.close()
    assert "timecode_enabled" in client_columns

    assert await count_networks(db) == 0
    total, enabled = await count_profiles(db)
    assert total == 0
    assert enabled == 0

    await db.close()


@pytest.mark.asyncio
async def test_run_migrations_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "relay.db"
    db = Database(db_path)
    await db.connect()

    first = await run_migrations(db)
    second = await run_migrations(db)

    assert first == 13
    assert second == 13

    cursor = await db.connection.execute("SELECT version FROM schema_migrations")
    migration_rows = await cursor.fetchall()
    await cursor.close()
    assert len(migration_rows) == 13

    await db.close()
