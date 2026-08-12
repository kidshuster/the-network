from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import discord

from bot.config import Settings
from tests.core.client_guard import snapshot_protected_clients
from tests.core.live_backend import phase_delay_seconds
from tests.core.mock_backend import load_mock_context
from tests.core.probes import LiveContext, ProbeOutcome
from tests.core.recipes import RecipeRunner, load_recipes
from tests.core.run_logging import SmokeRunLogger, make_run_log_path
from tests.core.scheduler import DiscordTestScheduler, SmokeMetrics

Backend = Literal["live", "mock"]


@dataclass(frozen=True)
class SmokeRunResult:
    success: bool
    run_id: str
    recipe_name: str
    scenario: str
    backend: Backend
    outcomes: tuple[ProbeOutcome, ...]
    metrics: SmokeMetrics
    log_path: Path | None = None
    error: str | None = None


async def run_smoke_recipe(
    *,
    recipe_name: str,
    scenario: str = "healthy",
    backend: Backend = "live",
    bot: Any | None = None,
    guild: discord.Guild | None = None,
    context: LiveContext | Any | None = None,
    run_id: str | None = None,
    log_dir: Path | None = None,
    run_logger: SmokeRunLogger | None = None,
    cancel_event: asyncio.Event | None = None,
    on_progress: Any | None = None,
    close_database: bool = False,
    max_rate_limit_wait_seconds: float = 300.0,
) -> SmokeRunResult:
    """Shared smoke entry used by CLI and in-process `/server test`."""
    recipes = load_recipes()
    if recipe_name not in recipes:
        raise KeyError(f"Unknown smoke recipe {recipe_name!r}")

    resolved_run_id = run_id or "local"
    owned_logger = run_logger
    log_path: Path | None = None
    if owned_logger is None and log_dir is not None:
        log_path = make_run_log_path(log_dir, recipe_name, resolved_run_id)
        owned_logger = SmokeRunLogger(log_path)
    elif owned_logger is not None:
        log_path = owned_logger.path

    cancel = cancel_event or asyncio.Event()
    scheduler = DiscordTestScheduler(
        cancel_event=cancel,
        max_rate_limit_wait_seconds=max_rate_limit_wait_seconds,
        phase_delay_seconds=phase_delay_seconds(),
    )

    if owned_logger is not None:
        owned_logger.write(
            f"run_id={resolved_run_id} recipe={recipe_name} scenario={scenario} "
            f"backend={backend}"
        )

    database_to_close = None
    run_context: LiveContext | Any
    try:
        if backend == "mock":
            run_context = load_mock_context(scenario)
        elif context is not None:
            run_context = context
        else:
            if bot is None or guild is None:
                raise ValueError("live backend requires bot+guild or an explicit context")
            if guild.me is None:
                raise RuntimeError("Bot member is unavailable in the target guild.")
            runtime = getattr(bot, "bot_context", None)
            if runtime is None:
                raise RuntimeError("Bot context is not ready.")
            settings = getattr(bot, "settings", None)
            if not isinstance(settings, Settings):
                settings = Settings()
            run_context = LiveContext(
                guild=guild,
                bot_member=guild.me,
                bot=cast(Any, bot),
                settings=settings,
                database=bot.db,
                runtime=runtime,
                protected_clients=await snapshot_protected_clients(runtime, guild.id),
            )

        runner = RecipeRunner(
            run_context,
            recipes,
            backend=backend,
            scheduler=scheduler,
            cancel_event=cancel,
            run_logger=owned_logger,
            on_progress=on_progress,
        )
        outcomes = await runner.run(recipe_name)
        if owned_logger is not None:
            owned_logger.write(
                "SUMMARY success=true "
                f"mutations={scheduler.metrics.mutations} "
                f"rest_reads={scheduler.metrics.rest_reads} "
                f"rate_limit_wait={scheduler.metrics.rate_limit_wait_seconds:.1f}s "
                f"duration={scheduler.metrics.duration_seconds:.1f}s"
            )
        return SmokeRunResult(
            success=True,
            run_id=resolved_run_id,
            recipe_name=recipe_name,
            scenario=scenario,
            backend=backend,
            outcomes=tuple(outcomes),
            metrics=scheduler.metrics,
            log_path=log_path,
        )
    except BaseException as exc:
        if owned_logger is not None:
            owned_logger.write(f"ERROR: {exc}")
            owned_logger.write(
                "SUMMARY success=false "
                f"mutations={scheduler.metrics.mutations} "
                f"duration={scheduler.metrics.duration_seconds:.1f}s"
            )
        return SmokeRunResult(
            success=False,
            run_id=resolved_run_id,
            recipe_name=recipe_name,
            scenario=scenario,
            backend=backend,
            outcomes=(),
            metrics=scheduler.metrics,
            log_path=log_path,
            error=str(exc),
        )
    finally:
        if close_database and database_to_close is not None:
            await database_to_close.close()
        if owned_logger is not None and run_logger is None:
            owned_logger.close()
