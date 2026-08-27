from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from interaction_helpers import make_interaction, make_member
from subscription_helpers import make_client_subscription
from widget_helpers import mock_recipe_result, wire_widget_bot

from bot.app.widgets import render_view
from bot.core.models.client import Client
from bot.core.models.network import Network
from bot.core.templates import render_text


def _user_message(interaction: MagicMock) -> str:
    for call in (
        interaction.response.send_message,
        interaction.followup.send,
    ):
        count = getattr(call, "await_count", None)
        if not isinstance(count, int) or count < 1:
            continue
        args = call.await_args
        if args.args:
            return str(args.args[0])
        content = args.kwargs.get("content")
        if content is not None:
            return str(content)
        embed = args.kwargs.get("embed")
        if embed is not None:
            return str(embed.description or "")
    raise AssertionError("no user message sent")


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
        timecode_enabled=False, read_only=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


def _bot(context: MagicMock) -> MagicMock:
    bot = wire_widget_bot()
    bot.bot_context = context
    bot.settings.guild_id = 100
    bot.settings.network_access_role_name = "The Network"
    bot.trigger_catalog.get.side_effect = Exception("skip filter")
    return bot


async def _click_label(view: object, label: str, interaction: discord.Interaction) -> None:
    for child in getattr(view, "children", []):
        if isinstance(child, discord.ui.Button) and child.label == label:
            await child.callback(interaction)
            return
    raise AssertionError(f"missing button {label!r}")


@pytest.mark.asyncio
async def test_subscribe_button_success_renders_subscribe_success_embed() -> None:
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

    subscribe_result = MagicMock(
        success=True,
        subscription=subscription,
        created=True,
        error=None,
        message="Subscribed.",
    )

    bot = _bot(context)
    mock_recipe_result(bot, recipe="subscription.create", result=subscribe_result)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(
        side_effect=lambda cid: publish if cid == 100 else subscribe,
    )

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Join stingers", interaction)

    interaction.followup.send.assert_awaited_once()
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "Network Subscription"


@pytest.mark.asyncio
async def test_subscribe_button_blocks_without_client_role() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=False)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = _bot(context)

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Join stingers", interaction)

    assert "client role" in _user_message(interaction).casefold()


@pytest.mark.asyncio
async def test_subscribe_button_renders_failure_embed() -> None:
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

    bot = _bot(context)
    mock_recipe_result(
        bot,
        recipe="subscription.create",
        result=MagicMock(
            success=False,
            subscription=None,
            created=False,
            error="Discord API error: Missing Permissions",
        ),
    )

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Join stingers", interaction)

    assert "missing permissions" in _user_message(interaction).casefold()


@pytest.mark.asyncio
async def test_subscribe_button_reports_network_not_found() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)
    context.store.networks.get_by_key = AsyncMock(return_value=None)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["missing"])
    await _click_label(view, "Join missing", interaction)

    assert _user_message(interaction) == render_text(
        "network_not_found",
        network_key="missing",
    )


@pytest.mark.asyncio
async def test_subscribe_button_reports_client_not_found() -> None:
    guild, bot_member, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild, manage_guild=True)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=None)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member

    view = render_view("network_profile", bot, client_id=999, network_keys=["stingers"])
    await _click_label(view, "Join stingers", interaction)

    assert _user_message(interaction) == render_text("client_not_found")


@pytest.mark.asyncio
async def test_subscribe_button_allows_manage_guild_without_client_role() -> None:
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

    bot = _bot(context)
    mock_recipe_result(
        bot,
        recipe="subscription.create",
        result=MagicMock(
            success=True,
            subscription=subscription,
            created=True,
            error=None,
            message="Subscribed.",
        ),
    )

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)
    publish = MagicMock(spec=discord.TextChannel, id=100, mention="#publish")
    subscribe = MagicMock(spec=discord.TextChannel, id=101, mention="#subscribe")
    guild.get_channel = MagicMock(
        side_effect=lambda cid: publish if cid == 100 else subscribe,
    )

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Join stingers", interaction)

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

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view(
        "network_profile",
        bot,
        client_id=client.id,
        network_keys=["stingers"],
        timecode_enabled=False, read_only=False,
    )
    await _click_label(view, "Timecodes: Off", interaction)

    assert _user_message(interaction) == render_text("client_role_required_edit")


@pytest.mark.asyncio
async def test_delete_button_blocks_without_client_role() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[], manage_guild=False)

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Delete Client", interaction)

    assert _user_message(interaction) == render_text("client_role_required_delete")


