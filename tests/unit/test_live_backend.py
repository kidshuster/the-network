from __future__ import annotations

from typing import Any

import pytest

from tests.live.live_backend import phase_delay_seconds, run_live_probe
from tests.live.probes import ProbeOutcome


def test_phase_delay_uses_default_for_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SMOKE_PHASE_DELAY_SEC", "invalid")
    assert phase_delay_seconds() == 2.0


def test_phase_delay_clamps_negative_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_PHASE_DELAY_SEC", "-4")
    assert phase_delay_seconds() == 0.0


@pytest.mark.asyncio
async def test_live_backend_owns_requested_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def probe(_context: Any) -> ProbeOutcome:
        return ProbeOutcome("probe", "ok")

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("tests.live.live_backend.get_probe", lambda _name: probe)
    monkeypatch.setattr("tests.live.live_backend.phase_delay_seconds", lambda: 3.5)
    monkeypatch.setattr("tests.live.live_backend.asyncio.sleep", sleep)
    outcome = await run_live_probe("probe", object(), pause_after=True)  # type: ignore[arg-type]
    assert outcome.detail == "ok"
    assert sleeps == [3.5]


@pytest.mark.asyncio
async def test_live_backend_skips_unrequested_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def probe(_context: Any) -> ProbeOutcome:
        return ProbeOutcome("probe", "ok")

    async def unexpected_sleep(_delay: float) -> None:
        raise AssertionError("sleep should not be called")

    monkeypatch.setattr("tests.live.live_backend.get_probe", lambda _name: probe)
    monkeypatch.setattr("tests.live.live_backend.asyncio.sleep", unexpected_sleep)
    await run_live_probe("probe", object(), pause_after=False)  # type: ignore[arg-type]
