from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import discord
import pytest
from discord_helpers import http_50013

from bot.domain.client import Client
from bot.hub.init import initialize_guild
from bot.smoke.provision_flow import GuildInitSmokeResult


def _guild_with_roles(
    *,
    access_position: int = 10,
    operator_position: int = 11,
    human_mod_position: int = 4,
) -> tuple[MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.categories = []
    guild.text_channels = []
    guild.channels = []
    guild.rules_channel = None

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    everyone.position = 0
    guild.default_role = everyone

    human_mod = MagicMock(spec=discord.Role, name="Moderator", id=30, position=human_mod_position)
    human_mod.is_default.return_value = False
    access_role = MagicMock(
        spec=discord.Role, name="The Network", id=40, position=access_position
    )
    access_role.is_default.return_value = False
    operator_role = MagicMock(
        spec=discord.Role, name="The Network+", id=50, position=operator_position
    )
    operator_role.is_default.return_value = False
    operator_role.permissions.manage_channels = True
    operator_role.permissions.manage_roles = True
    operator_role.permissions.manage_webhooks = True
    operator_role.permissions.send_messages = True
    operator_role.permissions.embed_links = True
    operator_role.permissions.attach_files = True
    operator_role.permissions.read_message_history = True
    operator_role.permissions.manage_messages = True
    operator_role.permissions.manage_emojis_and_stickers = True

    bot = MagicMock(spec=discord.Member, id=999, roles=[access_role, operator_role])
    bot.top_role = operator_role
    perms = MagicMock()
    perms.manage_channels = True
    perms.manage_roles = True
    perms.manage_webhooks = True
    perms.administrator = False
    type(bot).guild_permissions = PropertyMock(return_value=perms)

    guild.roles = [everyone, human_mod, access_role, operator_role]
    guild.me = bot
    return guild, bot, human_mod, access_role, operator_role


def _patch_init_roles(
    monkeypatch: pytest.MonkeyPatch,
    access_role: MagicMock,
    operator_role: MagicMock,
    human_mod: MagicMock,
) -> None:
    monkeypatch.setattr(
        "bot.hub.init.resolve_access_role_by_name",
        MagicMock(return_value=access_role),
    )
    monkeypatch.setattr(
        "bot.hub.init.resolve_operator_role_by_name",
        MagicMock(return_value=operator_role),
    )
    monkeypatch.setattr(
        "bot.hub.reconcilers.resolve_human_moderator_role",
        MagicMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.hub.init.run_guild_init_smoke_checks",
        AsyncMock(
            return_value=GuildInitSmokeResult(
                operator_steps=("create category", "create text channel"),
                provision_steps=(
                    "create client role",
                    "create client publish channel with webhook overwrites",
                    "create webhook on publish channel as client role",
                ),
            )
        ),
    )
    monkeypatch.setattr(
        "bot.hub.reconcilers._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )


@pytest.mark.asyncio
async def test_initialize_guild_survives_category_sync_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access_role, operator_role = _guild_with_roles()

    existing_category = MagicMock(spec=discord.CategoryChannel)
    existing_category.id = 501
    existing_category.name = "The Network"
    existing_category.channels = []
    existing_category.overwrites = {}
    existing_category.edit = AsyncMock(side_effect=http_50013())

    moderation_category = MagicMock(spec=discord.CategoryChannel)
    moderation_category.id = 502
    moderation_category.name = "Moderation"
    moderation_category.channels = []
    moderation_category.overwrites = {}
    moderation_category.edit = AsyncMock()

    guild.categories = [existing_category, moderation_category]
    guild.text_channels = []
    _patch_init_roles(monkeypatch, access_role, operator_role, human_mod)

    async def fake_create_text_channel(**kwargs: object) -> MagicMock:
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 900
        channel.position = 0
        channel.edit = AsyncMock()
        return channel

    guild.create_text_channel = AsyncMock(side_effect=fake_create_text_channel)
    guild.create_category = AsyncMock(return_value=existing_category)

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    assert result.failed_steps
    assert any("category" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_initialize_guild_fails_without_operator_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access_role, operator_role = _guild_with_roles()
    _patch_init_roles(monkeypatch, access_role, operator_role, human_mod)
    monkeypatch.setattr(
        "bot.hub.init.resolve_operator_role_by_name",
        MagicMock(return_value=None),
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is False
    assert result.reason is not None
    assert "The Network+" in result.reason
    assert "Manage Channels" in result.reason


@pytest.mark.asyncio
async def test_initialize_guild_survives_rules_channel_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access_role, operator_role = _guild_with_roles()

    network_cat = MagicMock(spec=discord.CategoryChannel)
    network_cat.id = 501
    network_cat.name = "The Network"
    network_cat.channels = []

    rules = MagicMock(spec=discord.TextChannel)
    rules.id = 777
    rules.name = "rules"
    rules.mention = "#rules"
    rules.category_id = network_cat.id
    rules.overwrites = {}
    rules.edit = AsyncMock(side_effect=http_50013())
    rules.set_permissions = AsyncMock(side_effect=http_50013())
    guild.rules_channel = rules
    network_cat.channels = [rules]

    subscribe = MagicMock(spec=discord.CategoryChannel)
    subscribe.id = 502
    subscribe.name = "Subscribe To Me!"
    subscribe.channels = []
    subscribe.edit = AsyncMock()
    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.id = 503
    moderation.name = "Moderation"
    moderation.channels = []
    moderation.edit = AsyncMock()
    moderation.overwrites = {}
    network_cat.edit = AsyncMock()
    network_cat.overwrites = {}
    leaders = MagicMock(spec=discord.CategoryChannel)
    leaders.id = 504
    leaders.name = "Leaders"
    leaders.channels = []
    leaders.edit = AsyncMock()
    leaders.overwrites = {}
    guild.categories = [network_cat, moderation, leaders, subscribe]
    guild.text_channels = [rules]
    guild.channels = [*guild.categories, rules]

    _patch_init_roles(monkeypatch, access_role, operator_role, human_mod)
    guild.create_text_channel = AsyncMock(
        side_effect=lambda **kwargs: MagicMock(
            spec=discord.TextChannel,
            id=800,
            name=str(kwargs.get("name", "channel")),
            mention=f"#{kwargs.get('name', 'channel')}",
            category_id=getattr(kwargs.get("category"), "id", None),
            overwrites={},
            edit=AsyncMock(),
        )
    )
    guild.create_category = AsyncMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    assert any("rules" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_initialize_guild_survives_client_category_sync_50013(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guild, bot, human_mod, access_role, operator_role = _guild_with_roles()

    client_role = MagicMock(spec=discord.Role, id=60, name="Client: Alpha", position=1)
    client_role.is_default.return_value = False
    guild.roles.append(client_role)

    client_category = MagicMock(spec=discord.CategoryChannel)
    client_category.id = 600
    client_category.name = "Alpha"
    client_category.overwrites = {}
    client_category.edit = AsyncMock(side_effect=http_50013())
    guild.categories = [client_category]

    for name in ("The Network", "Moderation", "Leaders"):
        cat = MagicMock(spec=discord.CategoryChannel)
        cat.id = id(name)
        cat.name = name
        cat.channels = []
        cat.edit = AsyncMock()
        cat.overwrites = {}
        guild.categories.append(cat)
    guild.text_channels = []

    _patch_init_roles(monkeypatch, access_role, operator_role, human_mod)
    guild.get_role = MagicMock(return_value=client_role)
    guild.create_text_channel = AsyncMock(
        side_effect=lambda **kwargs: MagicMock(
            spec=discord.TextChannel,
            id=800,
            name=str(kwargs.get("name", "channel")),
            mention=f"#{kwargs.get('name', 'channel')}",
            category_id=getattr(kwargs.get("category"), "id", None),
            overwrites={},
            edit=AsyncMock(),
        )
    )
    guild.create_category = AsyncMock()

    client = Client(
        id=1,
        guild_id=100,
        server_name="Alpha",
        display_name="Alpha",
        category_id=600,
        client_role_id=60,
        profile_channel_id=700,
        profile_message_id=701,
        enabled=True,
        timecode_enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
    )

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
        clients=[client],
    )

    assert result.success is True
    assert any("client category" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_initialize_guild_survives_hidden_moderator_only_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-existing #moderator-only the bot cannot see should warn, not abort init."""
    guild, bot, human_mod, access_role, operator_role = _guild_with_roles()

    def _http_50001() -> discord.HTTPException:
        exc = discord.HTTPException(MagicMock(), "Missing Access")
        exc.status = 403
        exc.code = 50001
        return exc

    moderation = MagicMock(spec=discord.CategoryChannel)
    moderation.id = 601
    moderation.name = "Moderation"
    moderation.channels = []
    moderation.edit = AsyncMock()
    network_cat = MagicMock(spec=discord.CategoryChannel)
    network_cat.id = 602
    network_cat.name = "The Network"
    network_cat.channels = []
    network_cat.edit = AsyncMock()
    leaders_cat = MagicMock(spec=discord.CategoryChannel)
    leaders_cat.id = 603
    leaders_cat.name = "Leaders"
    leaders_cat.channels = []
    leaders_cat.edit = AsyncMock()
    guild.categories = [moderation, network_cat, leaders_cat]

    mod_only = MagicMock(spec=discord.TextChannel)
    mod_only.id = 700
    mod_only.name = "moderator-only"
    mod_only.category_id = None
    mod_only.category = None

    async def _raise_missing_access(*_args: object, **_kwargs: object) -> None:
        raise _http_50001()

    mod_only.edit = AsyncMock(side_effect=_raise_missing_access)
    mod_only.permissions_for = MagicMock(
        return_value=MagicMock(view_channel=False, manage_channels=False),
    )
    guild.text_channels = [mod_only]
    guild.channels = guild.categories + guild.text_channels

    _patch_init_roles(monkeypatch, access_role, operator_role, human_mod)
    monkeypatch.setattr(
        "bot.hub.reconcilers._ensure_human_moderator_role",
        AsyncMock(return_value=human_mod),
    )
    monkeypatch.setattr(
        "bot.hub.leaders.ensure_leaders_channels",
        AsyncMock(return_value=(None, None, MagicMock(
            rectification_notes=lambda: [],
            skip_notes=lambda: [],
            failures=[],
        ))),
    )
    monkeypatch.setattr(
        "bot.stickies.join_requests_sticky.sync_hub_join_sticky",
        AsyncMock(return_value=MagicMock(message=None)),
    )
    monkeypatch.setattr(
        "bot.stickies.rules_sticky.sync_rules_sticky",
        AsyncMock(return_value=MagicMock(message=None)),
    )
    for cat in guild.categories:
        cat.overwrites = getattr(cat, "overwrites", {}) or {}
    mod_only.overwrites = {}
    guild.create_text_channel = AsyncMock(
        side_effect=lambda **kwargs: MagicMock(
            spec=discord.TextChannel,
            id=800,
            name=str(kwargs.get("name", "channel")),
            mention=f"#{kwargs.get('name', 'channel')}",
            category_id=getattr(kwargs.get("category"), "id", None),
            overwrites={},
            edit=AsyncMock(),
        ),
    )
    guild.create_category = AsyncMock()

    result = await initialize_guild(
        guild,
        bot,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert result.success is True
    assert any("moderator" in step.casefold() for step in result.failed_steps)


@pytest.mark.asyncio
async def test_reconcile_map_falls_back_when_bulk_channel_edit_fails() -> None:
    from bot.permissions.service import build_context, permission_service

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 1
    channel.category_id = 100
    channel.overwrites = {}
    channel.edit = AsyncMock(
        side_effect=[
            http_50013(),
            None,
            None,
        ]
    )
    channel.set_permissions = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_channels = True
    bot_member.top_role = MagicMock(position=10, id=50)

    client_role = MagicMock(spec=discord.Role, id=101, position=1)
    client_role.is_default.return_value = False
    overwrite = discord.PermissionOverwrite(view_channel=True)

    sync = await permission_service.reconcile_map(
        channel,
        build_context(
            MagicMock(spec=discord.Guild),
            bot_member,
            access_role=None,
            moderator_role=None,
        ),
        {client_role: overwrite},
        reason="The Network guild init",
    )

    assert sync.success is True
    assert channel.edit.await_count == 3
    channel.set_permissions.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_map_falls_back_to_incremental_set_permissions() -> None:
    from bot.permissions.service import build_context, permission_service

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 1
    channel.category_id = 100
    channel.overwrites = {}
    channel.edit = AsyncMock(
        side_effect=[
            http_50013(),
            None,
            http_50013(),
        ]
    )
    channel.set_permissions = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_channels = True
    bot_member.top_role = MagicMock(position=10, id=50)

    client_role = MagicMock(spec=discord.Role, id=101, position=1)
    client_role.is_default.return_value = False
    overwrite = discord.PermissionOverwrite(view_channel=True)

    sync = await permission_service.reconcile_map(
        channel,
        build_context(
            MagicMock(spec=discord.Guild),
            bot_member,
            access_role=None,
            moderator_role=None,
        ),
        {client_role: overwrite},
        reason="The Network guild init",
    )

    assert sync.success is True
    channel.set_permissions.assert_awaited_once_with(
        client_role,
        overwrite=overwrite,
        reason="The Network guild init",
    )


def test_moderator_category_overwrite_has_no_thread_flags() -> None:
    from bot.layout import preset_overwrite

    category = preset_overwrite("moderator_staff_category")
    channel = preset_overwrite("moderator_staff")
    assert category.create_public_threads is not True
    assert channel.create_public_threads is True


def test_everyone_readonly_category_overwrite_has_no_thread_flags() -> None:
    from bot.layout import preset_overwrite

    category = preset_overwrite("everyone_readonly_category")
    channel = preset_overwrite("everyone_readonly")
    assert category.create_public_threads is not True
    assert channel.create_public_threads is False
