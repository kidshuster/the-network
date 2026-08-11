from __future__ import annotations

import asyncio
import os

from tests.core.probes import LiveContext, ProbeOutcome, get_probe


def phase_delay_seconds() -> float:
    raw = os.getenv("SMOKE_PHASE_DELAY_SEC", "2")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 2.0


async def run_live_probe(
    name: str,
    context: LiveContext,
    *,
    pause_after: bool = False,
) -> ProbeOutcome:
    """Execute one real Discord probe and apply live-only API pacing."""
    outcome = await get_probe(name)(context)
    if pause_after:
        delay = phase_delay_seconds()
        if delay:
            await asyncio.sleep(delay)
    return outcome

