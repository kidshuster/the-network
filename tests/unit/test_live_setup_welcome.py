from __future__ import annotations

from tests.core.probes import PROBES
from tests.core.recipes import load_recipes


def test_standard_live_suite_includes_setup_welcome_flow() -> None:
    assert "relay.setup_welcome" in PROBES
    assert any(
        step.probe == "relay.setup_welcome"
        for step in load_recipes()["full"].steps
    )
