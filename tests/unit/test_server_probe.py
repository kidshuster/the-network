from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest
from discord_helpers import make_guild_with_roles, make_role

from bot.channels.layout.managed import hub_category_name, hub_channel_name
from bot.channels.resolve import (
    HUB_CATEGORY_LEADERS,
    HUB_CATEGORY_MODERATION,
    HUB_CATEGORY_NETWORK,
    HUB_CHANNEL_CHANGELOG,
    HUB_CHANNEL_COMMANDS,
    HUB_CHANNEL_JOIN_REQUESTS,
    HUB_CHANNEL_JOIN_THE_NETWORK,
    HUB_CHANNEL_LEADERS,
    HUB_CHANNEL_MODERATOR_ONLY,
    HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
    HUB_CHANNEL_RULES,
)
from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
from bot.core.hub.probe import run_server_probe
from bot.widgets.presenters import server_probe_embed


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        network_access_role_name="The Network",
        network_operator_role_name="The Network+",
    )


def _text_channel(
    *,
    channel_id: int,
    name: str,
    category: MagicMock | None,
    view: bool = True,
    news: bool = False,
) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.name = name
    channel.mention = f"#{name}"
    channel.category = category
    channel.category_id = None if category is None else category.id
    channel.is_news = MagicMock(return_value=news)
    perms = MagicMock()
    perms.view_channel = view
    channel.permissions_for = MagicMock(return_value=perms)
    channel.overwrites_for = MagicMock(
        return_value=discord.PermissionOverwrite(view_channel=True if view else False)
    )
    return channel


def _ready_guild() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild, bot, moderator, access, operator = make_guild_with_roles()
    bot_access = discord.utils.get(guild.roles, name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME)
    assert bot_access is not None
    bot.roles = [access, bot_access, operator]
    bot.top_role = operator
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.manage_webhooks = True
    perms.manage_guild = True
    perms.administrator = False
    type(bot).guild_permissions = PropertyMock(return_value=perms)

    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.id = 1
    moderation.name = hub_category_name(HUB_CATEGORY_MODERATION)
    network = MagicMock(spec=discord.CategoryChannel)
    network.id = 2
    network.name = hub_category_name(HUB_CATEGORY_NETWORK)
    leaders = MagicMock(spec=discord.CategoryChannel)
    leaders.id = 3
    leaders.name = hub_category_name(HUB_CATEGORY_LEADERS)
    for category in (moderation, network, leaders):
        category.overwrites_for = MagicMock(
            return_value=discord.PermissionOverwrite(view_channel=True)
        )
        category.permissions_for = MagicMock(
            return_value=MagicMock(view_channel=True)
        )

    channels = [
        _text_channel(
            channel_id=10,
            name=hub_channel_name(HUB_CHANNEL_MODERATOR_ONLY),
            category=moderation,
        ),
        _text_channel(
            channel_id=11,
            name=hub_channel_name(HUB_CHANNEL_JOIN_REQUESTS),
            category=moderation,
        ),
        _text_channel(
            channel_id=12,
            name=hub_channel_name(HUB_CHANNEL_COMMANDS),
            category=moderation,
        ),
        _text_channel(
            channel_id=13,
            name=hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS),
            category=moderation,
        ),
        _text_channel(
            channel_id=20,
            name=hub_channel_name(HUB_CHANNEL_RULES),
            category=network,
        ),
        _text_channel(
            channel_id=21,
            name=hub_channel_name(HUB_CHANNEL_JOIN_THE_NETWORK),
            category=network,
        ),
        _text_channel(
            channel_id=30,
            name=hub_channel_name(HUB_CHANNEL_LEADERS),
            category=leaders,
        ),
        _text_channel(
            channel_id=31,
            name=hub_channel_name(HUB_CHANNEL_CHANGELOG),
            category=leaders,
        ),
    ]
    guild.categories = [moderation, network, leaders]
    guild.text_channels = channels
    guild.rules_channel = channels[4]
    guild.public_updates_channel = channels[0]
    return guild, bot, moderator, access, operator


@pytest.mark.asyncio
async def test_run_server_probe_passes_on_healthy_hub() -> None:
    guild, bot, _mod, _access, _operator = _ready_guild()
    store = SimpleNamespace(clients=SimpleNamespace(list_all=AsyncMock(return_value=[])))
    context = SimpleNamespace(store=store)

    report = await run_server_probe(guild, bot, settings=_settings(), context=context)

    assert report.passed
    assert {check.name for check in report.checks} >= {
        "operator setup",
        "bot access role",
        "hub layout",
        "community slots",
        "bot channel access",
        "announcements channel",
        "leaders access",
    }
    embed = server_probe_embed(report)
    assert "passed" in (embed.description or "").casefold()
    assert embed.colour == discord.Colour.green()


@pytest.mark.asyncio
async def test_run_server_probe_reports_community_and_access_failures() -> None:
    guild, bot, _mod, _access, _operator = _ready_guild()
    guild.rules_channel = None
    guild.public_updates_channel = None
    for channel in guild.text_channels:
        if channel.name == hub_channel_name(HUB_CHANNEL_COMMANDS):
            channel.permissions_for = MagicMock(
                return_value=MagicMock(view_channel=False)
            )
            channel.overwrites_for = MagicMock(
                return_value=discord.PermissionOverwrite(view_channel=False)
            )

    client_role = make_role(name="Client: Alpha", role_id=90, position=2)
    guild.roles.append(client_role)
    guild.get_role = MagicMock(side_effect=lambda role_id: client_role if role_id == 90 else None)
    store = SimpleNamespace(
        clients=SimpleNamespace(
            list_all=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        guild_id=guild.id,
                        client_role_id=90,
                        server_name="Alpha",
                    )
                ]
            )
        )
    )
    # Leaders category denies the client role.
    leaders_cat = next(
        cat for cat in guild.categories if cat.name == hub_category_name(HUB_CATEGORY_LEADERS)
    )
    leaders_cat.overwrites_for = MagicMock(
        return_value=discord.PermissionOverwrite(view_channel=False)
    )
    leaders_cat.permissions_for = MagicMock(return_value=MagicMock(view_channel=False))

    report = await run_server_probe(
        guild, bot, settings=_settings(), context=SimpleNamespace(store=store)
    )

    assert not report.passed
    failed_names = {check.name for check in report.failed_checks}
    assert "community slots" in failed_names
    assert "bot channel access" in failed_names
    assert "leaders access" in failed_names
    embed = server_probe_embed(report)
    assert embed.colour == discord.Colour.gold()
    assert any(field.name == "Failed" for field in embed.fields)
