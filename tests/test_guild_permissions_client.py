from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import (
    discord_like_hub_category_create_text_channel,
    http_50013,
    make_guild_with_roles,
    make_role,
)

from bot.permissions.service import (
    ResourceKind,
    applicable_overwrites,
    build_context,
    permission_service,
)

Target = discord.Role | discord.Member | discord.Object


def _client_setup() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild, bot, human_mod, access, _operator = make_guild_with_roles()
    client_role = make_role(name="Client: Acme", role_id=60, position=1)
    return guild, bot, client_role, access, human_mod


def _text_filter(
    bot: discord.Member,
    overwrites: Mapping[Target, discord.PermissionOverwrite],
) -> dict[Target, discord.PermissionOverwrite]:
    return applicable_overwrites(
        build_context(bot.guild, bot, access_role=None, moderator_role=None),
        overwrites,
        kind=ResourceKind.TEXT,
    )


async def _ensure_text(
    guild: discord.Guild,
    bot: discord.Member,
    *,
    name: str,
    overwrites: Mapping[Target, discord.PermissionOverwrite],
    reason: str,
    category: discord.CategoryChannel | None = None,
) -> discord.TextChannel:
    result = await permission_service.ensure_text_channel(
        guild,
        build_context(guild, bot, access_role=None, moderator_role=None),
        existing=None,
        name=name,
        overwrites=overwrites,
        reason=reason,
        category=category,
    )
    return result.resource


def test_managed_role_passes_filter() -> None:
    guild, bot, client_role, _, _ = _client_setup()
    managed = make_role(name="Managed", role_id=70, position=2, managed=True)
    source = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        managed: discord.PermissionOverwrite(view_channel=True),
        client_role: discord.PermissionOverwrite(view_channel=True),
    }
    safe = _text_filter(bot, source)
    assert managed in safe
    assert client_role in safe


@pytest.mark.asyncio
async def test_ensure_text_omits_overwrites_on_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, client_role, _, _ = _client_setup()
    managed = make_role(name="Managed", role_id=70, position=2, managed=True)
    safe = _text_filter(
        bot,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            managed: discord.PermissionOverwrite(view_channel=True),
            client_role: discord.PermissionOverwrite(view_channel=True),
        },
    )
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 900
    channel.category_id = None
    channel.overwrites = {}
    channel.edit = AsyncMock(side_effect=http_50013("Cannot set overwrites on managed role"))
    channel.set_permissions = AsyncMock(
        side_effect=http_50013("Cannot set overwrites on managed role"),
    )
    guild.create_text_channel = AsyncMock(return_value=channel)
    bot.guild = guild
    bot.guild_permissions.manage_channels = True
    monkeypatch.setattr(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    await _ensure_text(guild, bot, name="bad", overwrites=safe, reason="test")

    assert "overwrites" not in guild.create_text_channel.await_args.kwargs
    channel.edit.assert_awaited()


@pytest.mark.asyncio
async def test_profile_create_in_hub_category_50013_without_two_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, client_role, access, _ = _client_setup()
    hub_category = MagicMock(spec=discord.CategoryChannel, id=100)
    overwrites = _text_filter(
        bot,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            client_role: discord.PermissionOverwrite(view_channel=True),
            access: discord.PermissionOverwrite(view_channel=True, manage_webhooks=True),
        },
    )
    guild.create_text_channel = AsyncMock(
        side_effect=discord_like_hub_category_create_text_channel(bot),
    )
    monkeypatch.setattr(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    with pytest.raises(discord.HTTPException) as exc_info:
        await guild.create_text_channel(
            name="acme-profile",
            category=hub_category,
            overwrites=overwrites,
            reason="test",
        )
    assert exc_info.value.code == 50013


@pytest.mark.asyncio
async def test_ensure_text_avoids_hub_category_create_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, client_role, access, _ = _client_setup()
    hub_category = MagicMock(spec=discord.CategoryChannel, id=100)
    created: list[MagicMock] = []

    async def _create(**kwargs: object) -> discord.TextChannel:
        channel = await discord_like_hub_category_create_text_channel(bot)(**kwargs)
        created.append(channel)
        return channel

    guild.create_text_channel = AsyncMock(side_effect=_create)
    monkeypatch.setattr(
        "bot.hub.notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )
    overwrites = _text_filter(
        bot,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            client_role: discord.PermissionOverwrite(view_channel=True),
            access: discord.PermissionOverwrite(view_channel=True),
        },
    )
    profile = await _ensure_text(
        guild,
        bot,
        name="acme-profile",
        category=hub_category,
        overwrites=overwrites,
        reason="test",
    )
    assert profile is created[0]
    assert "overwrites" not in guild.create_text_channel.await_args.kwargs
    profile.edit.assert_awaited()


def test_profile_overwrites_skip_role_above_bot_top() -> None:
    guild, bot, client_role, _, _ = _client_setup()
    high_role = make_role(name="Owner", role_id=80, position=20)
    safe = _text_filter(
        bot,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            high_role: discord.PermissionOverwrite(view_channel=True),
            client_role: discord.PermissionOverwrite(view_channel=True),
        },
    )
    assert high_role not in safe
    assert client_role in safe
