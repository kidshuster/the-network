from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from tests.core.constants import (
    SERVER_INIT_PROBE_REASON,
    SMOKE_CLEANUP_REASON,
    TEST_CLEANUP_REASON,
)
from tests.core.resource_guard import (
    cleanup_guild_test_artifacts,
    guild_test_resource_guard,
    is_test_category_name,
    is_test_channel_name,
    is_test_role_name,
)


def test_smoke_cleanup_constants() -> None:
    assert TEST_CLEANUP_REASON.startswith("The Network test cleanup")
    assert SMOKE_CLEANUP_REASON.startswith("The Network smoke cleanup")
    assert SERVER_INIT_PROBE_REASON.startswith("The Network server-init live probe")


def test_name_matchers() -> None:
    assert is_test_channel_name("network-perm-probe-ch-dead")
    assert is_test_channel_name("diag8-ch-dead")
    assert is_test_channel_name("smoke-wh-ab12")
    assert not is_test_channel_name("rules")

    assert is_test_category_name("network-perm-probe-client-cat-dead")
    assert is_test_category_name("diag10-cat-dead")
    assert is_test_category_name("Smoke Accept abc123")
    assert not is_test_category_name("The Network")

    assert is_test_role_name("network-perm-probe-client-dead")
    assert is_test_role_name("diag8-d9198e")
    assert is_test_role_name("Client: Smoke Accept abc")
    assert is_test_role_name("Client: Smoke Deny abc")
    assert is_test_role_name("Client: Smoke Rebuild abc")
    assert not is_test_role_name("The Network+")


@pytest.mark.asyncio
async def test_guild_test_resource_guard_cleans_tracked_resources() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []

    bot = MagicMock(spec=discord.Member, id=999, roles=[])

    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "network-perm-probe-client-cat-dead"
    category.channels = []
    category.delete = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "network-perm-probe-profile-dead"
    channel.delete = AsyncMock()

    role = MagicMock(spec=discord.Role)
    role.name = "network-perm-probe-client-dead"
    role.delete = AsyncMock()

    bot.roles = []
    bot.remove_roles = AsyncMock()

    webhook = MagicMock(spec=discord.Webhook)
    webhook.delete = AsyncMock()

    emoji = MagicMock(spec=discord.Emoji)
    emoji.name = "tnprobedead"
    emoji.delete = AsyncMock()

    async with guild_test_resource_guard(guild, bot_member=bot) as guard:
        guard.track_category(category)
        guard.track_channel(channel)
        guard.track_role(role)
        guard.track_webhook(webhook)
        guard.track_emoji(emoji)
        guard.track_role_assignment(role)
        bot.roles = [role]

    bot.remove_roles.assert_awaited_once()
    webhook.delete.assert_awaited_once()
    channel.delete.assert_awaited_once()
    category.delete.assert_awaited_once()
    role.delete.assert_awaited_once()
    emoji.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_guild_test_resource_guard_cleans_up_after_failure() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []

    category = MagicMock(spec=discord.CategoryChannel)
    category.name = "network-perm-probe-cat-dead"
    category.channels = []
    category.delete = AsyncMock()

    with pytest.raises(RuntimeError, match="boom"):
        async with guild_test_resource_guard(guild) as guard:
            guard.track_category(category)
            raise RuntimeError("boom")

    category.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_guild_test_resource_guard_does_not_sweep_guild_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    sweep = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "tests.core.resource_guard.cleanup_guild_test_artifacts",
        sweep,
    )

    async with guild_test_resource_guard(guild):
        pass

    sweep.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_guild_test_artifacts_removes_categories_and_channels() -> None:
    guild = MagicMock(spec=discord.Guild)

    stale_channel = MagicMock(spec=discord.TextChannel)
    stale_channel.name = "network-perm-probe-ch-dead"
    stale_channel.delete = AsyncMock()

    stale_category = MagicMock(spec=discord.CategoryChannel)
    stale_category.name = "diag-cat-dead"
    inner_channel = MagicMock(spec=discord.TextChannel)
    inner_channel.name = "network-profile"
    inner_channel.delete = AsyncMock()
    stale_category.channels = [inner_channel]
    stale_category.delete = AsyncMock()

    other_channel = MagicMock(spec=discord.TextChannel)
    other_channel.name = "rules"

    stale_role = MagicMock(spec=discord.Role)
    stale_role.name = "network-perm-probe-role-dead"
    stale_role.delete = AsyncMock()

    stale_emoji = MagicMock(spec=discord.Emoji)
    stale_emoji.name = "tnprobedead"
    stale_emoji.delete = AsyncMock()

    guild.channels = [stale_channel, stale_category, other_channel]
    guild.roles = [stale_role]
    guild.emojis = [stale_emoji]

    removed = await cleanup_guild_test_artifacts(guild)

    assert "channel:network-perm-probe-ch-dead" in removed
    assert "category:diag-cat-dead" in removed
    assert "channel:network-profile" in removed
    assert "role:network-perm-probe-role-dead" in removed
    assert "emoji:tnprobedead" in removed
    stale_channel.delete.assert_awaited_once()
    inner_channel.delete.assert_awaited_once()
    stale_category.delete.assert_awaited_once()
    stale_role.delete.assert_awaited_once()
    stale_emoji.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_orphan_smoke_subscription_channels() -> None:
    from tests.core.resource_guard import cleanup_orphan_smoke_subscription_channels

    orphan_publish = MagicMock(spec=discord.TextChannel)
    orphan_publish.category = None
    orphan_publish.name = "smoke-rebuild-abc-stingers-publish"
    orphan_publish.id = 1001
    orphan_publish.delete = AsyncMock()

    orphan_subscribe = MagicMock()
    orphan_subscribe.category = None
    orphan_subscribe.name = "smoke-rebuild-abc-stingers-subscribe"
    orphan_subscribe.id = 1002
    orphan_subscribe.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), {}))

    live_publish = MagicMock(spec=discord.TextChannel)
    live_publish.category = None
    live_publish.name = "live-publish"
    live_publish.id = 2001
    live_publish.delete = AsyncMock()

    unrelated_orphan = MagicMock(spec=discord.TextChannel)
    unrelated_orphan.category = None
    unrelated_orphan.name = "partner-stingers-publish"
    unrelated_orphan.id = 2003
    unrelated_orphan.delete = AsyncMock()

    guild = MagicMock(spec=discord.Guild)
    guild.channels = [orphan_publish, orphan_subscribe, live_publish, unrelated_orphan]

    context = MagicMock()
    client = MagicMock()
    client.profile_channel_id = 3001
    context.store.clients.list_all = AsyncMock(return_value=[client])
    context.store.clients.list_subscriptions_by_client = AsyncMock(
        return_value=[MagicMock(publish_channel_id=2001, subscribe_channel_id=2002)],
    )

    manual = await cleanup_orphan_smoke_subscription_channels(guild, context)

    orphan_publish.delete.assert_awaited_once()
    orphan_subscribe.delete.assert_awaited_once()
    live_publish.delete.assert_not_called()
    unrelated_orphan.delete.assert_not_called()
    assert manual == ["#smoke-rebuild-abc-stingers-subscribe (1002)"]
