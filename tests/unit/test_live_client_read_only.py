from __future__ import annotations

from tests.core.probes import PROBES
from tests.core.recipes import load_recipes


def test_standard_live_suite_includes_client_read_only_flow() -> None:
    assert "client.read_only" in PROBES
    assert any(
        step.probe == "client.read_only"
        for step in load_recipes()["full"].steps
    )


def test_smoke_readonly_prefix_is_recognized() -> None:
    from tests.core.resource_guard import is_smoke_client_server_name, is_test_category_name

    assert is_smoke_client_server_name("Smoke Readonly abc")
    assert is_test_category_name("Smoke Readonly abc")
