from __future__ import annotations

import pytest

from tests.core import pacing


def test_delay_seconds_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SMOKE_STEP_DELAY_SEC", raising=False)
    assert pacing._delay_seconds("SMOKE_STEP_DELAY_SEC", 2.0) == 2.0


def test_delay_seconds_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_STEP_DELAY_SEC", "12.5")
    assert pacing._delay_seconds("SMOKE_STEP_DELAY_SEC", 2.0) == 12.5


def test_delay_seconds_clamps_negative_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_ROLE_CREATE_DELAY_SEC", "-1")
    assert pacing._delay_seconds("SMOKE_ROLE_CREATE_DELAY_SEC", 0.5) == 0.0
