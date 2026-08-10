from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member

from bot.cogs._responses import defer_ephemeral
from bot.domain.client import Client
from bot.messages import render_text
from bot.services.sticky_sync import embed_content_signature, sticky_channel_embed_permission_error
from bot.ui._auth import MembershipPolicy, ensure_client_access, validate_hub_modal_context


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


@pytest.mark.asyncio
async def test_ensure_client_access_allows_admin_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=True)
    interaction = make_interaction(guild=guild, user=member, deferred=True)
    guild.get_role = MagicMock(return_value=client_role)

    allowed = await ensure_client_access(
        interaction,
        guild,
        client,
        popup_key="client_role_required_subscribe",
        membership_policy=MembershipPolicy.ALLOW_NON_MEMBER,
        via="followup",
    )

    assert allowed is True
    interaction.followup.send.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_client_access_skips_check_for_non_member_when_allowed() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    user = MagicMock(spec=discord.User, id=999)
    interaction = make_interaction(guild=guild, user=user, deferred=True)

    allowed = await ensure_client_access(
        interaction,
        guild,
        client,
        popup_key="client_role_required_subscribe",
        membership_policy=MembershipPolicy.ALLOW_NON_MEMBER,
        via="followup",
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_validate_hub_modal_context_rejects_wrong_guild() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.bot_context = MagicMock()
    interaction = MagicMock()
    interaction.guild = MagicMock(id=999)

    result = validate_hub_modal_context(bot, interaction)

    assert result == render_text("central_guild_only")


@pytest.mark.asyncio
async def test_validate_client_modal_context_rejects_missing_guild() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.bot_context = MagicMock()
    interaction = MagicMock()
    interaction.guild = None

    from bot.ui._auth import validate_client_modal_context

    result = validate_client_modal_context(bot, interaction)

    assert result == render_text("hub_guild_form_only")


@pytest.mark.asyncio
async def test_validate_hub_modal_context_uses_custom_guild_only_key() -> None:
    bot = MagicMock()
    bot.settings.guild_id = 100
    bot.bot_context = MagicMock()
    interaction = MagicMock()
    interaction.guild = MagicMock(id=999)

    result = validate_hub_modal_context(
        bot,
        interaction,
        guild_only_key="hub_guild_only",
    )

    assert result == render_text("hub_guild_only")


def test_embed_content_signature_stable_for_same_embed() -> None:
    embed = discord.Embed(title="Hello", description="World")
    assert embed_content_signature(embed) == embed_content_signature(embed)


def test_sticky_channel_embed_permission_error_when_missing_embed_links() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "#rules"
    bot_member = MagicMock(spec=discord.Member)
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = False
    channel.permissions_for = MagicMock(return_value=perms)

    error = sticky_channel_embed_permission_error(channel, bot_member)

    assert error is not None
    assert "Embed Links" in error


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
    assert response.sent is True
