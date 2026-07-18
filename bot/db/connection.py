from __future__ import annotations

from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        await self.connection.execute(sql, params)
        await self.connection.commit()

    async def fetchone(self, sql: str, params: tuple[object, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.connection.execute(sql, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchval(self, sql: str, params: tuple[object, ...] = ()) -> object | None:
        row = await self.fetchone(sql, params)
        if row is None:
            return None
        return row[0]  # type: ignore[no-any-return]
