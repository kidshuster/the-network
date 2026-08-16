from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord_helpers import make_guild_with_roles
from subscription_helpers import make_client_subscription

from bot.core.models.client import Client
from bot.features.recipes.hub.clients.subscription import (
    ensure_client_publish_channels,
    strip_client_publish_channels,
)


def _client(*, read_only: bool = False) -> Client:
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
        timecode_enabled=True,
        read_only=read_only,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )


@pytest.mark.asyncio
async def test_strip_client_publish_channels_deletes_and_clears_ids() -> None:
    guild, _, _, _, _ = make_guild_with_roles()
    client = _client(read_only=True)
    subscription = make_client_subscription(id=5, publish_channel_id=201)

    publish = MagicMock(spec=discord.TextChannel, id=201)
    publish.webhooks = AsyncMock(return_value=[])
    publish.delete = AsyncMock()
    guild.get_channel = MagicMock(return_value=publish)

    client_repo = MagicMock()
    client_repo.list_subscriptions_by_client = AsyncMock(return_value=[subscription])
    client_repo.update_publish_setup_message_id = AsyncMock(return_value=subscription)
    client_repo.update_publish_channel_id = AsyncMock(
        return_value=make_client_subscription(id=5, publish_channel_id=None)
    )

    await strip_client_publish_channels(guild, client=client, client_repo=client_repo)

    publish.delete.assert_awaited_once()
    client_repo.update_publish_setup_message_id.assert_awaited_once_with(5, None)
    client_repo.update_publish_channel_id.assert_awaited_once_with(5, None)


@pytest.mark.asyncio
async def test_ensure_client_publish_channels_creates_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, _ = make_guild_with_roles()
    client = _client(read_only=False)
    subscription = make_client_subscription(id=5, publish_channel_id=None)

    client_role = MagicMock(spec=discord.Role, id=20, position=1)
    client_role.is_default.return_value = False
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.channels = []
    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(return_value=category)

    publish = MagicMock(spec=discord.TextChannel, id=777)
    from bot.features.channels.layout.applier import BatchApplyResult, ResourceApplyResult

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_access_role",
        MagicMock(return_value=access),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[ResourceApplyResult("publish", True, channel=publish)]
            )
        ),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.reorder_client_category_channels",
        AsyncMock(),
    )

    client_repo = MagicMock()
    client_repo.list_subscriptions_by_client = AsyncMock(return_value=[subscription])
    client_repo.update_publish_channel_id = AsyncMock(
        return_value=make_client_subscription(id=5, publish_channel_id=777)
    )
    network_repo = MagicMock()

    await ensure_client_publish_channels(
        guild,
        bot,
        client=client,
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    client_repo.update_publish_channel_id.assert_awaited_once_with(5, 777)


@pytest.mark.asyncio
async def test_toggle_read_only_recipe_strips_then_ensures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from bot.features.recipes.client import toggle_client_read_only

    guild, bot_member, _, _, _ = make_guild_with_roles()
    guild.me = bot_member
    client = _client(read_only=False)
    updated_ro = _client(read_only=True)
    restored = _client(read_only=False)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 1

    store_clients = MagicMock()
    store_clients.get_by_id = AsyncMock(side_effect=[client, updated_ro, restored])
    store_clients.set_read_only = AsyncMock(return_value=updated_ro)
    store_clients.list_subscriptions_by_client = AsyncMock(return_value=[])

    recipe_context = SimpleNamespace(
        bot=SimpleNamespace(
            settings=SimpleNamespace(network_access_role_name="The Network", guild_id=100)
        ),
        core=SimpleNamespace(
            store=SimpleNamespace(clients=store_clients, networks=MagicMock()),
            refresh_client_counts=AsyncMock(),
        ),
    )

    monkeypatch.setattr(
        "bot.features.recipes.client.interaction_guild",
        MagicMock(return_value=guild),
    )
    monkeypatch.setattr(
        "bot.features.recipes.client.interaction_actor",
        MagicMock(return_value=interaction.user),
    )
    monkeypatch.setattr(
        "bot.features.recipes.client.require_client_member",
        MagicMock(),
    )
    monkeypatch.setattr(
        "bot.features.recipes.client.interaction_view_registry",
        MagicMock(return_value=MagicMock()),
    )
    strip = AsyncMock()
    ensure = AsyncMock()
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.strip_client_publish_channels",
        strip,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.ensure_client_publish_channels",
        ensure,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.profile_sync.refresh_client_profile_message",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.features.channels.stickies.subscription.sync_subscription_setup",
        AsyncMock(),
    )

    with patch(
        "bot.features.recipes.client._require_client",
        AsyncMock(side_effect=[client, updated_ro]),
    ):
        result = await toggle_client_read_only(
            recipe_context,  # type: ignore[arg-type]
            interaction=interaction,
            client_id=1,
        )

    assert result.read_only is True
    strip.assert_awaited_once()
    ensure.assert_not_awaited()
