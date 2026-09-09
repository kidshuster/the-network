from __future__ import annotations

from tests.core.probes import PROBES
from tests.core.recipes import load_recipes


def test_standard_live_suite_includes_hub_follow_reject() -> None:
    assert "publish.hub_follow_reject" in PROBES
    assert any(
        step.probe == "publish.hub_follow_reject"
        for step in load_recipes()["full"].steps
    )
