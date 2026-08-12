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
    channel.permissions_for = MagicMock(
        return_value=MagicMock(
            view_channel=True,
            manage_channels=True,
            manage_roles=True,
        )
    )
    return guild, bot, moderator, access, bot_access, context, channel


def _bot_access_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        manage_channels=True,
    )


@pytest.mark.asyncio
async def test_reconcile_clamps_bits_bot_lacks_on_channel() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    channel.permissions_for = MagicMock(
        return_value=MagicMock(
            view_channel=True,
            manage_channels=True,
            manage_roles=True,
            send_messages=True,
            add_reactions=False,
            create_public_threads=False,
        )
    )
    client = make_role(name="Client: Example", role_id=55, position=1)
    desired = {
        bot_access: _bot_access_overwrite(),
        client: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=False,
            add_reactions=False,
            create_public_threads=False,
        ),
    }
    result = await PermissionService().reconcile(
        channel,
        context,
        desired,
        managed_targets={bot_access, client},
        reason="test",
    )
    assert result.success
    final = channel.edit.await_args.kwargs["overwrites"]
    client_ow = final[client]
    assert client_ow.view_channel is True
    assert client_ow.send_messages is False
    assert client_ow.add_reactions is None
    assert client_ow.create_public_threads is None


@pytest.mark.asyncio
async def test_reconcile_adds_complete_desired_map() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    desired = {bot_access: _bot_access_overwrite()}
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
    stale = discord.PermissionOverwrite(
        view_channel=True, manage_channels=True
    )
    custom = discord.PermissionOverwrite(send_messages=False)
    desired_bot = _bot_access_overwrite()
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
    assert final[bot_access].pair() == desired_bot.pair()
    assert final[unrelated] is custom
    assert result.removed == (str(bot.name),)
    assert result.preserved == (unrelated.name,)


@pytest.mark.asyncio
async def test_reconcile_updates_owned_entry_and_is_idempotent() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    desired = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, manage_channels=True
    )
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
async def test_bulk_failure_falls_back_to_targeted_permission_updates() -> None:
    _, _, _, _, bot_access, context, channel = _setup()
    channel.edit.side_effect = http_50013()
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: _bot_access_overwrite()},
        managed_targets={bot_access},
        reason="test",
    )
    assert result.success and result.changed
    assert not result.failures
    assert channel.edit.await_count == 1
    channel.set_permissions.assert_awaited()


@pytest.mark.asyncio
async def test_reconcile_bootstraps_when_manage_channels_missing() -> None:
    _, bot, _, _, bot_access, context, channel = _setup()
    perms = MagicMock(view_channel=True, manage_channels=False, manage_roles=True)
    channel.permissions_for = MagicMock(return_value=perms)
    channel.overwrites = {
        bot_access: discord.PermissionOverwrite(view_channel=True),
    }

    async def _bootstrap(*args: object, **kwargs: object) -> None:
        perms.manage_channels = True
        channel.overwrites[bot] = discord.PermissionOverwrite(
            view_channel=True, manage_channels=True
        )

    channel.set_permissions = AsyncMock(side_effect=_bootstrap)
    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: _bot_access_overwrite()},
        managed_targets={bot, bot_access},
        reason="leaders",
    )
    assert result.success
    assert channel.set_permissions.await_count >= 1


@pytest.mark.asyncio
async def test_reconcile_bootstraps_stale_bot_member_deny_then_strips_it() -> None:
    _, bot, _, _, bot_access, context, channel = _setup()
    deny = discord.PermissionOverwrite(view_channel=False, manage_channels=False)
    channel.overwrites = {bot: deny}
    perms = MagicMock()
    perms.view_channel = False
    perms.manage_channels = False
    perms.manage_roles = False
    channel.permissions_for = MagicMock(return_value=perms)

    async def _after_bootstrap(*args: object, **kwargs: object) -> None:
        perms.view_channel = True
        perms.manage_channels = True
        perms.manage_roles = True
        channel.overwrites = {
            bot: discord.PermissionOverwrite(
                view_channel=True,
                manage_channels=True,
            ),
            bot_access: _bot_access_overwrite(),
        }

    channel.set_permissions = AsyncMock(side_effect=_after_bootstrap)
    channel.edit = AsyncMock(side_effect=_after_bootstrap)

    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: _bot_access_overwrite()},
        managed_targets={bot, bot_access},
        reason="leaders",
    )

    assert result.success and result.verified
    assert channel.set_permissions.await_count >= 1
    # Final strip removes direct bot-member overwrite after role access is verified.
    final_calls = [
        call
        for call in channel.set_permissions.await_args_list
        if call.args and call.args[0] is bot and call.kwargs.get("overwrite") is None
    ]
    assert final_calls


@pytest.mark.asyncio
async def test_incremental_fallback_defers_bot_member_removal() -> None:
    _, bot, _, _, bot_access, context, channel = _setup()
    channel.overwrites = {
        bot: discord.PermissionOverwrite(
            view_channel=True, manage_channels=True
        ),
    }
    channel.edit.side_effect = http_50013()

    result = await PermissionService().reconcile(
        channel,
        context,
        {bot_access: _bot_access_overwrite()},
        managed_targets={bot, bot_access},
        reason="test",
    )

    assert result.success
    applied = channel.set_permissions.await_args_list
    access_idx = next(
        i for i, call in enumerate(applied) if call.args and call.args[0] is bot_access
    )
    # Bot member cleared only after desired role grant, via explicit strip.
    strip_idx = next(
        i
        for i, call in enumerate(applied)
        if call.args
        and call.args[0] is bot
        and call.kwargs.get("overwrite") is None
    )
    assert access_idx < strip_idx


@pytest.mark.asyncio
async def test_reconcile_stress_cleans_every_owned_subset() -> None:
    _, bot, moderator, access, bot_access, context, _ = _setup()
    old_operator = make_role(name="Legacy operator", role_id=77, position=8)
    unrelated = make_role(name="Unmanaged custom", role_id=88, position=2)
    owned = (bot, moderator, access, old_operator, bot_access)
    desired = {bot_access: _bot_access_overwrite()}
    custom = discord.PermissionOverwrite(send_messages=False)
    for present in product((False, True), repeat=len(owned)):
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 800
        channel.edit = AsyncMock()
        channel.set_permissions = AsyncMock()
        channel.permissions_for = MagicMock(
            return_value=MagicMock(
                view_channel=True, manage_channels=True, manage_roles=True
            )
        )
        current = {
            target: discord.PermissionOverwrite(view_channel=True)
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
            assert bot_access in final
            assert final[unrelated] is custom
            assert bot not in final or final[bot].pair()[0].view_channel


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
