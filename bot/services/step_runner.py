from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import discord

logger = logging.getLogger(__name__)

_DEFAULT_STEP_TIMEOUT_SECONDS = 45.0


class StepResult(Protocol):
    failed_steps: list[str]
    notes: list[str]


async def run_guild_step[T](
    result: StepResult,
    step: str,
    action: Callable[[], Awaitable[T]],
    *,
    timeout: float = _DEFAULT_STEP_TIMEOUT_SECONDS,
    fallback: T | None = None,
) -> T | None:
    try:
        return await asyncio.wait_for(action(), timeout=timeout)
    except TimeoutError:
        message = f"{step}: timed out after {timeout:.0f}s"
        result.failed_steps.append(message)
        result.notes.append(f"Could not {step}: timed out")
        logger.warning("Guild step timed out", extra={"step": step})
        return fallback
    except discord.HTTPException as exc:
        message = f"{step}: {exc}"
        result.failed_steps.append(message)
        result.notes.append(f"Could not {step}: {exc}")
        logger.warning("Guild step failed", extra={"step": step, "error": str(exc)})
        return fallback
