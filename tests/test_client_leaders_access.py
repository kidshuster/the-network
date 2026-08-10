from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from bot.services.guild_permissions import (
    create_text_channel_with_overwrites,
    sync_channel_permission_overwrites,
)


def test_client_approval_grants_leaders_channel_access() -> None:
    """New clients created via join-request approval should sync Leaders access immediately."""
    from bot.services.server_request_service import ServerRequestService

    source = inspect.getsource(ServerRequestService.approve_request)
    assert "grant_leaders_channel_access" in source
    assert "Leaders access sync reported issues" in source


def test_guild_init_syncs_leaders_for_all_client_roles() -> None:
    """Server init re-syncs Leaders permissions for every stored client role."""
    from bot.services.guild_init import initialize_guild

    source = inspect.getsource(initialize_guild)
    assert "ensure_leaders_channels" in source


async def test_create_text_channel_with_overwrites_omits_sync_permissions_kwarg() -> None:
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.category_id = 100
    channel.edit = AsyncMock()
    guild.create_text_channel = AsyncMock(return_value=channel)

    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    guild.default_role = everyone

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10
    bot_member.top_role.id = 50

    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 100

    overwrite = {everyone: discord.PermissionOverwrite(view_channel=False)}

    with (
        patch(
            "bot.services.guild_notifications.ensure_guild_only_mention_notifications",
            new=AsyncMock(),
        ),
        patch(
            "bot.services.guild_permissions.sync_channel_permission_overwrites",
            new=AsyncMock(),
        ) as sync_overwrites,
    ):
        await create_text_channel_with_overwrites(
            guild,
            bot_member,
            name="probe-profile",
            category=category,
            overwrites=overwrite,
            reason="test",
        )

    kwargs = guild.create_text_channel.await_args.kwargs
    assert "sync_permissions" not in kwargs
    assert "overwrites" not in kwargs
    sync_overwrites.assert_awaited_once_with(
        channel,
        bot_member,
        overwrite,
        reason="test",
    )


async def test_sync_channel_permission_overwrites_applies_bulk_edit() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.category_id = 100
    channel.edit = AsyncMock()

    bot_member = MagicMock(spec=discord.Member)
    bot_member.guild_permissions.manage_roles = True
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10
    bot_member.top_role.id = 50

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

    channel.edit.assert_awaited_once_with(
        overwrites={client_role: overwrite},
        sync_permissions=False,
        reason="test",
    )


async def test_sync_channel_permission_overwrites_refreshes_from_category_on_failure() -> None:
    channel = MagicMock(spec=discord.TextChannel)
    channel.category_id = 100
    channel.edit = AsyncMock(
        side_effect=[
            discord.HTTPException(MagicMock(), "Forbidden"),
            None,
            None,
        ]
    )

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock()
    bot_member.top_role.position = 10
    bot_member.top_role.id = 50

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

    assert channel.edit.await_count == 3
    edit_kwargs = [call.kwargs for call in channel.edit.await_args_list]
    assert edit_kwargs[0]["overwrites"] == {client_role: overwrite}
    assert edit_kwargs[1]["sync_permissions"] is True
    assert edit_kwargs[2]["overwrites"] == {client_role: overwrite}
    assert edit_kwargs[2]["sync_permissions"] is False


async def test_apply_client_role_leaders_overwrites_targets_layout_channels() -> None:
    from bot.services.leaders_channel import _apply_client_role_leaders_overwrites

    guild = MagicMock(spec=discord.Guild)
    category = MagicMock(spec=discord.CategoryChannel)
    category.set_permissions = AsyncMock()
    leaders = MagicMock(spec=discord.TextChannel)
    leaders.set_permissions = AsyncMock()
    changelog = MagicMock(spec=discord.TextChannel)
    changelog.set_permissions = AsyncMock()

    client_role = MagicMock(spec=discord.Role)
    client_role.id = 101
    client_role.name = "Client: Acme"
    client_role.position = 2
    client_role.is_default.return_value = False

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock(position=20)

    import bot.services.guild_layout as guild_layout
    import bot.services.leaders_channel as leaders_module

    originals = {
        "resolve_leaders_category": leaders_module.resolve_leaders_category,
        "resolve_leaders_channel": leaders_module.resolve_leaders_channel,
        "resolve_changelog_channel": leaders_module.resolve_changelog_channel,
    }
    leaders_module.resolve_leaders_category = MagicMock(return_value=category)
    leaders_module.resolve_leaders_channel = MagicMock(return_value=leaders)
    leaders_module.resolve_changelog_channel = MagicMock(return_value=changelog)

    try:
        failures = await _apply_client_role_leaders_overwrites(
            guild,
            bot_member,
            client_role,
            reason="test",
        )
    finally:
        leaders_module.resolve_leaders_category = originals["resolve_leaders_category"]
        leaders_module.resolve_leaders_channel = originals["resolve_leaders_channel"]
        leaders_module.resolve_changelog_channel = originals["resolve_changelog_channel"]

    assert failures == []
    category.set_permissions.assert_awaited_once()
    leaders.set_permissions.assert_awaited_once()
    changelog.set_permissions.assert_awaited_once()

    for call in (
        category.set_permissions.await_args,
        leaders.set_permissions.await_args,
        changelog.set_permissions.await_args,
    ):
        assert call is not None
        assert call.args[0] is client_role
        assert call.kwargs["overwrite"].view_channel is True


