from __future__ import annotations

import inspect


def test_join_approval_smoke_verifies_leaders_access_after_accept() -> None:
    """Live join-approval smoke must assert Leaders access right after Accept."""
    from bot.smoke.provision_flow import run_join_approval_smoke_flow

    source = inspect.getsource(run_join_approval_smoke_flow)
    assert "_collect_leaders_access_gaps" in source
    assert "Leaders access sync reported issues" in source
