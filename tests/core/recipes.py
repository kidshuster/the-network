from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from tests.core.client_guard import assert_protected_clients_unchanged
from tests.core.live_backend import run_live_probe
from tests.core.mock_backend import MockContext, run_mock_probe
from tests.core.probes import LiveContext, ProbeOutcome
from tests.core.scheduler import (
    BudgetExceededError,
    DiscordTestScheduler,
    SmokeBudgets,
    SmokeMetrics,
)

RECIPE_DIR = Path(__file__).resolve().parents[1] / "recipes"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecipeStep:
    probe: str | None = None
    recipe: str | None = None
    pause: bool = False
    protect_clients: bool = True


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    steps: tuple[RecipeStep, ...]
    finally_steps: tuple[RecipeStep, ...] = ()
    budgets: SmokeBudgets = SmokeBudgets()


def _step(raw: Any, *, source: Path) -> RecipeStep:
    if isinstance(raw, str):
        return RecipeStep(probe=raw)
    if not isinstance(raw, dict):
        raise ValueError(f"{source}: recipe step must be a string or mapping")
    probe = raw.get("probe")
    recipe = raw.get("recipe")
    if (probe is None) == (recipe is None):
        raise ValueError(f"{source}: step must define exactly one of probe or recipe")
    return RecipeStep(
        probe=str(probe) if probe is not None else None,
        recipe=str(recipe) if recipe is not None else None,
        pause=bool(raw.get("pause", False)),
        protect_clients=bool(raw.get("protect_clients", True)),
    )


