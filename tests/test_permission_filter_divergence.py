"""Characterize applicable_overwrites create vs edit filtering.

These tests document the intentional remaining divergence: category create
omits bot/operator access roles, while channel reconcile keeps the operator
access role for edits.
"""

from __future__ import annotations

from collections.abc import Mapping
from unittest.mock import MagicMock, PropertyMock

import discord

from bot.permissions.service import ResourceKind, applicable_overwrites, build_context

Target = discord.Role | discord.Member | discord.Object


def _make_bot_with_operator_top_role(
    *,
    operator_position: int = 10,
) -> tuple[discord.Member, discord.Role]:
    operator = MagicMock(spec=discord.Role, id=301, position=operator_position)
    operator.is_default.return_value = False

    bot = MagicMock(spec=discord.Member, id=999)
    bot.top_role = operator
    bot.roles = [operator]
    bot.guild = MagicMock(spec=discord.Guild)
    perms = MagicMock(administrator=False)
    type(bot).guild_permissions = PropertyMock(return_value=perms)
    return bot, operator


def _sample_overwrites(
    *,
    everyone: discord.Role,
    client: discord.Role,
    bot: discord.Member,
    operator: discord.Role,
) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
    overwrite = discord.PermissionOverwrite(view_channel=True)
    return {
        everyone: overwrite,
        client: overwrite,
        bot: overwrite,
        operator: overwrite,
    }


def _filter(
    bot: discord.Member,
    overwrites: Mapping[Target, discord.PermissionOverwrite],
    *,
    kind: ResourceKind,
    for_category_create: bool = False,
) -> dict[Target, discord.PermissionOverwrite]:
    return applicable_overwrites(
        build_context(bot.guild, bot, access_role=None, moderator_role=None),
        overwrites,
        kind=kind,
        for_category_create=for_category_create,
    )


def test_text_filter_strips_bot_member() -> None:
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10, position=1)
    client.is_default.return_value = False
    bot, operator = _make_bot_with_operator_top_role()
    source = _sample_overwrites(
        everyone=everyone,
        client=client,
        bot=bot,
        operator=operator,
    )

    filtered = _filter(bot, source, kind=ResourceKind.TEXT)

    assert bot not in filtered
    assert operator in filtered
    assert client in filtered


def test_category_create_omits_bot_and_operator_top_role() -> None:
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10, position=1)
    client.is_default.return_value = False
    bot, operator = _make_bot_with_operator_top_role()
    source = _sample_overwrites(
        everyone=everyone,
        client=client,
        bot=bot,
        operator=operator,
    )

    prepared = _filter(
        bot,
        source,
        kind=ResourceKind.CATEGORY,
        for_category_create=True,
    )

    assert bot not in prepared
    assert operator not in prepared
    assert client in prepared


def test_text_filter_keeps_operator_even_when_not_configurable() -> None:
    """Operator top role is retained for channel edits despite can_configure_role False."""
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10, position=1)
    client.is_default.return_value = False
    bot, operator = _make_bot_with_operator_top_role()
    source = _sample_overwrites(
        everyone=everyone,
        client=client,
        bot=bot,
        operator=operator,
    )

    filtered = _filter(bot, source, kind=ResourceKind.TEXT)

    assert operator in filtered
    assert bot not in filtered


def test_filter_divergence_operator_in_text_but_not_in_category_create() -> None:
    """Documents intentional create-vs-edit divergence for the operator top role."""
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10, position=1)
    client.is_default.return_value = False
    bot, operator = _make_bot_with_operator_top_role()
    source = _sample_overwrites(
        everyone=everyone,
        client=client,
        bot=bot,
        operator=operator,
    )

    for_channel = _filter(bot, source, kind=ResourceKind.TEXT)
    for_category_create = _filter(
        bot,
        source,
        kind=ResourceKind.CATEGORY,
        for_category_create=True,
    )

    assert operator in for_channel
    assert operator not in for_category_create


def test_category_filter_includes_bot_member() -> None:
    everyone = MagicMock(spec=discord.Role)
    everyone.is_default.return_value = True
    client = MagicMock(spec=discord.Role, id=10, position=1)
    client.is_default.return_value = False
    bot, operator = _make_bot_with_operator_top_role()
    source = _sample_overwrites(
        everyone=everyone,
        client=client,
        bot=bot,
        operator=operator,
    )

    category_filtered = _filter(bot, source, kind=ResourceKind.CATEGORY)

    assert bot in category_filtered
