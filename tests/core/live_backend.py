from __future__ import annotations

import asyncio
import os

from tests.core.probes import LiveContext, ProbeOutcome, get_probe
from tests.core.scheduler import DiscordTestScheduler, get_active_scheduler


def phase_delay_seconds() -> float:
    raw = os.getenv("SMOKE_PHASE_DELAY_SEC", "0.5")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.5


async def run_live_probe(
    name: str,
    context: LiveContext,
    *,
    pause_after: bool = False,
    scheduler: DiscordTestScheduler | None = None,
) -> ProbeOutcome:
    """Execute one real Discord probe and apply live-only API pacing."""
    active = scheduler or get_active_scheduler()
    outcome = await get_probe(name)(context)
    if pause_after:
        if active is not None:
            await active.checkpoint(f"after:{name}")
        else:
            delay = phase_delay_seconds()
            if delay:
                await asyncio.sleep(delay)
    return outcome
