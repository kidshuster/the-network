from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.config import Settings
from bot.constants import RelayStatus
from bot.db.repositories import NetworkRepository, ProfileRepository, RelayRecordRepository
from bot.domain.profile import ServerProfile
from bot.services.profile_cache import ProfileCache
from bot.services.relay_service import RelayService
from bot.services.routing_service import RoutingService


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    monkeypatch.setenv("MANUAL_RELAY_ENABLED", "false")
    return Settings(_env_file=None)


async def _seed_network_profile(
    db,
    *,
    network_enabled: bool = True,
    profile_enabled: bool = True,
) -> tuple[ServerProfile, int]:
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    network = await network_repo.create(
        guild_id=100,
        key="stingers",
        display_name="Stingers",
        feed_category_id=10,
        output_channel_id=500,
        concat_channel_id=501,
    )
    if not network_enabled:
        await network_repo.set_enabled("stingers", False)

    await profile_repo.upsert(
        guild_id=100,
        profile_thread_id=301,
        profile_starter_message_id=302,
        source_channel_id=201,
        network_id=network.id,
        server_name="partner",
        display_name="Partner",
        enabled=profile_enabled,
    )
    await profile_repo.update_emoji_fields(
        301,
        emoji_id=888,
        emoji_name="net_partner_123456",
        image_hash="hash",
        degraded_reason=None,
    )
    updated = await profile_repo.get_by_thread_id(301)
    assert updated is not None
    return updated, network.output_channel_id


def _make_webhook_message(
    *,
    message_id: int = 1001,
    channel_id: int = 201,
    content: str = "Raid starts at 8 PM.",
    author_name: str = "Original Username",
    webhook_id: int = 777,
) -> discord.Message:
    message = MagicMock(spec=discord.Message)
    message.id = message_id
    message.content = content
    message.webhook_id = webhook_id
    message.embeds = []
    message.attachments = []

    author = MagicMock()
    author.name = author_name
    author.display_name = author_name
    author.bot = False
    message.author = author

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    message.channel = channel

    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    message.guild = guild
    return message


async def _build_service(
    db,
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings | None = None,
) -> RelayService:
    settings = settings or _settings(monkeypatch)
    network_repo = NetworkRepository(db)
    profile_repo = ProfileRepository(db)
    relay_record_repo = RelayRecordRepository(db)
    routing = RoutingService(network_repo)
    await routing.load_cache()
    profile_cache = ProfileCache(profile_repo)
    await profile_cache.load_cache()
    return RelayService(settings, routing, profile_cache, relay_record_repo)


@pytest.mark.asyncio
async def test_end_to_end_webhook_relay(db, monkeypatch: pytest.MonkeyPatch) -> None:
    profile, output_channel_id = await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is not None
    assert result.success is True
    assert result.destination_message_ids == (9001,)
    assert result.published_message_ids == (9001,)

    send_kwargs = output_channel.send.await_args.kwargs
    allowed = send_kwargs["allowed_mentions"]
    assert isinstance(allowed, discord.AllowedMentions)
    assert allowed.everyone is False and allowed.users is False and allowed.roles is False
    embed = send_kwargs["embed"]
    assert embed.author.name == "Partner"
    assert embed.author.icon_url == "https://cdn.discordapp.com/emojis/888.png?size=128"
    assert embed.description == "Raid starts at 8 PM."
    assert send_kwargs.get("content") in (None, "")
    sent.publish.assert_awaited_once()

    relay_repo = RelayRecordRepository(db)
    record = await relay_repo.get_by_source_message(message.id)
    assert record is not None
    assert record.status == RelayStatus.PUBLISHED
    assert record.profile_id == profile.id


@pytest.mark.asyncio
async def test_transform_header_and_content(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message(content="Line one")

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 42
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    await service.relay_message(message)

    embed = output_channel.send.await_args.kwargs["embed"]
    assert embed.author.name == "Partner"
    assert embed.description == "Line one"


@pytest.mark.asyncio
async def test_duplicate_source_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    first = await service.relay_message(message)
    second = await service.relay_message(message)

    assert first is not None
    assert second is None
    assert output_channel.send.await_count == 1


@pytest.mark.asyncio
async def test_disabled_profile_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db, profile_enabled=False)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    output_channel.send = AsyncMock()
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is None
    output_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_network_ignored(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db, network_enabled=False)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    output_channel.send = AsyncMock()
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is None
    output_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_publish_status(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001

    async def fail_publish() -> None:
        exc = discord.HTTPException(MagicMock(), "publish failed")
        exc.status = 403
        raise exc

    sent.publish = AsyncMock(side_effect=fail_publish)
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is not None
    assert result.success is False
    relay_repo = RelayRecordRepository(db)
    record = await relay_repo.get_by_source_message(message.id)
    assert record is not None
    assert record.status == RelayStatus.FAILED_PUBLISH
    assert record.destination_message_ids == (9001,)


@pytest.mark.asyncio
async def test_status_pending_sent_published(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()

    statuses: list[RelayStatus] = []

    original_create = service._relay_records.create_pending
    original_update = service._relay_records.update_status

    async def track_create(**kwargs: object):
        record = await original_create(**kwargs)
        statuses.append(record.status)
        return record

    async def track_update(record_id: int, **kwargs: object):
        record = await original_update(record_id, **kwargs)
        statuses.append(record.status)
        return record

    service._relay_records.create_pending = track_create  # type: ignore[method-assign]
    service._relay_records.update_status = track_update  # type: ignore[method-assign]

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9001
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    await service.relay_message(message)

    assert statuses == [
        RelayStatus.PENDING,
        RelayStatus.SENT,
        RelayStatus.PUBLISHED,
    ]


@pytest.mark.asyncio
async def test_create_pending_record_before_send(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    relay_repo = RelayRecordRepository(db)
    message = _make_webhook_message()

    pending_before_send: list[bool] = []

    output_channel = MagicMock(spec=discord.TextChannel)

    async def send_and_track(**kwargs: object) -> discord.Message:
        record = await relay_repo.get_by_source_message(message.id)
        pending_before_send.append(record is not None and record.status == RelayStatus.PENDING)
        sent = MagicMock(spec=discord.Message)
        sent.id = 9001
        sent.publish = AsyncMock()
        return sent

    output_channel.send = AsyncMock(side_effect=send_and_track)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    await service.relay_message(message)

    assert pending_before_send == [True]


@pytest.mark.asyncio
async def test_non_webhook_ignored_without_manual_relay(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message()
    message.webhook_id = None

    output_channel = MagicMock(spec=discord.TextChannel)
    output_channel.send = AsyncMock()
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is None
    output_channel.send.assert_not_awaited()
    assert service.feed_reject_reason(message) is not None


@pytest.mark.asyncio
async def test_embed_only_webhook_relay(db, monkeypatch: pytest.MonkeyPatch) -> None:
    await _seed_network_profile(db)
    service = await _build_service(db, monkeypatch)
    message = _make_webhook_message(content="")
    embed = MagicMock()
    embed.title = "Raid tonight"
    embed.description = "Meet at 8 PM."
    embed.fields = []
    message.embeds = [embed]

    output_channel = MagicMock(spec=discord.TextChannel)
    sent = MagicMock(spec=discord.Message)
    sent.id = 9002
    sent.publish = AsyncMock()
    output_channel.send = AsyncMock(return_value=sent)
    message.guild.get_channel = MagicMock(return_value=output_channel)

    result = await service.relay_message(message)

    assert result is not None
    assert result.success is True
    content = output_channel.send.await_args.kwargs["embed"].description
    assert "Raid tonight" in content
    assert "Meet at 8 PM." in content
