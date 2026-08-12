from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class SmokeRunInfo:
    run_id: str
    recipe_name: str
    scenario: str
    guild_id: int
    requester_id: int
    started_at: datetime
    log_path: Path
    cancel_event: asyncio.Event


class SmokeRunCoordinator:
    """Single in-process smoke run lock — not a general job queue."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.active_run: SmokeRunInfo | None = None

    async def begin(
        self,
        *,
        recipe_name: str,
        scenario: str,
        guild_id: int,
        requester_id: int,
        log_path: Path,
    ) -> SmokeRunInfo | None:
        if self._lock.locked():
            return None
        await self._lock.acquire()
        if self.active_run is not None:
            self._lock.release()
            return None
        info = SmokeRunInfo(
            run_id=secrets.token_hex(4),
            recipe_name=recipe_name,
            scenario=scenario,
            guild_id=guild_id,
            requester_id=requester_id,
            started_at=datetime.now(tz=UTC),
            log_path=log_path,
            cancel_event=asyncio.Event(),
        )
        self.active_run = info
        return info

    def end(self, run_id: str) -> None:
        active = self.active_run
        if active is not None and active.run_id == run_id:
            self.active_run = None
        if self._lock.locked():
            self._lock.release()

    def request_cancel(self) -> str | None:
        active = self.active_run
        if active is None:
            return None
        active.cancel_event.set()
        return active.run_id
