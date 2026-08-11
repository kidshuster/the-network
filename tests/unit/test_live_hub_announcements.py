from __future__ import annotations

from pathlib import Path


def test_standard_live_suite_includes_hub_announcement_flow() -> None:
    suite = Path(__file__).resolve().parents[1] / "live" / "suite.py"
    assert "run_hub_announcements_smoke_flow" in suite.read_text(encoding="utf-8")
