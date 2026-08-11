from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest

from bot.core.models.errors import NetworkValidationError
from tests.core.permission_probe import (
    cleanup_stale_probe_resources,
    verify_operator_permissions_live,
    verify_provision_permissions_live,
)


@pytest.mark.asyncio
async def test_verify_operator_permissions_live_runs_probe_and_cleans_up() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    access = MagicMock(spec=discord.Role, name="The Network")
    bot = MagicMock(spec=discord.Member, id=999)

    category = MagicMock(spec=discord.CategoryChannel)
    channel = MagicMock(spec=discord.TextChannel)
    channel.set_permissions = AsyncMock()
    channel.create_webhook = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    channel.send = AsyncMock()
    role = MagicMock(spec=discord.Role)
    role.delete = AsyncMock()
    emoji = MagicMock(spec=discord.Emoji)
    emoji.delete = AsyncMock()
    category.delete = AsyncMock()
    channel.delete = AsyncMock()

    guild.create_category = AsyncMock(return_value=category)
    guild.create_text_channel = AsyncMock(return_value=channel)
    guild.create_role = AsyncMock(return_value=role)
    guild.create_custom_emoji = AsyncMock(return_value=emoji)

    steps = await verify_operator_permissions_live(
        guild,
        bot,
        access,
        operator_role_name="The Network+",
    )

    assert "create category" in steps
    assert "create emoji" in steps
    channel.send.assert_awaited_once_with("The Network permission probe.")
    category.delete.assert_awaited_once()
    channel.delete.assert_awaited_once()
    role.delete.assert_awaited_once()
    emoji.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_operator_permissions_live_cleans_up_after_failure() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    access = MagicMock(spec=discord.Role, name="The Network")
    bot = MagicMock(spec=discord.Member, id=999)

    category = MagicMock(spec=discord.CategoryChannel)
    category.delete = AsyncMock()
    guild.create_category = AsyncMock(return_value=category)
    guild.create_text_channel = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "Missing Permissions")
    )

    with pytest.raises(NetworkValidationError, match="create text channel"):
        await verify_operator_permissions_live(
            guild,
            bot,
            access,
            operator_role_name="The Network+",
        )

    category.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_operator_permissions_live_reports_non_http_failures() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    access = MagicMock(spec=discord.Role, name="The Network")
    bot = MagicMock(spec=discord.Member, id=999)

    category = MagicMock(spec=discord.CategoryChannel)
    channel = MagicMock(spec=discord.TextChannel)
    channel.set_permissions = AsyncMock()
    channel.create_webhook = AsyncMock()
    channel.send = AsyncMock(side_effect=TypeError("bad kwarg"))
    category.delete = AsyncMock()
    channel.delete = AsyncMock()

    guild.create_category = AsyncMock(return_value=category)
    guild.create_text_channel = AsyncMock(return_value=channel)
    guild.create_role = AsyncMock()

    with pytest.raises(NetworkValidationError, match="send message") as exc_info:
        await verify_operator_permissions_live(
            guild,
            bot,
            access,
            operator_role_name="The Network+",
        )

    assert "TypeError" in str(exc_info.value)
    assert "create category" in str(exc_info.value)
    channel.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_stale_probe_resources_removes_leftovers() -> None:
    guild = MagicMock(spec=discord.Guild)

    stale_channel = MagicMock(spec=discord.TextChannel)
    stale_channel.name = "network-perm-probe-ch-dead"
    stale_channel.delete = AsyncMock()
    other_channel = MagicMock(spec=discord.TextChannel)
    other_channel.name = "rules"

    stale_role = MagicMock(spec=discord.Role)
    stale_role.name = "network-perm-probe-role-dead"
    stale_role.delete = AsyncMock()

    stale_emoji = MagicMock(spec=discord.Emoji)
    stale_emoji.name = "tnprobedead"
    stale_emoji.delete = AsyncMock()

    stale_category = MagicMock(spec=discord.CategoryChannel)
    stale_category.name = "network-perm-probe-client-cat-dead"
    stale_category.channels = []
    stale_category.delete = AsyncMock()

    guild.channels = [stale_channel, stale_category, other_channel]
    guild.roles = [stale_role]
    guild.emojis = [stale_emoji]

    removed = await cleanup_stale_probe_resources(guild)

    assert "channel:network-perm-probe-ch-dead" in removed
    assert "category:network-perm-probe-client-cat-dead" in removed
    assert "role:network-perm-probe-role-dead" in removed
    assert "emoji:tnprobedead" in removed
    stale_channel.delete.assert_awaited_once()
    stale_role.delete.assert_awaited_once()
    stale_emoji.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_provision_permissions_live_runs_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    guild.default_role = MagicMock(spec=discord.Role, is_default=lambda: True, position=0)

    access = MagicMock(spec=discord.Role, name="The Network", id=40, position=10)
    access.is_default.return_value = False
    operator = MagicMock(spec=discord.Role, name="The Network+", id=50, position=11)
    operator.is_default.return_value = False
    human_mod = MagicMock(spec=discord.Role, name="Moderator", id=30, position=4)
    human_mod.is_default.return_value = False

    bot = MagicMock(spec=discord.Member, id=999, roles=[access, operator])
    bot.top_role = operator
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.manage_webhooks = True
    type(bot).guild_permissions = PropertyMock(return_value=perms)
    bot.add_roles = AsyncMock()

    async def _add_roles(role: discord.Role, **_kwargs: object) -> None:
        bot.roles = [*bot.roles, role]

    bot.add_roles.side_effect = _add_roles
    bot.remove_roles = AsyncMock()

    category = MagicMock(spec=discord.CategoryChannel)
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    channel.create_webhook = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    publish_channel = MagicMock(spec=discord.TextChannel)
    publish_channel.create_webhook = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    partner_role = MagicMock(spec=discord.Role)
    partner_role.delete = AsyncMock()
    category.delete = AsyncMock()
    channel.delete = AsyncMock()
    publish_channel.delete = AsyncMock()

    guild.create_category = AsyncMock(return_value=category)
    guild.create_role = AsyncMock(return_value=partner_role)
    guild.create_text_channel = AsyncMock(side_effect=[channel, publish_channel])

    monkeypatch.setattr(
        "bot.features.channels.resolve.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.core.networks.roles.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.core.networks.roles.validate_provision_permissions",
        MagicMock(),
    )
    from bot.app.layout.applier import BatchApplyResult, ResourceApplyResult

    batch = BatchApplyResult(
        results=[
            ResourceApplyResult(
                resource_id="client",
                success=True,
                changed=True,
                channel=category,
            ),
            ResourceApplyResult(
                resource_id="profile",
                success=True,
                changed=True,
                channel=channel,
            ),
            ResourceApplyResult(
                resource_id="publish",
                success=True,
                changed=True,
                channel=publish_channel,
            ),
        ]
    )
    monkeypatch.setattr(
        "bot.app.layout.apply_layout",
        AsyncMock(return_value=batch),
    )

    steps = await verify_provision_permissions_live(
        guild,
        bot,
        access,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert "create client role" in steps
    assert "assign client role to member" in steps
    assert any("create webhook on publish channel" in step for step in steps)
    bot.add_roles.assert_awaited_once()
    bot.remove_roles.assert_awaited_once()
    channel.delete.assert_awaited_once()
    publish_channel.delete.assert_awaited_once()
    publish_channel.create_webhook.assert_awaited_once()
    category.delete.assert_awaited_once()
    partner_role.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_provision_permissions_live_fails_at_profile_channel_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from discord_helpers import http_50013

    guild = MagicMock(spec=discord.Guild)
    guild.emojis = []
    guild.roles = []
    guild.channels = []
    guild.default_role = MagicMock(spec=discord.Role, is_default=lambda: True, position=0)

    access = MagicMock(spec=discord.Role, name="The Network", id=40, position=10)
    access.is_default.return_value = False
    operator = MagicMock(spec=discord.Role, name="The Network+", id=50, position=11)
    operator.is_default.return_value = False
    human_mod = MagicMock(spec=discord.Role, name="Moderator", id=30, position=4)
    human_mod.is_default.return_value = False

    bot = MagicMock(spec=discord.Member, id=999, roles=[access, operator])
    bot.top_role = operator
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.manage_webhooks = True
    type(bot).guild_permissions = PropertyMock(return_value=perms)
    bot.add_roles = AsyncMock()
    bot.remove_roles = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.delete = AsyncMock()
    category = MagicMock(spec=discord.CategoryChannel)
    category.delete = AsyncMock()

    guild.create_role = AsyncMock(return_value=client_role)
    guild.create_category = AsyncMock(return_value=category)

    from bot.app.layout.applier import BatchApplyResult, ResourceApplyResult

    monkeypatch.setattr(
        "bot.features.channels.resolve.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.core.networks.roles.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.app.layout.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[
                    ResourceApplyResult(
                        resource_id="client",
                        success=True,
                        changed=True,
                        channel=category,
                    ),
                    ResourceApplyResult(
                        resource_id="profile",
                        success=False,
                        detail=str(http_50013()),
                    ),
                ]
            )
        ),
    )

    with pytest.raises(NetworkValidationError, match="network-profile channel") as exc_info:
        await verify_provision_permissions_live(
            guild,
            bot,
            access,
            access_role_name="The Network",
            operator_role_name="The Network+",
        )

    assert "create client role" in str(exc_info.value)
    category.delete.assert_awaited_once()
    client_role.delete.assert_awaited_once()
