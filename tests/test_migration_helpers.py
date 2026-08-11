"""Characterize migration helper correctness before repository refactor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.core.database.connection import Database
from bot.core.database.migrations import _column_not_null, run_migrations


@pytest.mark.asyncio
async def test_column_not_null_detects_not_null_column(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    await db.connect()
    await db.connection.execute("CREATE TABLE sample (id INTEGER NOT NULL, label TEXT)")
    await db.connection.commit()

    assert await _column_not_null(db, "sample", "id") is True
    assert await _column_not_null(db, "sample", "label") is False
    assert await _column_not_null(db, "sample", "missing") is False

    await db.close()


@pytest.mark.asyncio
async def test_column_not_null_uses_single_fetchall(tmp_path: Path) -> None:
    """Regression: double fetchall on the same cursor returns empty rows."""
    db_path = tmp_path / "test.db"
    db = Database(db_path)
    await db.connect()
    await db.connection.execute("CREATE TABLE sample (required INTEGER NOT NULL)")
    await db.connection.commit()

    cursor = await db.connection.execute("PRAGMA table_info(sample)")
    first = await cursor.fetchall()
    second = await cursor.fetchall()
    await cursor.close()
    assert len(first) == 1
    assert second == []

    assert await _column_not_null(db, "sample", "required") is True

    await db.close()


@pytest.mark.asyncio
async def test_column_not_null_mock_rejects_double_fetchall() -> None:
    row = (0, "feed_category_id", "INTEGER", 1, None, 0)
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(side_effect=[[row], []])
    cursor.close = AsyncMock()

    db = MagicMock()
    db.connection.execute = AsyncMock(return_value=cursor)

    assert await _column_not_null(db, "networks", "feed_category_id") is True
    assert cursor.fetchall.await_count == 1


@pytest.mark.asyncio
async def test_fresh_schema_has_expected_not_null_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "relay.db"
    db = Database(db_path)
    await db.connect()
    await run_migrations(db)

    assert await _column_not_null(db, "clients", "guild_id") is True
    assert await _column_not_null(db, "client_subscriptions", "client_id") is True
    assert await _column_not_null(db, "networks", "key") is True

    await db.close()
