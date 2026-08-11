from __future__ import annotations

from tests.live.probes import PROBES
from tests.live.recipes import load_recipes


def test_standard_live_suite_includes_hub_announcement_flow() -> None:
    assert "relay.hub_announcement" in PROBES
    assert any(
        step.probe == "relay.hub_announcement"
        for step in load_recipes()["full"].steps
    )
