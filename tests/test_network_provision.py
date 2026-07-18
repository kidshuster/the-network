from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.domain.errors import NetworkValidationError
from bot.services.network_provision import (
    build_base_overwrites,
    build_forum_overwrites,
    category_name_for,
    resolve_access_role,
    validate_provision_permissions,
)


def test_category_name_for() -> None:
    assert category_name_for("Stingers") == "Stingers Feed"


def test_resolve_access_role_explicit() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    role = MagicMock(spec=discord.Role)
    role.guild.id = 100
    assert resolve_access_role(guild, role_name="ignored", explicit_role=role) is role


def test_resolve_access_role_by_name() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    role = MagicMock(spec=discord.Role)
    role.name = "The Network"
    guild.roles = [role]
    assert resolve_access_role(guild, role_name="The Network") is role


def test_resolve_access_role_missing() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 100
    guild.roles = []
    with pytest.raises(NetworkValidationError):
        resolve_access_role(guild, role_name="Missing Role")


def test_forum_overwrites_omit_manage_threads_for_bot() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.default_role = MagicMock(spec=discord.Role)
    bot = MagicMock(spec=discord.Member)
    access = MagicMock(spec=discord.Role)
    overwrites = dict(build_forum_overwrites(guild, bot, access))
    assert overwrites[bot].manage_threads is None
    assert overwrites[access].manage_threads is None


def test_base_overwrites_omit_manage_threads_for_bot() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.default_role = MagicMock(spec=discord.Role)
    bot = MagicMock(spec=discord.Member)
    access = MagicMock(spec=discord.Role)
    overwrites = dict(build_base_overwrites(guild, bot, access))
    assert overwrites[bot].manage_threads is None


def test_validate_provision_permissions_requires_manage_roles() -> None:
    bot = MagicMock(spec=discord.Member)
    bot.guild_permissions.manage_channels = True
    bot.guild_permissions.manage_roles = False
    bot.guild_permissions.manage_webhooks = True
    bot.top_role = MagicMock(spec=discord.Role, name="Bot", position=5)
    access = MagicMock(spec=discord.Role, name="The Network", position=1)
    with pytest.raises(NetworkValidationError, match="Manage Roles"):
        validate_provision_permissions(bot, access)


def test_validate_provision_permissions_same_role_is_clear() -> None:
    bot = MagicMock(spec=discord.Member)
    bot.display_name = "The-Network"
    bot.guild_permissions.manage_channels = True
    bot.guild_permissions.manage_roles = True
    bot.guild_permissions.manage_webhooks = True
    bot.top_role = MagicMock(spec=discord.Role, name="The Network", position=1, id=42)
    access = MagicMock(spec=discord.Role, name="The Network", position=1, id=42)
    with pytest.raises(NetworkValidationError, match="assigned the role"):
        validate_provision_permissions(bot, access)
