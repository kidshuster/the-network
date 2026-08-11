from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from context_helpers import make_test_context

from bot.config import Settings
from bot.features.recipes.hub.announcements import (
    can_post_hub_announcement,
    dispatch_system_announcement,
    parse_announcement_content,
)


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "100")
    return Settings(_env_file=None)


def test_parse_announcement_defaults_to_all_networks() -> None:
    parsed = parse_announcement_content(
        "Maintenance tonight.", available_keys={"smoke", "stingers"}
    )
    assert parsed.network_keys == ("smoke", "stingers")
    assert parsed.body == "Maintenance tonight."
    assert parsed.error is None


def test_parse_announcement_targets_one_network_and_allows_embed_only() -> None:
    parsed = parse_announcement_content("[stingers]", available_keys={"smoke", "stingers"})
    assert parsed.network_keys == ("stingers",)
    assert parsed.body == ""
    assert parsed.error is None


def test_parse_announcement_rejects_unknown_network() -> None:
    parsed = parse_announcement_content("[missing]\nHello", available_keys={"smoke"})
    assert parsed.error is not None
    assert "Unknown network" in parsed.error


def test_can_post_hub_announcement_allows_operator_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(monkeypatch)
    guild = MagicMock(spec=discord.Guild)
    operator = MagicMock(spec=discord.Role)
    operator.name = settings.network_operator_role_name
    guild.roles = [operator]
    member = MagicMock(spec=discord.Member)
    member.roles = [operator]
    member.guild_permissions.manage_guild = False
    assert can_post_hub_announcement(member, guild, settings)


async def test_dispatch_targets_enabled_networks_without_synthetic_client(
    db,
) -> None:
    context = make_test_context(db)
    await context.store.networks.create(guild_id=100, key="alpha", display_name="Alpha")
    await context.store.networks.create(guild_id=100, key="beta", display_name="Beta")
    context.relay_service.deliver_system_announcement = AsyncMock(
        return_value=MagicMock(success=True, error=None)
    )
    message = MagicMock(spec=discord.Message)
    message.content = "Maintenance tonight."
    message.embeds = []
    message.attachments = []

    result = await dispatch_system_announcement(context, MagicMock(spec=discord.Guild), message)

    assert result.success
    assert result.networks_attempted == ("alpha", "beta")
    assert context.relay_service.deliver_system_announcement.await_count == 2


async def test_dispatch_rejects_empty_message(db) -> None:
    context = make_test_context(db)
    await context.store.networks.create(guild_id=100, key="alpha", display_name="Alpha")
    message = MagicMock(spec=discord.Message)
    message.content = ""
    message.embeds = []
    message.attachments = []

    result = await dispatch_system_announcement(context, MagicMock(spec=discord.Guild), message)

    assert not result.success
    assert result.errors == ("Message is empty.",)
