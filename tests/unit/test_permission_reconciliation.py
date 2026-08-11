from __future__ import annotations

from itertools import product
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord_helpers import http_50013, make_guild_with_roles, make_role

from bot.core.permissions.service import PermissionContext, PermissionService


def _setup():
    guild, bot, moderator, access, _operator = make_guild_with_roles()
    bot_access = discord.utils.get(guild.roles, name="The Network Bot Access")
    assert bot_access is not None
    context = PermissionContext(guild, bot, access, moderator, bot_access)
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 700
    channel.overwrites = {}
    channel.edit = AsyncMock()
    channel.set_permissions = AsyncMock()
    return guild, bot, moderator, access, bot_access, context, channel


@pytest.mark.asyncio
async def test_reconcile_adds_complete_desired_map() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    desired = {bot_access: discord.PermissionOverwrite(view_channel=True)}
    result = await PermissionService().reconcile(
        channel,
        context,
        desired,
        managed_targets={bot_access},
        reason="test",
    )
    assert result.success and result.changed and result.verified
    assert result.added == (bot_access.name,)
    assert channel.edit.await_args.kwargs["overwrites"] == desired
    assert "sync_permissions" not in channel.edit.await_args.kwargs


@pytest.mark.asyncio
async def test_reconcile_removes_stale_owned_entries_and_preserves_unmanaged() -> None:
    _, bot, _, _, bot_access, context, channel = _setup()
    unrelated = make_role(name="Administrator custom", role_id=88, position=2)
    stale = discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    custom = discord.PermissionOverwrite(send_messages=False)
    desired_bot = discord.PermissionOverwrite(view_channel=True)
    channel.overwrites = {bot: stale, unrelated: custom}
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: desired_bot},
        managed_targets={bot, bot_access},
        reason="test",
    )
    final = channel.edit.await_args.kwargs["overwrites"]
    assert bot not in final
    assert final[bot_access] is desired_bot
    assert final[unrelated] is custom
    assert result.removed == (str(bot.name),)
    assert result.preserved == (unrelated.name,)


@pytest.mark.asyncio
async def test_reconcile_updates_owned_entry_and_is_idempotent() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    desired = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    channel.overwrites = {bot_access: discord.PermissionOverwrite(view_channel=True)}
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: desired},
        managed_targets={bot_access},
        reason="test",
    )
    assert result.updated == (bot_access.name,)
    channel.edit.reset_mock()
    channel.overwrites = {bot_access: desired}
    repeated = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: desired},
        managed_targets={bot_access},
        reason="test",
    )
    assert repeated.success and not repeated.changed and repeated.verified
    channel.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_does_not_mutate_when_role_is_unconfigurable() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    above = make_role(name="Above bot", role_id=99, position=99)
    result = await PermissionService().reconcile(
        channel,
        context,
        {above: discord.PermissionOverwrite(view_channel=True)},
        managed_targets={above, bot_access},
        reason="test",
    )
    assert not result.success
    assert "above the bot" in result.blockers[0]
    channel.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_failure_falls_back_to_incremental_set_permissions() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    channel.edit.side_effect = http_50013()
    desired = discord.PermissionOverwrite(view_channel=True)
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: desired},
        managed_targets={bot_access},
        reason="test",
    )
    assert result.success and result.changed and result.verified
    assert channel.edit.await_count == 1
    channel.set_permissions.assert_awaited_once_with(
        bot_access, overwrite=desired, reason="test"
    )


@pytest.mark.asyncio
async def test_incremental_failure_reports_failure() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    channel.edit.side_effect = http_50013()
    channel.set_permissions.side_effect = http_50013()
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: discord.PermissionOverwrite(view_channel=True)},
        managed_targets={bot_access},
        reason="test",
    )
    assert not result.success and not result.changed
    assert result.failures
    assert channel.edit.await_count == 1
    assert channel.set_permissions.await_count == 1


@pytest.mark.asyncio
async def test_bulk_failure_on_category_uses_incremental() -> None:
    _, _, _, _, bot_access, context, _ = _setup()
    category = MagicMock(spec=discord.CategoryChannel)
    category.id = 701
    category.overwrites = {}
    category.edit = AsyncMock(side_effect=http_50013())
    category.set_permissions = AsyncMock()
    desired = discord.PermissionOverwrite(view_channel=True)
    result = await PermissionService().reconcile(
        category,
        context,
        {bot_access: desired},
        managed_targets={bot_access},
        reason="test",
    )
    assert result.success and result.changed
    category.set_permissions.assert_awaited_once_with(
        bot_access, overwrite=desired, reason="test"
    )


@pytest.mark.asyncio
async def test_reconcile_stress_cleans_every_owned_subset() -> None:
    _, bot, moderator, access, bot_access, context, _ = _setup()
    old_operator = make_role(name="Legacy operator", role_id=77, position=8)
    unrelated = make_role(name="Unmanaged custom", role_id=88, position=2)
    owned = (bot, moderator, access, old_operator, bot_access)
    desired = {bot_access: discord.PermissionOverwrite(view_channel=True)}
    custom = discord.PermissionOverwrite(send_messages=False)
    for present in product((False, True), repeat=len(owned)):
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 800
        channel.edit = AsyncMock()
        channel.set_permissions = AsyncMock()
        current = {
            target: discord.PermissionOverwrite(view_channel=False)
            for target, included in zip(owned, present, strict=True)
            if included
        }
        current[unrelated] = custom
        channel.overwrites = current
        result = await PermissionService().reconcile(
            channel,
            context,
            desired,
            managed_targets=set(owned),
            reason="stress",
        )
        assert result.success
        if channel.edit.await_count:
            final = channel.edit.await_args.kwargs["overwrites"]
            assert set(final) == {bot_access, unrelated}
            assert final[unrelated] is custom


def test_production_permission_mutations_are_confined_to_permission_api() -> None:
    root = Path(__file__).parents[2] / "bot"
    violations: list[str] = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative == "core/permissions/service.py" or relative.startswith("smoke/"):
            continue
        if relative == "core/permissions/probe.py":
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in (".set_permissions(", "sync_permissions=True", "edit(overwrites="):
            if forbidden in source:
                violations.append(f"{relative}: {forbidden}")
    assert violations == []
