from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import (
    discord_like_create_text_channel,
    discord_like_hub_category_create_text_channel,
    http_50013,
    make_guild_with_roles,
    make_role,
)

from bot.services.guild_permissions import (
    build_client_category_overwrites,
    build_client_profile_channel_overwrites,
    build_client_publish_channel_overwrites,
    build_client_subscribe_channel_overwrites,
    create_text_channel_with_overwrites,
    filter_configurable_overwrites,
    sync_client_category_permissions,
)


def _client_setup() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    client_role = make_role(name="Client: Acme", role_id=60, position=1)
    return guild, bot, client_role, access, human_mod


def test_client_category_overwrites_hide_everyone_and_grant_client() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    overwrites = dict(
        build_client_category_overwrites(
            guild, bot, client_role, access, human_mod,
        )
    )
    assert overwrites[guild.default_role].view_channel is False
    assert overwrites[client_role].view_channel is True
    assert overwrites[access].view_channel is True
    assert bot in overwrites


def test_client_profile_overwrites_omit_bot_member_on_channel() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    source = dict(
        build_client_profile_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        )
    )
    safe = filter_configurable_overwrites(bot, source, for_channel=True)
    assert bot not in safe
    assert guild.default_role in safe
    assert client_role in safe
    assert access in safe


def test_client_publish_overwrite_allows_webhooks_not_send() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    overwrites = dict(
        build_client_publish_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        )
    )
    publish = overwrites[client_role]
    assert publish.manage_webhooks is True
    assert publish.send_messages is False


def test_client_subscribe_overwrite_hides_everyone_grants_client() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    overwrites = dict(
        build_client_subscribe_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        )
    )
    everyone = overwrites[guild.default_role]
    assert everyone.view_channel is False
    assert overwrites[client_role].view_channel is True
    assert overwrites[access].view_channel is True


def test_managed_role_passes_filter_but_discord_like_create_rejects() -> None:
    guild, bot, client_role, _, _ = _client_setup()
    managed = make_role(name="Managed", role_id=70, position=2, managed=True)
    source = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        managed: discord.PermissionOverwrite(view_channel=True),
        client_role: discord.PermissionOverwrite(view_channel=True),
    }
    safe = filter_configurable_overwrites(bot, source, for_channel=True)
    assert managed in safe
    assert client_role in safe


@pytest.mark.asyncio
async def test_managed_role_rejected_by_discord_like_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    guild, bot, client_role, _, _ = _client_setup()
    managed = make_role(name="Managed", role_id=70, position=2, managed=True)
    safe = filter_configurable_overwrites(
        bot,
        {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            managed: discord.PermissionOverwrite(view_channel=True),
            client_role: discord.PermissionOverwrite(view_channel=True),
        },
        for_channel=True,
    )
    guild.create_text_channel = AsyncMock(
        side_effect=discord_like_create_text_channel(bot),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    with pytest.raises(discord.HTTPException) as exc_info:
        await create_text_channel_with_overwrites(
            guild,
            bot,
            name="bad",
            overwrites=safe,
            reason="test",
        )
    assert exc_info.value.code == 50013


@pytest.mark.asyncio
async def test_sync_client_category_permissions_edits_category() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    category = MagicMock(spec=discord.CategoryChannel)
    category.guild = guild
    category.edit = AsyncMock()

    await sync_client_category_permissions(
        category,
        bot,
        client_role,
        access,
        human_mod,
        reason="test",
    )

    category.edit.assert_awaited_once()
    overwrites = category.edit.await_args.kwargs["overwrites"]
    assert guild.default_role in overwrites
    assert client_role in overwrites


@pytest.mark.asyncio
async def test_create_text_channel_rejects_member_overwrites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    guild, bot, client_role, access, human_mod = _client_setup()
    category = MagicMock(spec=discord.CategoryChannel, id=100)
    created_channels: list[MagicMock] = []

    async def _create_channel(**kwargs: object) -> discord.TextChannel:
        channel = await discord_like_create_text_channel(bot)(**kwargs)
        created_channels.append(channel)
        return channel

    guild.create_text_channel = AsyncMock(side_effect=_create_channel)
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    overwrites = dict(
        build_client_profile_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        )
    )
    await create_text_channel_with_overwrites(
        guild,
        bot,
        name="acme-profile",
        category=category,
        overwrites=overwrites,
        reason="test",
    )
    guild.create_text_channel.assert_awaited_once()
    create_kwargs = guild.create_text_channel.await_args.kwargs
    assert "overwrites" not in create_kwargs
    assert create_kwargs["category"] is category
    channel = created_channels[0]
    channel.edit.assert_awaited()


