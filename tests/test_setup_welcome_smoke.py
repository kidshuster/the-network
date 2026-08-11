from __future__ import annotations

from pathlib import Path


def test_setup_welcome_smoke_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "bin" / "smoke_setup_welcome.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
