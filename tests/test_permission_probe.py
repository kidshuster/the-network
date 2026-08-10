from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest
from discord_helpers import discord_like_hub_category_create_text_channel, make_guild_with_roles

from bot.domain.errors import NetworkValidationError
from bot.services.permission_probe import (
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
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.validate_provision_permissions",
        MagicMock(),
    )
    monkeypatch.setattr(
        "bot.services.guild_permissions.create_text_channel_with_overwrites",
        AsyncMock(side_effect=[channel, publish_channel]),
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

    async def _fail_profile_create(**kwargs: object) -> MagicMock:
        if "profile" in str(kwargs.get("name", "")):
            raise http_50013()
        channel = MagicMock(spec=discord.TextChannel)
        channel.delete = AsyncMock()
        return channel

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.guild_permissions.create_text_channel_with_overwrites",
        AsyncMock(side_effect=_fail_profile_create),
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


@pytest.mark.asyncio
async def test_verify_provision_permissions_live_uses_real_overwrite_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    guild.emojis = []
    guild.channels = []

    client_role = MagicMock(spec=discord.Role, id=601, position=1)
    client_role.is_default.return_value = False
    client_role.delete = AsyncMock()
    category = MagicMock(spec=discord.CategoryChannel)
    category.delete = AsyncMock()

    channel_counter = 0

    async def _create(**kwargs: object) -> MagicMock:
        nonlocal channel_counter
        channel_counter += 1
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        channel.create_webhook = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
        channel.delete = AsyncMock()
        return channel

    guild.create_role = AsyncMock(return_value=client_role)
    guild.create_category = AsyncMock(return_value=category)
    guild.create_text_channel = AsyncMock(side_effect=_create)

    async def _add_roles(role: discord.Role, **_kwargs: object) -> None:
        bot.roles = [*bot.roles, role]

    bot.add_roles = AsyncMock(side_effect=_add_roles)
    bot.remove_roles = AsyncMock()

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    steps = await verify_provision_permissions_live(
        guild,
        bot,
        access,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert "create network-profile channel" in steps
    assert guild.create_text_channel.await_count >= 2
    for call in guild.create_text_channel.await_args_list:
        overwrites = call.kwargs.get("overwrites") or {}
        assert bot not in overwrites


@pytest.mark.asyncio
async def test_verify_provision_permissions_live_survives_hub_category_create_quirk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for live init failure: profile channel 50013 inside hub category."""
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    guild.emojis = []
    guild.channels = []

    client_role = MagicMock(spec=discord.Role, id=601, position=1, name="Client: probe")
    client_role.is_default.return_value = False
    client_role.delete = AsyncMock()
    category = MagicMock(spec=discord.CategoryChannel, id=700)
    category.delete = AsyncMock()

    guild.create_role = AsyncMock(return_value=client_role)
    guild.create_category = AsyncMock(return_value=category)
    guild.create_text_channel = AsyncMock(
        side_effect=discord_like_hub_category_create_text_channel(bot),
    )

    async def _add_roles(role: discord.Role, **_kwargs: object) -> None:
        bot.roles = [*bot.roles, role]

    bot.add_roles = AsyncMock(side_effect=_add_roles)
    bot.remove_roles = AsyncMock()

    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=operator),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    steps = await verify_provision_permissions_live(
        guild,
        bot,
        access,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert "create network-profile channel" in steps
    assert "create client publish channel with webhook overwrites" in steps
    for call in guild.create_text_channel.await_args_list:
        assert "overwrites" not in call.kwargs
