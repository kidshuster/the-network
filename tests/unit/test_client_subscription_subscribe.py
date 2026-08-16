from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import make_guild_with_roles
from subscription_helpers import make_client_subscription

from bot.core.models.client import Client
from bot.features.recipes.hub.clients.subscription import ClientSubscriptionService


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


@pytest.mark.asyncio
async def test_subscribe_client_returns_existing_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, _, _, _ = make_guild_with_roles()
    client = _client()
    existing = make_client_subscription(id=5)
    client_repo = MagicMock()
    client_repo.get_subscription = AsyncMock(return_value=existing)
    network_repo = MagicMock()

    service = ClientSubscriptionService()
    result = await service.subscribe_client(
        guild,
        bot,
        client=client,
        network_id=2,
        network_key="stingers",
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    assert result.success is True
    assert result.created is False
    assert result.subscription is existing


@pytest.mark.asyncio
async def test_subscribe_client_creates_missing_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20, position=1)
    client_role.is_default.return_value = False
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.channels = []

    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(return_value=category)

    publish = MagicMock(spec=discord.TextChannel, id=100)
    subscribe = MagicMock(spec=discord.TextChannel, id=101)

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_access_role",
        MagicMock(return_value=access),
    )
    from bot.features.channels.layout.applier import BatchApplyResult, ResourceApplyResult

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[
                    ResourceApplyResult("publish", True, channel=publish),
                    ResourceApplyResult("subscribe", True, channel=subscribe),
                ]
            )
        ),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.reorder_client_category_channels",
        AsyncMock(),
    )

    created_sub = make_client_subscription(id=5)
    client_repo = MagicMock()
    client_repo.get_subscription = AsyncMock(return_value=None)
    client_repo.create_subscription = AsyncMock(return_value=created_sub)
    network_repo = MagicMock()

    service = ClientSubscriptionService()
    result = await service.subscribe_client(
        guild,
        bot,
        client=client,
        network_id=2,
        network_key="stingers",
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    assert result.success is True
    assert result.created is True
    client_repo.create_subscription.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscribe_client_read_only_skips_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, _ = make_guild_with_roles()
    client = _client()
    client = Client(
        id=client.id,
        guild_id=client.guild_id,
        server_name=client.server_name,
        display_name=client.display_name,
        category_id=client.category_id,
        client_role_id=client.client_role_id,
        profile_channel_id=client.profile_channel_id,
        profile_message_id=client.profile_message_id,
        enabled=client.enabled,
        timecode_enabled=client.timecode_enabled,
        read_only=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )
    client_role = MagicMock(spec=discord.Role, id=20, position=1)
    client_role.is_default.return_value = False
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.channels = []

    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(return_value=category)

    subscribe = MagicMock(spec=discord.TextChannel, id=101)

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_access_role",
        MagicMock(return_value=access),
    )
    from bot.features.channels.layout.applier import BatchApplyResult, ResourceApplyResult

    apply_layout = AsyncMock(
        return_value=BatchApplyResult(
            results=[ResourceApplyResult("subscribe", True, channel=subscribe)]
        )
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.apply_layout",
        apply_layout,
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.reorder_client_category_channels",
        AsyncMock(),
    )

    created_sub = make_client_subscription(id=5, publish_channel_id=None)
    client_repo = MagicMock()
    client_repo.get_subscription = AsyncMock(return_value=None)
    client_repo.create_subscription = AsyncMock(return_value=created_sub)
    network_repo = MagicMock()

    service = ClientSubscriptionService()
    result = await service.subscribe_client(
        guild,
        bot,
        client=client,
        network_id=2,
        network_key="stingers",
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    assert result.success is True
    assert result.created is True
    kwargs = client_repo.create_subscription.await_args.kwargs
    assert kwargs["publish_channel_id"] is None
    assert kwargs["subscribe_channel_id"] == 101
    resources = apply_layout.await_args.args[1]
    assert "publish" not in {resource.id for resource in resources}
    assert "subscribe" in {resource.id for resource in resources}


@pytest.mark.asyncio
async def test_subscribe_client_rolls_back_on_second_channel_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access, _ = make_guild_with_roles()
    client = _client()
    client_role = MagicMock(spec=discord.Role, id=20, position=1)
    client_role.is_default.return_value = False
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    category.channels = []

    guild.get_role = MagicMock(return_value=client_role)
    guild.get_channel = MagicMock(return_value=category)

    publish = MagicMock(spec=discord.TextChannel, id=100)
    publish.delete = AsyncMock()

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_access_role",
        MagicMock(return_value=access),
    )

    from bot.features.channels.layout.applier import BatchApplyResult, ResourceApplyResult

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.apply_layout",
        AsyncMock(
            return_value=BatchApplyResult(
                results=[
                    ResourceApplyResult("publish", True, channel=publish),
                    ResourceApplyResult("subscribe", False, detail="Missing Permissions"),
                ]
            )
        ),
    )

    client_repo = MagicMock()
    client_repo.get_subscription = AsyncMock(return_value=None)
    network_repo = MagicMock()

    service = ClientSubscriptionService()
    result = await service.subscribe_client(
        guild,
        bot,
        client=client,
        network_id=2,
        network_key="stingers",
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    assert result.success is False
    assert result.error is not None
    publish.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscribe_client_fails_when_client_role_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, _, access, _ = make_guild_with_roles()
    client = _client()
    category = MagicMock(spec=discord.CategoryChannel, id=10)
    guild.get_role = MagicMock(return_value=None)
    guild.fetch_role = AsyncMock(side_effect=discord.NotFound(MagicMock(), ""))
    guild.get_channel = MagicMock(return_value=category)

    monkeypatch.setattr(
        "bot.features.recipes.hub.clients.subscription.resolve_access_role",
        MagicMock(return_value=access),
    )

    client_repo = MagicMock()
    client_repo.get_subscription = AsyncMock(return_value=None)
    network_repo = MagicMock()

    service = ClientSubscriptionService()
    result = await service.subscribe_client(
        guild,
        bot,
        client=client,
        network_id=2,
        network_key="stingers",
        client_repo=client_repo,
        network_repo=network_repo,
        access_role_name="The Network",
    )

    assert result.success is False
    assert "Client role" in (result.error or "")
