from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest

from bot.domain.profile import ServerProfile
from bot.services.guild_init import initialize_guild


def _http_50013() -> discord.HTTPException:
    exc = discord.HTTPException(MagicMock(), "Missing Permissions")
    exc.status = 403
    exc.code = 50013
    return exc


def _guild_with_roles(
    *,
    bot_position: int = 10,
    access_position: int = 2,
    human_mod_position: int = 4,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.categories = []
    guild.text_channels = []
    guild.channels = []
    guild.rules_channel = None

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    everyone.position = 0
    guild.default_role = everyone

    access = MagicMock(spec=discord.Role, name="The Network", id=20, position=access_position)
    access.is_default.return_value = False
    human_mod = MagicMock(spec=discord.Role, name="Moderator", id=30, position=human_mod_position)
    human_mod.is_default.return_value = False
    bot_role = MagicMock(
        spec=discord.Role, name="The Network Moderator", id=40, position=bot_position
    )
    bot_role.is_default.return_value = False

    bot = MagicMock(spec=discord.Member, id=999, roles=[bot_role])
    bot.top_role = bot_role
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.administrator = False
    type(bot).guild_permissions = PropertyMock(return_value=perms)

    guild.roles = [everyone, access, human_mod, bot_role]
    guild.me = bot
    return guild, bot, access, human_mod, bot_role


def _patch_init_roles(
    monkeypatch: pytest.MonkeyPatch,
    access: MagicMock,
    bot_role: MagicMock,
    human_mod: MagicMock,
) -> None:
    monkeypatch.setattr(
        "bot.services.guild_init.resolve_access_role",
        MagicMock(return_value=access),
    )
    monkeypatch.setattr(
        "bot.services.guild_init.resolve_moderator_role",
        MagicMock(return_value=bot_role),
    )
    monkeypatch.setattr(
        "bot.services.guild_init.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.services.guild_init.resolve_welcome_sink_channel",
        MagicMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.services.guild_init._ensure_moderator_role",
        AsyncMock(return_value=bot_role),
    )


@pytest.mark.asyncio
async def test_initialize_guild_survives_category_sync_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, access, human_mod, bot_role = _guild_with_roles()

    existing_category = MagicMock(spec=discord.CategoryChannel)
    existing_category.id = 501
    existing_category.name = "The Network"
    existing_category.channels = []
    existing_category.edit = AsyncMock(side_effect=_http_50013())
    guild.categories = [existing_category]

    monkeypatch.setattr(
        "bot.services.guild_init.resolve_category",
        lambda _guild, name: existing_category if name == "The Network" else None,
    )
    _patch_init_roles(monkeypatch, access, bot_role, human_mod)

    async def fake_create_text_channel(**kwargs: object) -> MagicMock:
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 900
        channel.position = 0
        channel.edit = AsyncMock()
        return channel

    guild.create_text_channel = AsyncMock(side_effect=fake_create_text_channel)
    guild.create_category = AsyncMock(return_value=existing_category)

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        moderator_role_name="The Network Moderator",
    )

    assert result.success is True
    assert result.failed_steps
    assert any("category" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_initialize_guild_survives_rules_channel_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, access, human_mod, bot_role = _guild_with_roles()

    network_cat = MagicMock(spec=discord.CategoryChannel)
    network_cat.id = 501
    network_cat.name = "The Network"
    network_cat.channels = []

    rules = MagicMock(spec=discord.TextChannel)
    rules.id = 777
    rules.name = "rules"
    rules.mention = "#rules"
    rules.category_id = network_cat.id
    rules.edit = AsyncMock(side_effect=_http_50013())
    guild.rules_channel = rules
    network_cat.channels = [rules]

    subscribe = MagicMock(spec=discord.CategoryChannel, id=502, name="Subscribe To Me!")
    subscribe.channels = []
    subscribe.edit = AsyncMock()
    moderation = MagicMock(spec=discord.CategoryChannel, id=503, name="Moderation")
    moderation.channels = []
    moderation.edit = AsyncMock()

    def resolve_cat(_guild: MagicMock, name: str) -> MagicMock | None:
        return {
            "The Network": network_cat,
            "Subscribe To Me!": subscribe,
            "Moderation": moderation,
        }.get(name)

    monkeypatch.setattr("bot.services.guild_init.resolve_category", resolve_cat)
    _patch_init_roles(monkeypatch, access, bot_role, human_mod)
    guild.create_text_channel = AsyncMock()
    guild.create_category = AsyncMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        moderator_role_name="The Network Moderator",
    )

    assert result.success is True
    assert any("rules" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_initialize_guild_survives_partner_feed_sync_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, access, human_mod, bot_role = _guild_with_roles()

    partner_role = MagicMock(spec=discord.Role, id=60, name="Partner: Alpha", position=1)
    partner_role.is_default.return_value = False
    guild.roles.append(partner_role)

    feed_category = MagicMock(spec=discord.CategoryChannel)
    feed_category.id = 600
    feed_category.name = "Stingers Feed"
    feed_channel = MagicMock(spec=discord.TextChannel)
    feed_channel.id = 700
    feed_channel.name = "stingers-alpha"
    feed_channel.type = discord.ChannelType.text
    feed_channel.edit = AsyncMock(side_effect=_http_50013())
    feed_category.channels = [feed_channel]
    guild.categories = [feed_category]

    for name in ("Subscribe To Me!", "The Network", "Moderation"):
        cat = MagicMock(spec=discord.CategoryChannel, id=id(name), name=name, channels=[])
        cat.edit = AsyncMock()
        guild.categories.append(cat)

    monkeypatch.setattr(
        "bot.services.guild_init.resolve_category",
        lambda _guild, name: next((c for c in guild.categories if c.name == name), None),
    )
    _patch_init_roles(monkeypatch, access, bot_role, human_mod)
    guild.get_role = MagicMock(return_value=partner_role)
    guild.create_text_channel = AsyncMock()
    guild.create_category = AsyncMock()

    profile = ServerProfile(
        id=1,
        guild_id=100,
        profile_thread_id=1,
        profile_starter_message_id=1,
        source_channel_id=700,
        network_id=1,
        server_name="Alpha",
        display_name="Alpha",
        enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
        partner_role_id=60,
        profile_forum_channel_id=None,
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        moderator_role_name="The Network Moderator",
        profiles=[profile],
    )

    assert result.success is True
    assert any("partner feed" in step.casefold() for step in result.failed_steps)


def test_moderator_category_overwrite_has_no_thread_flags() -> None:
    from bot.services.guild_permissions import (
        build_moderator_category_overwrite,
        build_moderator_channel_overwrite,
    )

    category = build_moderator_category_overwrite()
    channel = build_moderator_channel_overwrite()
    assert category.create_public_threads is not True
    assert channel.create_public_threads is True


def test_category_access_overwrite_has_no_thread_flags() -> None:
    from bot.services.guild_permissions import (
        build_network_access_category_overwrite,
        build_network_access_overwrite,
    )

    category = build_network_access_category_overwrite()
    channel = build_network_access_overwrite()
    assert category.create_public_threads is not True
    assert channel.create_public_threads is False
