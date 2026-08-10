from __future__ import annotations

from bot.services.permission_probe import _provision_probe_failure


def test_provision_probe_failure_explains_sync_permissions_typeerror() -> None:
    exc = TypeError(
        "Guild.create_text_channel() got an unexpected keyword argument 'sync_permissions'"
    )
    error = _provision_probe_failure(
        "create network-profile channel",
        ["create client role"],
        exc,
    )

    message = str(error)
    assert "not** a Discord permissions issue" in message or "not a Discord permissions" in message
    assert "1.2.9" in message
    assert "git pull" in message
    assert "Fix **The Network+** permissions" not in message
