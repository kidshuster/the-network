from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.services.guild_permissions import sync_channel_permission_overwrites


def test_client_approval_grants_leaders_channel_access() -> None:
    """New clients created via join-request approval should sync Leaders access immediately."""
    from bot.services.server_request_service import ServerRequestService

    source = inspect.getsource(ServerRequestService.approve_request)
    assert "grant_leaders_channel_access" in source


def test_guild_init_syncs_leaders_for_all_client_roles() -> None:
    """Server init re-syncs Leaders permissions for every stored client role."""
    from bot.services.guild_init import initialize_guild

    source = inspect.getsource(initialize_guild)
    assert "ensure_leaders_channels" in source


async def test_sync_channel_permission_overwrites_refreshes_from_category() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.category_id = 100
    channel.permissions_synced = False
    channel.edit = AsyncMock()
    channel.set_permissions = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 101
    client_role.position = 1
    client_role.is_default.return_value = False

    overwrite = discord.PermissionOverwrite(view_channel=True)

    await sync_channel_permission_overwrites(
        channel,
        bot_member,
        {client_role: overwrite},
        reason="test",
    )

    assert channel.edit.await_count >= 2
    edit_kwargs = [call.kwargs for call in channel.edit.await_args_list]
    assert any(kwargs.get("sync_permissions") is True for kwargs in edit_kwargs)
    assert any(kwargs.get("sync_permissions") is False for kwargs in edit_kwargs)
    channel.set_permissions.assert_awaited_once_with(
        client_role,
        overwrite=overwrite,
        reason="test",
    )


async def test_grant_leaders_channel_access_sets_permissions_on_existing_channels() -> None:
    from bot.domain.client import Client
    from bot.services.leaders_channel import grant_leaders_channel_access

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 500
    category.name = "Leaders"
    category.edit = AsyncMock()

    leaders = MagicMock(spec=discord.TextChannel)
    leaders.id = 501
    leaders.name = "leaders-channel"
    leaders.category_id = category.id
    leaders.edit = AsyncMock()
    leaders.set_permissions = AsyncMock()

    changelog = MagicMock(spec=discord.TextChannel)
    changelog.id = 502
    changelog.name = "changelog"
    changelog.category_id = category.id
    changelog.edit = AsyncMock()
    changelog.set_permissions = AsyncMock()

    category.channels = [leaders, changelog]

    existing_role = MagicMock(spec=discord.Role)
    existing_role.id = 100
    existing_role.position = 1
    existing_role.is_default.return_value = False

    new_role = MagicMock(spec=discord.Role)
    new_role.id = 101
    new_role.position = 2
    new_role.is_default.return_value = False

    access = MagicMock(spec=discord.Role)
    access.id = 200
    access.name = "Network Access"
    access.position = 5
    access.is_default.return_value = False

    operator = MagicMock(spec=discord.Role)
    operator.id = 302
    operator.position = 9
    operator.is_default.return_value = False

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 20

    guild.categories = [category]
    guild.text_channels = [leaders, changelog]
    guild.get_role = MagicMock(
        side_effect=lambda role_id: {
            100: existing_role,
            101: new_role,
        }.get(role_id),
    )

    client = Client(
        id=1,
        guild_id=1,
        server_name="Acme",
        display_name="Acme",
        category_id=900,
        client_role_id=100,
        profile_channel_id=30,
        profile_message_id=40,
        enabled=True,
        emoji_id=None,
        emoji_name=None,
        image_hash=None,
        degraded_reason=None,
        timecode_enabled=False,
    )

    context = MagicMock()
    context.client_repo.list_all = AsyncMock(return_value=[client])
    context.settings_repo.get = AsyncMock(return_value=None)

    import bot.services.guild_layout as guild_layout
    import bot.services.leaders_channel as leaders_module
    import bot.services.network_provision as network_provision

    originals = {
        "resolve_leaders_category": leaders_module.resolve_leaders_category,
        "resolve_leaders_channel": leaders_module.resolve_leaders_channel,
        "resolve_changelog_channel": leaders_module.resolve_changelog_channel,
        "resolve_access_role": network_provision.resolve_access_role,
        "resolve_operator_role_by_name": network_provision.resolve_operator_role_by_name,
        "resolve_human_moderator_role": guild_layout.resolve_human_moderator_role,
    }

    leaders_module.resolve_leaders_category = MagicMock(return_value=category)
    leaders_module.resolve_leaders_channel = MagicMock(return_value=leaders)
    leaders_module.resolve_changelog_channel = MagicMock(return_value=changelog)
    network_provision.resolve_access_role = MagicMock(return_value=access)
    network_provision.resolve_operator_role_by_name = MagicMock(return_value=operator)
    guild_layout.resolve_human_moderator_role = MagicMock(return_value=None)

    try:
        await grant_leaders_channel_access(
            guild,
            bot_member,
            context,
            new_role,
            access_role_name="Network Access",
            operator_role_name="The Network+",
        )
    finally:
        leaders_module.resolve_leaders_category = originals["resolve_leaders_category"]
        leaders_module.resolve_leaders_channel = originals["resolve_leaders_channel"]
        leaders_module.resolve_changelog_channel = originals["resolve_changelog_channel"]
        network_provision.resolve_access_role = originals["resolve_access_role"]
        network_provision.resolve_operator_role_by_name = originals[
            "resolve_operator_role_by_name"
        ]
        guild_layout.resolve_human_moderator_role = originals["resolve_human_moderator_role"]

    leaders_targets = [
        call.args[0]
        for call in leaders.set_permissions.await_args_list
        if call.args
    ]
    changelog_targets = [
        call.args[0]
        for call in changelog.set_permissions.await_args_list
        if call.args
    ]

    assert existing_role in leaders_targets
    assert new_role in leaders_targets
    assert existing_role in changelog_targets
    assert new_role in changelog_targets
    leaders.edit.assert_awaited()
    changelog.edit.assert_awaited()
