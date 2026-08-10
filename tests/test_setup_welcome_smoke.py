from __future__ import annotations

import inspect


def test_setup_welcome_smoke_checks_sticky_copy_and_welcome_rules() -> None:
    from bot.smoke import setup_welcome_probes

    flow_source = inspect.getsource(setup_welcome_probes.run_setup_welcome_smoke_flow)
    assert "verify_setup_sticky_copy" in flow_source
    assert "add_blacklist" in flow_source
    assert "expected_incumbent_member_welcomes=0" in flow_source
    assert "expected_incumbent_member_welcomes=1" in flow_source
    assert "server connected" in inspect.getsource(setup_welcome_probes)


def test_setup_welcome_smoke_script_exists() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "bin" / "smoke_setup_welcome.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
