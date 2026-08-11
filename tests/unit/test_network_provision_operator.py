from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from discord_helpers import make_bot_member, make_role

from bot.core.models.errors import NetworkValidationError
from bot.core.networks.roles import validate_operator_setup


def _operator_bot() -> tuple[MagicMock, MagicMock, MagicMock]:
    access = make_role(name="The Network", role_id=40, position=5)
    operator = make_role(name="The Network+", role_id=50, position=10)
    operator.permissions.manage_channels = True
    operator.permissions.manage_roles = True
    operator.permissions.manage_webhooks = True
    operator.permissions.send_messages = True
    operator.permissions.embed_links = True
    operator.permissions.attach_files = True
    operator.permissions.read_message_history = True
    operator.permissions.manage_messages = True
    operator.permissions.manage_emojis_and_stickers = True
    operator.permissions.create_expressions = True
    bot = make_bot_member(access=access, operator=operator)
    return bot, access, operator


def test_validate_operator_setup_requires_role_present() -> None:
    bot, access, _operator = _operator_bot()
    with pytest.raises(NetworkValidationError, match="The Network+"):
        validate_operator_setup(
            bot,
            None,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_requires_bot_has_operator_role() -> None:
    bot, access, operator = _operator_bot()
    bot.roles = [access]
    with pytest.raises(NetworkValidationError, match="Assign"):
        validate_operator_setup(
            bot,
            operator,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_requires_operator_as_top_role() -> None:
    bot, access, operator = _operator_bot()
    bot.top_role = access
    with pytest.raises(NetworkValidationError, match="highest role"):
        validate_operator_setup(
            bot,
            operator,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_requires_operator_above_access() -> None:
    bot, access, operator = _operator_bot()
    access.position = 15
    operator.position = 10
    bot.top_role = operator
    with pytest.raises(NetworkValidationError, match="above"):
        validate_operator_setup(
            bot,
            operator,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_lists_missing_permissions() -> None:
    bot, access, operator = _operator_bot()
    operator.permissions.manage_roles = False
    operator.permissions.manage_webhooks = False
    with pytest.raises(NetworkValidationError, match="Manage Roles"):
        validate_operator_setup(
            bot,
            operator,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_accepts_emoji_permission_alias() -> None:
    bot, access, operator = _operator_bot()
    operator.permissions.manage_emojis_and_stickers = False
    operator.permissions.manage_expressions = True
    validate_operator_setup(
        bot,
        operator,
        access,
        operator_role_name="The Network+",
    )


def test_validate_operator_setup_requires_create_expressions() -> None:
    bot, access, operator = _operator_bot()
    operator.permissions.create_expressions = False
    operator.permissions.manage_expressions = True
    with pytest.raises(NetworkValidationError, match="Create Expressions"):
        validate_operator_setup(
            bot,
            operator,
            access,
            operator_role_name="The Network+",
        )


def test_validate_operator_setup_passes_when_configured() -> None:
    bot, access, operator = _operator_bot()
    validate_operator_setup(
        bot,
        operator,
        access,
        operator_role_name="The Network+",
    )
