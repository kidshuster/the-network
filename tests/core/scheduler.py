from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")

_ACTIVE: ContextVar[DiscordTestScheduler | None] = ContextVar(
    "discord_test_scheduler",
    default=None,
)


@dataclass
class SmokeMetrics:
    mutations: int = 0
    rest_reads: int = 0
    cache_reads: int = 0
    rate_limit_events: int = 0
    rate_limit_wait_seconds: float = 0.0
    phase_checkpoints: int = 0
    started_at: float = field(default_factory=time.monotonic)
    budget_exceeded_at: str | None = None

    @property
    def duration_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)


@dataclass(frozen=True)
class SmokeBudgets:
    max_mutations: int | None = None
    max_rest_reads: int | None = None
    max_rate_limit_wait_seconds: float | None = None
    max_duration_seconds: float | None = None


class BudgetExceededError(RuntimeError):
    def __init__(self, message: str, *, phase: str) -> None:
        super().__init__(message)
        self.phase = phase


class DiscordTestScheduler:
    """Serialize and pace Discord test operations for one smoke run."""

    def __init__(
        self,
        *,
        budgets: SmokeBudgets | None = None,
        cancel_event: asyncio.Event | None = None,
        max_rate_limit_wait_seconds: float = 300.0,
        phase_delay_seconds: float = 0.5,
    ) -> None:
        self.budgets = budgets or SmokeBudgets()
        self.cancel_event = cancel_event or asyncio.Event()
        self.max_rate_limit_wait_seconds = max_rate_limit_wait_seconds
        self.phase_delay_seconds = max(0.0, phase_delay_seconds)
        self.metrics = SmokeMetrics()
        self._mutate_lock = asyncio.Lock()
        self._discovery_cache: dict[str, object] = {}

    def activate(self) -> None:
        _ACTIVE.set(self)

    def deactivate(self) -> None:
        _ACTIVE.set(None)

    async def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise asyncio.CancelledError("Smoke run cancelled")

    def _check_budgets(self, *, phase: str) -> None:
        budgets = self.budgets
        metrics = self.metrics
        if (
            budgets.max_mutations is not None
            and metrics.mutations > budgets.max_mutations
        ):
            metrics.budget_exceeded_at = phase
            raise BudgetExceededError(
                f"Mutation budget exceeded ({metrics.mutations}/{budgets.max_mutations})",
                phase=phase,
            )
        if (
            budgets.max_rest_reads is not None
            and metrics.rest_reads > budgets.max_rest_reads
        ):
            metrics.budget_exceeded_at = phase
            raise BudgetExceededError(
                f"REST read budget exceeded ({metrics.rest_reads}/{budgets.max_rest_reads})",
                phase=phase,
            )
        if (
            budgets.max_rate_limit_wait_seconds is not None
            and metrics.rate_limit_wait_seconds > budgets.max_rate_limit_wait_seconds
        ):
            metrics.budget_exceeded_at = phase
            raise BudgetExceededError(
                "Rate-limit wait budget exceeded "
                f"({metrics.rate_limit_wait_seconds:.1f}/"
                f"{budgets.max_rate_limit_wait_seconds})",
                phase=phase,
            )
        if (
            budgets.max_duration_seconds is not None
            and metrics.duration_seconds > budgets.max_duration_seconds
        ):
            metrics.budget_exceeded_at = phase
            raise BudgetExceededError(
                f"Duration budget exceeded ({metrics.duration_seconds:.1f}s/"
                f"{budgets.max_duration_seconds})",
                phase=phase,
            )
        if metrics.rate_limit_wait_seconds > self.max_rate_limit_wait_seconds:
            metrics.budget_exceeded_at = phase
            raise BudgetExceededError(
                "Cumulative rate-limit wait exceeded configured threshold "
                f"({metrics.rate_limit_wait_seconds:.1f}/"
                f"{self.max_rate_limit_wait_seconds})",
                phase=phase,
            )

    async def checkpoint(self, phase: str) -> None:
        await self._check_cancel()
        self._check_budgets(phase=phase)
        if self.phase_delay_seconds > 0:
            await asyncio.sleep(self.phase_delay_seconds)
            self.metrics.phase_checkpoints += 1
        self._check_budgets(phase=phase)

    async def record_rate_limit_wait(self, seconds: float, *, phase: str) -> None:
        wait = max(0.0, float(seconds))
        if wait <= 0:
            return
        self.metrics.rate_limit_events += 1
        self.metrics.rate_limit_wait_seconds += wait
        await asyncio.sleep(wait)
        self._check_budgets(phase=phase)

    async def mutate(self, phase: str, action: Callable[[], Awaitable[T]]) -> T:
        async with self._mutate_lock:
            await self._check_cancel()
            self.metrics.mutations += 1
            self._check_budgets(phase=phase)
            return await action()

    async def read(
        self,
        key: str,
        action: Callable[[], Awaitable[T]],
        *,
        use_cache: bool = True,
    ) -> T:
        await self._check_cancel()
        if use_cache and key in self._discovery_cache:
            self.metrics.cache_reads += 1
            return self._discovery_cache[key]  # type: ignore[return-value]
        self.metrics.rest_reads += 1
        self._check_budgets(phase=f"read:{key}")
        value = await action()
        if use_cache:
            self._discovery_cache[key] = value
        return value


def get_active_scheduler() -> DiscordTestScheduler | None:
    return _ACTIVE.get()