@pytest.mark.asyncio
async def test_profile_channel_in_hub_category_replicates_live_50013_without_two_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discord rejects profile overwrites at create time inside a hub client category."""
    guild, bot, client_role, access, human_mod = _client_setup()
    hub_category = MagicMock(spec=discord.CategoryChannel, id=100)
    profile_overwrites = filter_configurable_overwrites(
        bot,
        build_client_profile_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        ),
        for_channel=True,
    )
    guild.create_text_channel = AsyncMock(
        side_effect=discord_like_hub_category_create_text_channel(bot),
    )
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    with pytest.raises(discord.HTTPException) as exc_info:
        await guild.create_text_channel(
            name="acme-profile",
            category=hub_category,
            overwrites=profile_overwrites,
            reason="test",
        )
    assert exc_info.value.code == 50013


@pytest.mark.asyncio
async def test_create_text_channel_with_overwrites_avoids_hub_category_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: provision probe profile channel inside hub category (live init failure)."""
    guild, bot, client_role, access, human_mod = _client_setup()
    hub_category = MagicMock(spec=discord.CategoryChannel, id=100)
    created_channels: list[MagicMock] = []

    async def _create_channel(**kwargs: object) -> discord.TextChannel:
        channel = await discord_like_hub_category_create_text_channel(bot)(**kwargs)
        created_channels.append(channel)
        return channel

    guild.create_text_channel = AsyncMock(side_effect=_create_channel)
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    profile_overwrites = filter_configurable_overwrites(
        bot,
        build_client_profile_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        ),
        for_channel=True,
    )
    publish_overwrites = filter_configurable_overwrites(
        bot,
        build_client_publish_channel_overwrites(
            guild, bot, client_role, access, human_mod,
        ),
        for_channel=True,
    )

    profile = await create_text_channel_with_overwrites(
        guild,
        bot,
        name="acme-profile",
        category=hub_category,
        overwrites=profile_overwrites,
        reason="test",
    )
    publish = await create_text_channel_with_overwrites(
        guild,
        bot,
        name="acme-publish",
        category=hub_category,
        overwrites=publish_overwrites,
        reason="test",
    )

    assert profile is created_channels[0]
    assert publish is created_channels[1]
    for call in guild.create_text_channel.await_args_list:
        assert "overwrites" not in call.kwargs
        assert call.kwargs["category"] is hub_category
    profile.edit.assert_awaited()
    publish.edit.assert_awaited()


@pytest.mark.asyncio
async def test_create_text_channel_fails_when_managed_role_in_overwrites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.services.guild_permissions import create_text_channel_with_overwrites

    guild, bot, _, access, _ = _client_setup()
    managed = make_role(name="ManagedMod", role_id=70, position=2, managed=True)
    category = MagicMock(spec=discord.CategoryChannel, id=100)
    channel = MagicMock(spec=discord.TextChannel)
    channel.category_id = 100
    channel.edit = AsyncMock(side_effect=http_50013("Cannot set overwrites on managed role"))
    guild.create_text_channel = AsyncMock(return_value=channel)
    monkeypatch.setattr(
        "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
        AsyncMock(),
    )

    with pytest.raises(discord.HTTPException) as exc_info:
        await create_text_channel_with_overwrites(
            guild,
            bot,
            name="bad-profile",
            category=category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                managed: discord.PermissionOverwrite(view_channel=True),
            },
            reason="test",
        )

    assert exc_info.value.code == 50013


def test_profile_overwrites_skip_role_above_bot_top() -> None:
    guild, bot, client_role, access, human_mod = _client_setup()
    high_role = make_role(name="Owner", role_id=80, position=20)
    source = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        high_role: discord.PermissionOverwrite(view_channel=True),
        client_role: discord.PermissionOverwrite(view_channel=True),
    }
    safe = filter_configurable_overwrites(bot, source, for_channel=True)
    assert high_role not in safe
    assert client_role in safe
