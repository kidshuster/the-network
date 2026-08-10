from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from subscription_helpers import make_client_subscription

from bot.domain.client import Client
from bot.domain.network import Network
from bot.ui.network_views import NetworkProfileView


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
async def test_subscribe_button_success_renders_subscribe_success_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = MagicMock(spec=discord.Member, id=555)
    member.roles = [client_role]
    member.guild_permissions.manage_guild = False

    network = Network(
        id=2,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )
    subscription = make_client_subscription(id=5)
    publish = MagicMock(spec=discord.TextChannel, id=100, mention="#publish")
    subscribe = MagicMock(spec=discord.TextChannel, id=101, mention="#subscribe")

    context = MagicMock()
    context.client_repo.get_by_id = AsyncMock(return_value=client)
    context.network_repo.get_by_key = AsyncMock(return_value=network)
    context.client_cache.load_cache = AsyncMock()
    context.routing_service.load_cache = AsyncMock()

    subscribe_result = MagicMock(success=True, subscription=subscription, created=True, error=None)
    monkeypatch.setattr(
        "bot.services.client_subscription.ClientSubscriptionService.subscribe_client",
        AsyncMock(return_value=subscribe_result),
    )
    monkeypatch.setattr(
        "bot.services.subscription_setup_sticky.sync_subscription_setup",
        AsyncMock(),
    )

    bot = MagicMock()
    bot.bot_context = context
    bot.settings.network_access_role_name = "The Network"

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(
        side_effect=lambda cid: publish if cid == 100 else subscribe,
    )

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._handle_subscribe(interaction, "stingers")

    interaction.followup.send.assert_awaited_once()
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Network Subscription"


@pytest.mark.asyncio
async def test_subscribe_button_blocks_without_client_role() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = MagicMock(spec=discord.Member, id=555)
    member.roles = []
    member.guild_permissions.manage_guild = False

    context = MagicMock()
    context.client_repo.get_by_id = AsyncMock(return_value=client)

    bot = MagicMock()
    bot.bot_context = context
    bot.settings.network_access_role_name = "The Network"

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._handle_subscribe(interaction, "stingers")

    sent = interaction.followup.send.await_args.args[0]
    assert "client role" in sent.casefold()


@pytest.mark.asyncio
async def test_subscribe_button_renders_failure_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = MagicMock(spec=discord.Member, id=555)
    member.roles = [client_role]
    member.guild_permissions.manage_guild = False

    network = Network(
        id=2,
        key="stingers",
        display_name="Stingers",
        feed_category_id=None,
        output_channel_id=None,
        concat_channel_id=None,
        profile_forum_channel_id=None,
        join_channel_id=None,
        enabled=True,
    )

    context = MagicMock()
    context.client_repo.get_by_id = AsyncMock(return_value=client)
    context.network_repo.get_by_key = AsyncMock(return_value=network)

    bot = MagicMock()
    bot.bot_context = context
    bot.settings.network_access_role_name = "The Network"

    subscribe_result = MagicMock(
        success=False,
        subscription=None,
        created=False,
        error="Discord API error: Missing Permissions",
    )
    monkeypatch.setattr(
        "bot.services.client_subscription.ClientSubscriptionService.subscribe_client",
        AsyncMock(return_value=subscribe_result),
    )

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._handle_subscribe(interaction, "stingers")

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Subscribe Failed"
