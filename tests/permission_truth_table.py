from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import discord
from discord_helpers import make_guild_with_roles, make_role

CapabilityMap = dict[str, bool | None]
RoleKey = str

# Capabilities that gate security-sensitive behavior across hub vs client layouts.
TRACKED_CAPABILITIES: tuple[str, ...] = (
    "view_channel",
    "read_message_history",
    "send_messages",
    "embed_links",
    "attach_files",
    "manage_webhooks",
    "manage_channels",
    "manage_messages",
    "create_public_threads",
    "send_messages_in_threads",
    "add_reactions",
    "use_application_commands",
)

POST_LOCKDOWN: CapabilityMap = {
    "send_messages": False,
    "add_reactions": False,
    "create_public_threads": False,
    "send_messages_in_threads": False,
}

CATEGORY_LOCKDOWN: CapabilityMap = {
    "send_messages": False,
    "add_reactions": False,
}


@dataclass(frozen=True)
class PermissionScenarioContext:
    guild: MagicMock
    bot: MagicMock
    human_mod: MagicMock
    access: MagicMock
    operator: MagicMock
    client: MagicMock
    server_role: MagicMock

    def role(self, key: RoleKey) -> discord.Role | discord.Member:
        return {
            "everyone": self.guild.default_role,
            "access": self.access,
            "client": self.client,
            "moderator": self.human_mod,
            "bot": self.bot,
            "operator": self.operator,
            "server": self.server_role,
        }[key]


@dataclass(frozen=True)
class PermissionTruthTableScenario:
    """Expected overwrite capabilities for one channel/category recipe."""

    name: str
    policy: str
    build: Callable[[PermissionScenarioContext], Mapping[Any, discord.PermissionOverwrite]]
    expectations: dict[RoleKey, CapabilityMap | None]
    filter_for_channel: bool = False


def make_permission_context() -> PermissionScenarioContext:
    guild, bot, human_mod, access, operator = make_guild_with_roles()
    client = make_role(name="Client: Acme", role_id=60, position=1)
    server_role = make_role(name="Partner: Acme", role_id=70, position=2)
    guild.roles = [*guild.roles, client, server_role]
    return PermissionScenarioContext(
        guild=guild,
        bot=bot,
        human_mod=human_mod,
        access=access,
        operator=operator,
        client=client,
        server_role=server_role,
    )


def overwrite_capabilities(overwrite: discord.PermissionOverwrite) -> CapabilityMap:
    return {cap: getattr(overwrite, cap) for cap in TRACKED_CAPABILITIES}


def assert_capabilities(
    overwrite: discord.PermissionOverwrite,
    expected: CapabilityMap,
    *,
    scenario: str,
    role: RoleKey,
) -> None:
    actual = overwrite_capabilities(overwrite)
    for capability, value in expected.items():
        assert actual[capability] is value, (
            f"{scenario} / {role} / {capability}: expected {value!r}, got {actual[capability]!r}"
        )


def assert_truth_table(
    scenario: PermissionTruthTableScenario,
    ctx: PermissionScenarioContext,
) -> None:
    raw = dict(scenario.build(ctx))
    overwrites = raw
    if scenario.filter_for_channel:
        from bot.services.guild_permissions import filter_configurable_overwrites

        overwrites = filter_configurable_overwrites(ctx.bot, raw, for_channel=True)

    for role_key, expected in scenario.expectations.items():
        role = ctx.role(role_key)
        if expected is None:
            assert role not in overwrites, f"{scenario.name}: {role_key} should be absent"
            continue
        assert role in overwrites, f"{scenario.name}: {role_key} missing from overwrites"
        assert_capabilities(
            overwrites[role],
            expected,
            scenario=scenario.name,
            role=role_key,
        )
