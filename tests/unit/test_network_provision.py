from __future__ import annotations

from unittest.mock import MagicMock

import discord
import pytest

from bot.core.models.errors import NetworkValidationError
from bot.features.networks.roles import (
    format_operator_setup_instructions,
    resolve_access_role,
    validate_hub_permissions,
    validate_provision_permissions,
)


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


def test_format_operator_setup_instructions_lists_permissions() -> None:
    text = format_operator_setup_instructions("The Network+", "The Network")
    assert "The Network+" in text
    assert "Manage Channels" in text
    assert "Manage Roles" in text


def _dual_role_bot() -> tuple[MagicMock, MagicMock, MagicMock]:
    access = MagicMock(spec=discord.Role, name="The Network", position=5, id=42)
    access.is_default.return_value = False
    operator = MagicMock(spec=discord.Role, name="The Network+", position=10, id=43)
    operator.is_default.return_value = False
    operator.permissions.manage_channels = True
    operator.permissions.manage_roles = True
    operator.permissions.manage_webhooks = True
    operator.permissions.send_messages = True
    operator.permissions.embed_links = True
    operator.permissions.attach_files = True
    operator.permissions.read_message_history = True
    operator.permissions.manage_messages = True
    operator.permissions.manage_emojis_and_stickers = True

    bot = MagicMock(spec=discord.Member)
    bot.guild_permissions.manage_channels = True
    bot.guild_permissions.manage_roles = True
    bot.guild_permissions.manage_webhooks = True
    bot.top_role = operator
    bot.roles = [access, operator]
    return bot, access, operator


def test_validate_provision_permissions_requires_manage_roles() -> None:
    bot, access, operator = _dual_role_bot()
    bot.guild_permissions.manage_roles = False
    with pytest.raises(NetworkValidationError, match="Manage Roles"):
        validate_provision_permissions(
            bot,
            access,
            operator_role=operator,
            operator_role_name="The Network+",
        )


def test_validate_provision_permissions_accepts_network_plus_as_top_role() -> None:
    bot, access, operator = _dual_role_bot()
    operator.name = "The Network+"
    bot.top_role = operator
    validate_provision_permissions(
        bot,
        access,
        operator_role=operator,
        operator_role_name="The Network+",
    )


def test_validate_provision_permissions_requires_operator_role() -> None:
    bot, access, _operator = _dual_role_bot()
    with pytest.raises(NetworkValidationError, match="The Network+"):
        validate_provision_permissions(
            bot,
            access,
            operator_role=None,
            operator_role_name="The Network+",
        )


def test_validate_provision_permissions_requires_operator_as_top_role() -> None:
    bot, access, operator = _dual_role_bot()
    bot.top_role = access
    with pytest.raises(NetworkValidationError, match="highest role"):
        validate_provision_permissions(
            bot,
            access,
            operator_role=operator,
            operator_role_name="The Network+",
        )


def test_validate_hub_permissions_requires_role_above_moderator() -> None:
    bot, access, operator = _dual_role_bot()
    access.position = 1
    operator.position = 10
    bot.top_role = operator
    human_moderator = MagicMock(spec=discord.Role, name="Moderator", position=15, id=3)
    with pytest.raises(NetworkValidationError, match="Moderator"):
        validate_hub_permissions(
            bot,
            access,
            operator_role=operator,
            operator_role_name="The Network+",
            human_moderator_role=human_moderator,
        )