def _budgets(raw: Any) -> SmokeBudgets:
    if not isinstance(raw, dict):
        return SmokeBudgets()
    return SmokeBudgets(
        max_mutations=_optional_int(raw.get("max_mutations")),
        max_rest_reads=_optional_int(raw.get("max_rest_reads")),
        max_rate_limit_wait_seconds=_optional_float(raw.get("max_rate_limit_wait_seconds")),
        max_duration_seconds=_optional_float(raw.get("max_duration_seconds")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def load_recipes(directory: Path = RECIPE_DIR) -> dict[str, Recipe]:
    recipes: dict[str, Recipe] = {}
    for path in sorted(directory.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: root must be a mapping")
        name = str(payload.get("name", path.stem))
        if name in recipes:
            raise ValueError(f"Duplicate live recipe {name!r}")
        recipes[name] = Recipe(
            name=name,
            description=str(payload.get("description", "")),
            steps=tuple(_step(raw, source=path) for raw in payload.get("steps", [])),
            finally_steps=tuple(
                _step(raw, source=path) for raw in payload.get("finally", [])
            ),
            budgets=_budgets(payload.get("budgets")),
        )
    return recipes


Backend = Literal["live", "mock"]
ProgressCallback = Callable[[str, SmokeMetrics], Any]
PROGRESS_HEARTBEAT_SECONDS = 5.0


class RecipeRunner:
    def __init__(
        self,
        context: LiveContext | MockContext,
        recipes: dict[str, Recipe],
        *,
        backend: Backend = "live",
        scheduler: DiscordTestScheduler | None = None,
        cancel_event: asyncio.Event | None = None,
        run_logger: Any | None = None,
        on_progress: ProgressCallback | None = None,
        progress_heartbeat_seconds: float = PROGRESS_HEARTBEAT_SECONDS,
    ) -> None:
        self.context = context
        self.recipes = recipes
        self.backend = backend
        self.scheduler = scheduler
        self.cancel_event = cancel_event
        self.run_logger = run_logger
        self.on_progress = on_progress
        self.progress_heartbeat_seconds = max(0.0, progress_heartbeat_seconds)
        self.outcomes: list[ProbeOutcome] = []
        self.budget_error: BudgetExceededError | None = None

    def _log(self, message: str) -> None:
        print(message, flush=True)
        if self.run_logger is not None:
            self.run_logger.write(message)

    def _metrics(self) -> SmokeMetrics:
        if self.scheduler is not None:
            return self.scheduler.metrics
        return SmokeMetrics()

    async def _emit_progress(self, phase: str) -> None:
        if self.on_progress is None:
            return
        maybe = self.on_progress(phase, self._metrics())
        if asyncio.iscoroutine(maybe):
            await maybe

    async def run(self, name: str) -> list[ProbeOutcome]:
        if self.scheduler is not None:
            self.scheduler.activate()
        try:
            await self._run_recipe(name, stack=())
        finally:
            if self.scheduler is not None:
                self.scheduler.deactivate()
        return list(self.outcomes)

    async def run_probe(self, name: str) -> ProbeOutcome:
        return await self._run_probe(name, protect_clients=True, pause=False)

    async def _run_recipe(self, name: str, *, stack: tuple[str, ...]) -> None:
        if name in stack:
            raise ValueError("Live recipe cycle: " + " -> ".join((*stack, name)))
        try:
            recipe = self.recipes[name]
        except KeyError as exc:
            raise KeyError(f"Unknown live recipe {name!r}") from exc
        if self.scheduler is not None and not stack:
            # Apply top-level budgets once.
            self.scheduler.budgets = recipe.budgets
        self._log(f"\n==> {recipe.name}: {recipe.description}")
        try:
            for step in recipe.steps:
                await self._run_step(step, stack=(*stack, name))
        except BudgetExceededError as exc:
            self.budget_error = exc
            self._log(f"BUDGET: {exc} at {exc.phase}")
            raise
        finally:
            for step in recipe.finally_steps:
                try:
                    await self._run_step(step, stack=(*stack, name))
                except Exception:
                    logger.exception("Recipe finally step failed", extra={"recipe": name})
                    self._log(f"FINALLY FAILED for step in {name}")

    async def _run_step(self, step: RecipeStep, *, stack: tuple[str, ...]) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise asyncio.CancelledError("Smoke run cancelled")
        if step.recipe is not None:
            await self._run_recipe(step.recipe, stack=stack)
            return
        assert step.probe is not None
        await self._run_probe(
            step.probe,
            protect_clients=step.protect_clients,
            pause=step.pause,
        )

    async def _run_probe(
        self, name: str, *, protect_clients: bool, pause: bool
    ) -> ProbeOutcome:
        self._log(f"  START {name}")
        await self._emit_progress(f"start:{name}")

        async def _heartbeat() -> None:
            if self.progress_heartbeat_seconds <= 0:
                return
            while True:
                await asyncio.sleep(self.progress_heartbeat_seconds)
                self._log(f"  RUNNING {name}")
                await self._emit_progress(f"running:{name}")

        heartbeat = asyncio.create_task(_heartbeat(), name=f"smoke-heartbeat:{name}")
        try:
            if self.backend == "mock":
                if not isinstance(self.context, MockContext):
                    raise TypeError("mock backend requires MockContext")
                outcome = await run_mock_probe(name, self.context, pause_after=pause)
            else:
                if not isinstance(self.context, LiveContext):
                    raise TypeError("live backend requires LiveContext")
                outcome = await run_live_probe(
                    name,
                    self.context,
                    pause_after=pause,
                    scheduler=self.scheduler,
                )
        except BaseException:
            self._log(f"  FAIL {name}")
            await self._emit_progress(f"fail:{name}")
            raise
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

        self.outcomes.append(outcome)
        self._log(f"  OK   {name}: {outcome.detail}")
        await self._emit_progress(f"ok:{name}")
        if (
            self.backend == "live"
            and protect_clients
            and name not in {"clients.protected", "artifacts.teardown"}
        ):
            assert isinstance(self.context, LiveContext)
            await assert_protected_clients_unchanged(
                self.context.guild,
                self.context.runtime,
                self.context.protected_clients,
                phase=name,
            )
        return outcome
