from __future__ import annotations

from discord_helpers import http_50013

from tests.live.permission_probe import (
    _probe_failure_detail,
    _probe_failure_for_step,
    _provision_probe_failure,
)


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


def test_provision_probe_failure_includes_50013_guidance() -> None:
    error = _provision_probe_failure(
        "create network-profile channel",
        ["create client role", "create client category with hub overwrites"],
        http_50013(),
    )
    message = str(error)
    assert "50013" in message
    assert "create network-profile channel" in message
    assert "Completed before failure" in message
    assert "The Network+" in message


def test_probe_failure_detail_for_http_exception() -> None:
    failure, guidance = _probe_failure_detail(http_50013())
    assert "Missing Permissions" in failure
    assert "50013" in failure
    assert "The Network+" in guidance


def test_probe_failure_for_step_lists_completed_steps() -> None:
    from bot.core.models.errors import NetworkValidationError

    error = _probe_failure_for_step(
        "create text channel",
        ["create category"],
        http_50013(),
    )
    assert isinstance(error, NetworkValidationError)
    message = str(error)
    assert "create category" in message
    assert "Permission probe failed" in message
