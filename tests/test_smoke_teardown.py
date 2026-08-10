from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.smoke.resource_guard import (
    SMOKE_CLIENT_SERVER_PREFIXES,
    is_smoke_client_server_name,
    is_test_category_name,
    is_test_role_name,
)


@pytest.mark.parametrize("prefix_name", SMOKE_CLIENT_SERVER_PREFIXES)
def test_is_smoke_client_server_name(prefix_name: str) -> None:
    assert is_smoke_client_server_name(f"{prefix_name}abc123")


def test_is_smoke_client_server_name_rejects_production() -> None:
    assert not is_smoke_client_server_name("acme-corp")


def test_is_test_category_name_covers_smoke_prefixes() -> None:
    assert is_test_category_name("Smoke HubSub abc")
    assert is_test_category_name("Smoke Welcome xyz")


def test_is_test_role_name_covers_smoke_hubsub() -> None:
    assert is_test_role_name("Client: Smoke HubSub abc")


@pytest.mark.asyncio
async def test_teardown_smoke_guild_removes_registered_clients() -> None:
    from bot.smoke import teardown as teardown_module
    from bot.smoke.teardown import teardown_smoke_guild

    guild = MagicMock()
    guild.id = 1
    bot_member = MagicMock()

    smoke_client = MagicMock()
    smoke_client.guild_id = 1
    smoke_client.server_name = "Smoke Accept abc"

    real_client = MagicMock()
    real_client.guild_id = 1
    real_client.server_name = "acme"

    context = MagicMock()
    context.client_repo.list_all = AsyncMock(
        return_value=[smoke_client, real_client],
    )
    context.client_cache.load_cache = AsyncMock()
    context.routing_service.load_cache = AsyncMock()

    cleanup_mock = AsyncMock()
    join_cleanup = AsyncMock()
    artifacts = AsyncMock(side_effect=[["emoji:tnprobe_a"], []])
    rebuild = AsyncMock(return_value=[])
    orphan = AsyncMock(return_value=[])

    originals = {
        "cleanup_smoke_client": teardown_module.cleanup_smoke_client,
        "cleanup_join_requests_smoke_artifacts": (
            teardown_module.cleanup_join_requests_smoke_artifacts
        ),
        "cleanup_guild_test_artifacts": teardown_module.cleanup_guild_test_artifacts,
        "cleanup_hub_rebuild_smoke_artifacts": (
            teardown_module.cleanup_hub_rebuild_smoke_artifacts
        ),
        "cleanup_orphan_smoke_subscription_channels": (
            teardown_module.cleanup_orphan_smoke_subscription_channels
        ),
    }
    teardown_module.cleanup_smoke_client = cleanup_mock
    teardown_module.cleanup_join_requests_smoke_artifacts = join_cleanup
    teardown_module.cleanup_guild_test_artifacts = artifacts
    teardown_module.cleanup_hub_rebuild_smoke_artifacts = rebuild
    teardown_module.cleanup_orphan_smoke_subscription_channels = orphan

    try:
        result = await teardown_smoke_guild(guild, context, bot_member)
    finally:
        for key, value in originals.items():
            setattr(teardown_module, key, value)

    cleanup_mock.assert_awaited_once()
    assert cleanup_mock.await_args.kwargs["server_name"] == "Smoke Accept abc"
    assert result.removed_clients == ["Smoke Accept abc"]
    assert "emoji:tnprobe_a" in result.removed_artifacts
