from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._transaction_lock = asyncio.Lock()
        self._transaction_owner: asyncio.Task[object] | None = None

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

    def _owns_transaction(self) -> bool:
        task = asyncio.current_task()
        return task is not None and task is self._transaction_owner

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        if self._owns_transaction():
            cursor = await self.connection.execute(sql, params)
            count = cursor.rowcount
            await cursor.close()
            return count
        async with self._transaction_lock:
            try:
                cursor = await self.connection.execute(sql, params)
                count = cursor.rowcount
                await cursor.close()
                await self.connection.commit()
                return count
            except BaseException:
                await self.connection.rollback()
                raise

    async def insert(self, sql: str, params: tuple[object, ...] = ()) -> int:
        async def _insert() -> int:
            cursor = await self.connection.execute(sql, params)
            row_id = cursor.lastrowid
            await cursor.close()
            if row_id is None:
                raise RuntimeError("Database insert did not return a row id")
            return row_id

        if self._owns_transaction():
            return await _insert()
        async with self._transaction_lock:
            try:
                row_id = await _insert()
                await self.connection.commit()
                return row_id
            except BaseException:
                await self.connection.rollback()
                raise

    async def fetchall(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[aiosqlite.Row]:
        async def _fetch() -> list[aiosqlite.Row]:
            cursor = await self.connection.execute(sql, params)
            rows = await cursor.fetchall()
            await cursor.close()
            return list(rows)

        if self._owns_transaction():
            return await _fetch()
        async with self._transaction_lock:
            return await _fetch()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run a Store recipe atomically on this connection.

        Transactions are deliberately non-nestable: a named Store recipe owns its
        whole commit boundary, which prevents partial commits hidden in callers.
        """
        task = asyncio.current_task()
        if task is not None and task is self._transaction_owner:
            raise RuntimeError("Nested database transactions are not supported")
        async with self._transaction_lock:
            self._transaction_owner = task
            try:
                await self.connection.execute("BEGIN IMMEDIATE")
                yield self.connection
            except BaseException:
                await self.connection.rollback()
                raise
            else:
                await self.connection.commit()
            finally:
                self._transaction_owner = None

    async def fetchone(self, sql: str, params: tuple[object, ...] = ()) -> aiosqlite.Row | None:
        rows = await self.fetchall(sql, params)
        return rows[0] if rows else None

    async def fetchval(self, sql: str, params: tuple[object, ...] = ()) -> object | None:
        row = await self.fetchone(sql, params)
        if row is None:
            return None
        return row[0]  # type: ignore[no-any-return]
