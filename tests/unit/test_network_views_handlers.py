from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member
from subscription_helpers import make_client_subscription

from bot.core.models.client import Client
from bot.core.models.network import Network
from bot.widgets import render_text
from bot.widgets.views.network_views import (
    NetworkProfileView,
    SubscriptionModerationView,
    handle_subscribe_connected,
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
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_key = AsyncMock(return_value=network)
    context.refresh_projections = AsyncMock()

    subscribe_result = MagicMock(success=True, subscription=subscription, created=True, error=None)
    monkeypatch.setattr(
        "bot.core.clients.subscription.ClientSubscriptionService.subscribe_client",
        AsyncMock(return_value=subscribe_result),
    )
    monkeypatch.setattr(
        "bot.channels.stickies.subscription.sync_subscription_setup",
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
    context.store.clients.get_by_id = AsyncMock(return_value=client)

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
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_key = AsyncMock(return_value=network)

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
        "bot.core.clients.subscription.ClientSubscriptionService.subscribe_client",
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


@pytest.mark.asyncio
async def test_subscribe_button_reports_network_not_found() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_key = AsyncMock(return_value=None)

    bot = MagicMock()
    bot.bot_context = context
    bot.settings.network_access_role_name = "The Network"

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["missing"])
    await view._handle_subscribe(interaction, "missing")

    assert interaction.followup.send.await_args.args[0] == render_text(
        "network_not_found",
        network_key="missing",
    )


@pytest.mark.asyncio
async def test_subscribe_button_reports_client_not_found() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=None)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member

    view = NetworkProfileView(bot, 999, ["stingers"])
    await view._handle_subscribe(interaction, "stingers")

    assert interaction.followup.send.await_args.args[0] == render_text("client_not_found")


@pytest.mark.asyncio
async def test_subscribe_button_allows_manage_guild_without_client_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=True)

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

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_key = AsyncMock(return_value=network)
    context.refresh_projections = AsyncMock()

    subscribe_result = MagicMock(success=True, subscription=subscription, created=True, error=None)
    monkeypatch.setattr(
        "bot.core.clients.subscription.ClientSubscriptionService.subscribe_client",
        AsyncMock(return_value=subscribe_result),
    )
    monkeypatch.setattr(
        "bot.channels.stickies.subscription.sync_subscription_setup",
        AsyncMock(),
    )

    bot = MagicMock()
    bot.bot_context = context
    bot.settings.network_access_role_name = "The Network"

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)
    publish = MagicMock(spec=discord.TextChannel, id=100, mention="#publish")
    subscribe = MagicMock(spec=discord.TextChannel, id=101, mention="#subscribe")
    guild.get_channel = MagicMock(
        side_effect=lambda cid: publish if cid == 100 else subscribe,
    )

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._handle_subscribe(interaction, "stingers")

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Network Subscription"


@pytest.mark.asyncio
async def test_timecode_toggle_blocks_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=False)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._timecode_toggle_callback(interaction)

    assert interaction.followup.send.await_args.args[0] == render_text(
        "client_role_required_edit",
    )


@pytest.mark.asyncio
async def test_delete_button_blocks_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=False)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._delete_callback(interaction)

    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.args[0] == render_text(
        "client_role_required_delete",
    )


@pytest.mark.asyncio
async def test_delete_button_shows_confirm_prompt_for_client_role_holder() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = NetworkProfileView(bot, client.id, ["stingers"])
    await view._delete_callback(interaction)

    prompt = interaction.response.send_message.await_args.args[0]
    assert client.server_name in prompt
    assert interaction.response.send_message.await_args.kwargs["view"] is not None


@pytest.mark.asyncio
async def test_leave_network_blocks_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=False)
    subscription = make_client_subscription()

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=subscription)
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = SubscriptionModerationView(bot, subscription.id, "stingers")
    await view._leave_callback(interaction)

    assert interaction.followup.send.await_args.args[0] == render_text(
        "client_role_required_leave",
    )


@pytest.mark.asyncio
async def test_leave_network_renders_failure_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])
    subscription = make_client_subscription()

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=subscription)
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_id = AsyncMock(
        return_value=Network(
            id=2,
            key="stingers",
            display_name="Stingers",
            feed_category_id=None,
            output_channel_id=None,
            concat_channel_id=None,
            profile_forum_channel_id=None,
            join_channel_id=None,
            enabled=True,
        ),
    )

    unsubscribe_result = MagicMock(success=False, error="Missing Permissions")
    monkeypatch.setattr(
        "bot.core.clients.subscription.ClientSubscriptionService.unsubscribe_client",
        AsyncMock(return_value=unsubscribe_result),
    )

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = SubscriptionModerationView(bot, subscription.id, "stingers")
    await view._leave_callback(interaction)

    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Could not leave network"


@pytest.mark.asyncio
async def test_blacklist_button_reports_no_targets() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])
    subscription = make_client_subscription()

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=subscription)
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.clients.list_subscriptions_by_network = AsyncMock(return_value=[subscription])

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = SubscriptionModerationView(
        bot,
        subscription.id,
        "stingers",
        show_blacklist=True,
    )
    await view._blacklist_callback(interaction)

    assert interaction.response.send_message.await_args.args[0] == render_text(
        "no_blacklist_targets",
    )


@pytest.mark.asyncio
async def test_subscribe_connected_reports_missing_subscription() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild)

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=None)

    bot = MagicMock()
    bot.bot_context = context

    interaction = make_interaction(guild=guild, user=member)

    await handle_subscribe_connected(bot, interaction, subscription_id=99, network_key="stingers")

    assert interaction.followup.send.await_args.args[0] == render_text("subscription_not_found")