async def test_apply_client_role_leaders_overwrites_reports_missing_layout() -> None:
    from bot.services.leaders_channel import _apply_client_role_leaders_overwrites

    guild = MagicMock(spec=discord.Guild)
    client_role = MagicMock(spec=discord.Role)
    client_role.id = 101
    client_role.name = "Client: Acme"
    client_role.position = 2
    client_role.is_default.return_value = False

    bot_member = MagicMock(spec=discord.Member)
    bot_member.top_role = MagicMock(position=20)

    import bot.services.leaders_channel as leaders_module

    originals = {
        "resolve_leaders_category": leaders_module.resolve_leaders_category,
        "resolve_leaders_channel": leaders_module.resolve_leaders_channel,
        "resolve_changelog_channel": leaders_module.resolve_changelog_channel,
    }
    leaders_module.resolve_leaders_category = MagicMock(return_value=None)
    leaders_module.resolve_leaders_channel = MagicMock(return_value=None)
    leaders_module.resolve_changelog_channel = MagicMock(return_value=None)

    try:
        failures = await _apply_client_role_leaders_overwrites(
            guild,
            bot_member,
            client_role,
            reason="test",
        )
    finally:
        leaders_module.resolve_leaders_category = originals["resolve_leaders_category"]
        leaders_module.resolve_leaders_channel = originals["resolve_leaders_channel"]
        leaders_module.resolve_changelog_channel = originals["resolve_changelog_channel"]

    assert len(failures) == 3
    assert all("not found" in failure for failure in failures)


async def test_grant_leaders_channel_access_runs_incremental_before_full_resync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bot.services.leaders_channel import LeadersSyncResult, grant_leaders_channel_access

    guild = MagicMock(spec=discord.Guild)
    bot_member = MagicMock(spec=discord.Member)
    client_role = MagicMock(spec=discord.Role, id=101, name="Client: Acme")
    context = MagicMock()

    calls: list[str] = []

    async def _incremental(*_args: object, **_kwargs: object) -> list[str]:
        calls.append("incremental")
        return []

    async def _ensure(*_args: object, **_kwargs: object) -> tuple[None, None, LeadersSyncResult]:
        calls.append("ensure")
        return None, None, LeadersSyncResult(roles_synced=["Client: Acme"])

    monkeypatch.setattr(
        "bot.services.leaders_channel._apply_client_role_leaders_overwrites",
        _incremental,
    )
    monkeypatch.setattr(
        "bot.services.leaders_channel.ensure_leaders_channels",
        _ensure,
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_access_role",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.services.network_provision.resolve_operator_role_by_name",
        MagicMock(return_value=MagicMock(spec=discord.Role)),
    )
    monkeypatch.setattr(
        "bot.services.guild_layout.resolve_human_moderator_role",
        MagicMock(return_value=None),
    )

    result = await grant_leaders_channel_access(
        guild,
        bot_member,
        context,
        client_role,
        access_role_name="The Network",
        operator_role_name="The Network+",
    )

    assert calls == ["incremental", "ensure"]
    assert result.failures == []
    assert result.roles_synced == ["Client: Acme"]


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
    category.set_permissions = AsyncMock()

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
    context.settings_repo.set = AsyncMock()

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
        result = await grant_leaders_channel_access(
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
        call.kwargs["overwrites"]
        for call in leaders.edit.await_args_list
        if call.kwargs.get("overwrites") is not None
    ][-1]
    changelog_targets = [
        call.kwargs["overwrites"]
        for call in changelog.edit.await_args_list
        if call.kwargs.get("overwrites") is not None
    ][-1]

    assert existing_role in leaders_targets
    assert new_role in leaders_targets
    assert existing_role in changelog_targets
    assert new_role in changelog_targets
    assert result.failures == []
    category.set_permissions.assert_awaited()
    leaders.set_permissions.assert_awaited()
    changelog.set_permissions.assert_awaited()
    leaders.edit.assert_awaited()
    changelog.edit.assert_awaited()