@pytest.mark.asyncio
async def test_delete_button_shows_confirm_prompt_for_client_role_holder() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])

    context = MagicMock()
    context.store.clients.get_by_id = AsyncMock(return_value=client)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view("network_profile", bot, client_id=client.id, network_keys=["stingers"])
    await _click_label(view, "Delete Client", interaction)

    assert interaction.followup.send.await_count == 1
    kwargs = interaction.followup.send.await_args.kwargs
    prompt = kwargs.get("content") or (
        interaction.followup.send.await_args.args[0]
        if interaction.followup.send.await_args.args
        else ""
    )
    assert client.server_name in prompt
    assert kwargs["view"] is not None


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
    context.store.networks.get_by_id = AsyncMock(return_value=None)
    context.store.networks.get_by_key = AsyncMock(return_value=None)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=subscription.id,
        network_key="stingers",
    )
    await _click_label(view, "Leave stingers", interaction)

    assert _user_message(interaction) == render_text("client_role_required_leave")


@pytest.mark.asyncio
async def test_leave_network_renders_failure_embed() -> None:
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

    bot = _bot(context)
    mock_recipe_result(
        bot,
        recipe="subscription.leave",
        result=MagicMock(success=False, error="Missing Permissions"),
    )

    interaction = make_interaction(guild=guild, user=member)
    guild.me = bot_member
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=subscription.id,
        network_key="stingers",
    )
    await _click_label(view, "Leave stingers", interaction)

    assert "missing permissions" in _user_message(interaction).casefold()


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
    context.store.networks.get_by_id = AsyncMock(return_value=MagicMock())

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)
    guild.get_role = MagicMock(return_value=client_role)

    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=subscription.id,
        network_key="stingers",
        show_blacklist=True,
    )
    await _click_label(view, "Blacklist", interaction)

    assert _user_message(interaction) == render_text("no_blacklist_targets")


@pytest.mark.asyncio
async def test_blacklist_button_opens_select_and_replace_updates() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client()
    peer = Client(
        id=2,
        guild_id=100,
        server_name="PeerCo",
        display_name="PeerCo",
        category_id=11,
        client_role_id=21,
        profile_channel_id=31,
        profile_message_id=41,
        enabled=True,
        timecode_enabled=False,
        read_only=False,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )
    client_role = MagicMock(spec=discord.Role, id=20)
    member = make_member(guild=guild, roles=[client_role])
    subscription = make_client_subscription(id=5, client_id=1, network_id=2)
    peer_sub = make_client_subscription(id=6, client_id=2, network_id=2)

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=subscription)
    context.store.clients.get_by_id = AsyncMock(side_effect=lambda i: {1: client, 2: peer}[i])
    context.store.clients.list_subscriptions_by_network = AsyncMock(
        return_value=[subscription, peer_sub]
    )
    context.store.clients.list_blacklisted_client_ids = AsyncMock(return_value=[])
    context.store.clients.add_blacklist = AsyncMock()
    context.store.clients.remove_blacklist = AsyncMock()
    context.store.networks.get_by_id = AsyncMock(return_value=MagicMock(id=2, key="stingers"))

    bot = _bot(context)
    guild.get_role = MagicMock(return_value=client_role)

    open_interaction = make_interaction(guild=guild, user=member)
    view = render_view(
        "subscription_moderation",
        bot,
        subscription_id=subscription.id,
        network_key="stingers",
        show_blacklist=True,
    )
    await _click_label(view, "Blacklist", open_interaction)

    assert open_interaction.followup.send.await_count == 1
    kwargs = open_interaction.followup.send.await_args.kwargs
    assert "block" in str(kwargs.get("content") or "").casefold()
    select_view = kwargs["view"]
    select = next(
        child for child in select_view.children if isinstance(child, discord.ui.Select)
    )
    assert [(opt.label, opt.value) for opt in select.options] == [("PeerCo", "2")]

    submit = make_interaction(guild=guild, user=member)
    submit.data = {"values": ["2"]}
    await select.callback(submit)

    context.store.clients.add_blacklist.assert_awaited_once_with(5, 2)
    assert _user_message(submit) == render_text("blacklist_updated", count="1")


@pytest.mark.asyncio
async def test_subscribe_connected_reports_missing_subscription() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    member = make_member(guild=guild)

    context = MagicMock()
    context.store.clients.get_subscription_by_id = AsyncMock(return_value=None)

    bot = _bot(context)
    interaction = make_interaction(guild=guild, user=member)

    view = render_view(
        "subscribe_setup",
        bot,
        subscription_id=99,
        network_key="stingers",
    )
    await _click_label(view, "Subscribed channel connected", interaction)

    assert _user_message(interaction) == render_text("subscription_not_found")
