from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from bot.core.database.connection import Database
from bot.core.database.migrations import run_migrations


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    await database.connect()
    await run_migrations(database)
    yield database
    await database.close()
