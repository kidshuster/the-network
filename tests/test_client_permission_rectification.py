from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.domain.client import Client
from bot.services.client_permission_rectification import rectify_client_permissions
from bot.services.guild_init import GuildInitResult
from bot.services.guild_layout import resolve_leaders_channel


def test_resolve_leaders_channel_finds_legacy_name_in_leaders_category() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.text_channels = []

    leaders_category = MagicMock(spec=discord.CategoryChannel)
    leaders_category.id = 100
    leaders_category.name = "Leaders"

    legacy = MagicMock(spec=discord.TextChannel)
    legacy.id = 200
    legacy.name = "leaders"
    legacy.category_id = 100

    guild.categories = [leaders_category]
    guild.text_channels = [legacy]

    assert resolve_leaders_channel(guild) is legacy


async def test_rectify_client_permissions_syncs_category_and_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 10
    category.edit = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 20
    client_role.position = 1
    client_role.is_default.return_value = False

    profile = MagicMock(spec=discord.TextChannel)
    profile.id = 30
    profile.mention = "#acme-profile"
    profile.permissions_synced = False
    profile.edit = AsyncMock()
    profile.set_permissions = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    access_role = MagicMock(spec=discord.Role)
    access_role.id = 40
    access_role.position = 5
    access_role.is_default.return_value = False

    guild.get_channel = MagicMock(
        side_effect=lambda channel_id: {10: category, 30: profile}.get(channel_id),
    )
    guild.get_role = MagicMock(return_value=client_role)

    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
        timecode_enabled=False,
    )

    context = MagicMock()
    context.client_repo.list_subscriptions_by_client = AsyncMock(return_value=[])

    monkeypatch.setattr(
        "bot.services.client_subscription.resolve_access_role",
        MagicMock(return_value=access_role),
    )
    monkeypatch.setattr(
        "bot.services.client_subscription.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )

    result = await rectify_client_permissions(
        guild,
        bot_member,
        context,
        client,
        access_role=access_role,
        human_moderator_role=None,
        access_role_name="The Network",
    )

    assert "category" in result.synced
    assert any("#acme-profile" in item for item in result.synced)
    category.edit.assert_awaited_once()
    profile.set_permissions.assert_awaited()


def test_guild_init_result_tracks_rectification_fields() -> None:
    result = GuildInitResult(success=True)
    result.rectifications.append("Leaders access synced.")
    result.rectification_skipped.append("**Acme**: client role missing in Discord")
    result.rectification_failures.append("Leaders: could not sync #leaders-channel.")

    assert len(result.rectifications) == 1
    assert len(result.rectification_skipped) == 1
    assert len(result.rectification_failures) == 1
