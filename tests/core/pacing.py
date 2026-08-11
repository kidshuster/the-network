from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _delay_seconds(env_var: str, default: float) -> float:
    raw = os.environ.get(env_var)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning(
            "Invalid smoke delay env var; using default",
            extra={"env_var": env_var, "raw": raw, "default": default},
        )
        return default


# Pause between operator and provision probes (each creates roles).
PROBE_PHASE_DELAY_SEC = _delay_seconds("SMOKE_PROBE_PHASE_DELAY_SEC", 2.0)

# Pause immediately before guild.create_role (shared rate-limit bucket).
ROLE_CREATE_DELAY_SEC = _delay_seconds("SMOKE_ROLE_CREATE_DELAY_SEC", 1.5)

# Optional pacing for standalone live scripts and destructive stress probes.
STEP_DELAY_SEC = _delay_seconds("SMOKE_STEP_DELAY_SEC", 8.0)

# Extra pause when pre-init probes run twice in a row (probe-only then full E2E).
DUPLICATE_PROBE_DELAY_SEC = _delay_seconds("SMOKE_DUPLICATE_PROBE_DELAY_SEC", 15.0)


async def pause_between_probe_phases() -> None:
    if PROBE_PHASE_DELAY_SEC <= 0:
        return
    await asyncio.sleep(PROBE_PHASE_DELAY_SEC)


async def pause_before_role_create() -> None:
    if ROLE_CREATE_DELAY_SEC <= 0:
        return
    await asyncio.sleep(ROLE_CREATE_DELAY_SEC)
