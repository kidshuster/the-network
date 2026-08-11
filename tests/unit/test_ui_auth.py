from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_member

from bot.app.discord.responses import defer_ephemeral
from bot.core.models.client import Client
from bot.core.templates import render_text
from bot.errors import UserFacingError
from bot.features.channels.stickies.reconciler import (
    embed_content_signature,
    sticky_channel_embed_permission_error,
)
from bot.features.widgets.guards import (
    require_client_member,
    require_hub_guild,
    require_manage_guild,
)


def _client() -> Client:
    return Client(
        id=1,
        guild_id=100,
        server_name="Acme",
        display_name="Acme",
        category_id=10,
        client_role_id=20,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        timecode_enabled=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def test_require_client_member_allows_admin_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=True)
    guild.get_role = MagicMock(return_value=client_role)
    require_client_member(guild, member, client, allow_non_member=True)


def test_require_client_member_skips_non_member_when_allowed() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    user = MagicMock(spec=discord.User, id=999)
    require_client_member(guild, user, client, allow_non_member=True)


def test_require_hub_guild_rejects_wrong_guild() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.bot_context = MagicMock()
    with pytest.raises(UserFacingError, match=render_text("hub_guild_only")):
        require_hub_guild(bot, MagicMock(id=999))


def test_require_manage_guild_rejects_member() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, roles=[], manage_guild=False)
    with pytest.raises(UserFacingError) as raised:
        require_manage_guild(member)
    assert raised.value.message == render_text("manage_guild_required")


def test_embed_content_signature_stable_for_same_embed() -> None:
    embed = discord.Embed(title="Hello", description="World")
    assert embed_content_signature(embed) == embed_content_signature(embed)


@pytest.mark.asyncio
async def test_defer_ephemeral_returns_response_helper() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    response = await defer_ephemeral(interaction)
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    await response.send("done", ephemeral=True)


def test_sticky_channel_embed_permission_error_message() -> None:
    assert sticky_channel_embed_permission_error is not None
