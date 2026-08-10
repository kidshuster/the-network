from __future__ import annotations

import inspect


def test_hub_announcements_smoke_covers_relay_and_write_only_guard() -> None:
    from bot.smoke import hub_announcements_probes

    source = inspect.getsource(hub_announcements_probes.run_hub_announcements_smoke_flow)
    assert "inject_hub_announcement" in source
    assert "relay_service.relay_message" in source
    assert "hub_subscribe" in source.lower() or "hub subscribe" in source.lower()


def test_smoke_hub_announcements_script_exists() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "bin" / "smoke_hub_announcements.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
