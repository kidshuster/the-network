from __future__ import annotations

from pathlib import Path


def test_smoke_hub_announcements_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "bin" / "smoke_hub_announcements.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
