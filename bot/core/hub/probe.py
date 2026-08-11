from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.channels.layout import LayoutContext, compile_hub
from bot.channels.layout.compiler import ResourceKind
from bot.channels.layout.managed import hub_category_name, hub_channel_name
from bot.channels.resolve import (
    HUB_CATEGORY_LEADERS,
    HUB_CATEGORY_MODERATION,
    HUB_CATEGORY_NETWORK,
    HUB_CHANNEL_CHANGELOG,
    HUB_CHANNEL_COMMANDS,
    HUB_CHANNEL_JOIN_REQUESTS,
    HUB_CHANNEL_JOIN_THE_NETWORK,
    HUB_CHANNEL_LEADERS,
    HUB_CHANNEL_MODERATOR_ONLY,
    HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
    HUB_CHANNEL_RULES,
    resolve_hub_category,
    resolve_hub_channel,
    resolve_human_moderator_role,
)
from bot.config import Settings
from bot.constants import DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME
from bot.core.networks.roles import (
    resolve_access_role,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)

if TYPE_CHECKING:
    from bot.core.runtime import BotContext


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class ServerProbeReport:
    checks: list[ProbeCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def passed_checks(self) -> list[ProbeCheck]:
        return [check for check in self.checks if check.passed]

    @property
    def failed_checks(self) -> list[ProbeCheck]:
        return [check for check in self.checks if not check.passed]


def _role_can_view_channel(channel: discord.abc.GuildChannel, role: discord.Role) -> bool:
    overwrite = channel.overwrites_for(role)
    if overwrite.view_channel is False:
        return False
    return channel.permissions_for(role).view_channel


def _layout_context(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> LayoutContext:
    access = resolve_access_role(guild, role_name=settings.network_access_role_name)
    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    bot_access = discord.utils.get(guild.roles, name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME)
    return LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access,
        moderator_role=resolve_human_moderator_role(guild),
        operator_role=operator,
        bot_access_role=bot_access,
        reason="The Network server probe",
    )


def _check_operator_setup(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeCheck:
    try:
        access_role = resolve_access_role(guild, role_name=settings.network_access_role_name)
        operator_role = resolve_operator_role_by_name(
            guild,
            role_name=settings.network_operator_role_name,
        )
        validate_hub_permissions(
            bot_member,
            access_role,
            operator_role=operator_role,
            operator_role_name=settings.network_operator_role_name,
            human_moderator_role=resolve_human_moderator_role(guild),
        )
    except Exception as exc:
        return ProbeCheck("operator setup", False, str(exc))
    return ProbeCheck(
        "operator setup",
        True,
        f"top role={bot_member.top_role.name}, access role={access_role.name}",
    )


def _check_bot_access_role(bot_member: discord.Member, guild: discord.Guild) -> ProbeCheck:
    role = discord.utils.get(guild.roles, name=DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME)
    if role is None:
        return ProbeCheck(
            "bot access role",
            False,
            f"**{DEFAULT_NETWORK_BOT_ACCESS_ROLE_NAME}** missing — run `/server init`",
        )
    if role not in bot_member.roles:
        return ProbeCheck(
            "bot access role",
            False,
            f"bot is missing **{role.name}** — run `/server init`",
        )
    if (
        isinstance(role.position, int)
        and isinstance(bot_member.top_role.position, int)
        and role.position >= bot_member.top_role.position
    ):
        return ProbeCheck(
            "bot access role",
            False,
            f"**{role.name}** must be below **{bot_member.top_role.name}**",
        )
    return ProbeCheck("bot access role", True, f"bot holds **{role.name}**")


def _check_manage_server(bot_member: discord.Member) -> ProbeCheck:
    if bot_member.guild_permissions.manage_guild:
        return ProbeCheck(
            "manage server",
            True,
            "bot can set guild default notifications",
        )
    return ProbeCheck(
        "manage server",
        True,
        "optional gap: missing **Manage Server** (init notes a notification warning)",
    )


def _check_hub_layout(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeCheck:
    try:
        ctx = _layout_context(guild, bot_member, settings)
        resources = compile_hub(ctx)
    except Exception as exc:
        return ProbeCheck("hub layout", False, f"compile_hub failed: {exc}")

    missing_categories: list[str] = []
    missing_channels: list[str] = []
    for resource in resources:
        if resource.kind is ResourceKind.CATEGORY:
            if not any(cat.name.casefold() == resource.name.casefold() for cat in guild.categories):
                missing_categories.append(resource.name)
            continue
        aliases = {resource.name.casefold(), *(n.casefold() for n in resource.legacy_names)}
        found = next(
            (
                channel
                for channel in guild.text_channels
                if channel.name.casefold() in aliases
            ),
            None,
        )
        if found is None:
            missing_channels.append(resource.name)

    problems = [
        *(f"category:{name}" for name in missing_categories),
        *(f"channel:{name}" for name in missing_channels),
    ]
    if problems:
        return ProbeCheck(
            "hub layout",
            False,
            "missing hub resources: " + ", ".join(problems[:8]),
        )
    channel_count = sum(1 for item in resources if item.kind is not ResourceKind.CATEGORY)
    category_count = sum(1 for item in resources if item.kind is ResourceKind.CATEGORY)
    return ProbeCheck(
        "hub layout",
        True,
        f"{category_count} categories and {channel_count} channels present",
    )


def _check_community_slots(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeCheck:
    try:
        ctx = _layout_context(guild, bot_member, settings)
        resources = compile_hub(ctx)
    except Exception as exc:
        return ProbeCheck("community slots", False, f"compile_hub failed: {exc}")

    moderation_name = hub_category_name(HUB_CATEGORY_MODERATION)
    problems: list[str] = []
    for resource in resources:
        if resource.community_slot is None:
            continue
        aliases = {resource.name.casefold(), *(n.casefold() for n in resource.legacy_names)}
        found = next(
            (
                channel
                for channel in guild.text_channels
                if channel.name.casefold() in aliases
            ),
            None,
        )
        if found is None:
            problems.append(f"{resource.name} missing")
            continue
        if not found.permissions_for(bot_member).view_channel:
            problems.append(f"#{found.name} hides bot view")
            continue
        if resource.community_slot == "rules":
            if guild.rules_channel is None or guild.rules_channel.id != found.id:
                problems.append(f"#{found.name} not bound as guild rules channel")
        elif resource.community_slot == "public_updates":
            if (
                guild.public_updates_channel is None
                or guild.public_updates_channel.id != found.id
            ):
                problems.append(f"#{found.name} not bound as public updates channel")
            if found.category is None or found.category.name != moderation_name:
                problems.append(f"#{found.name} not in **{moderation_name}**")

    if problems:
        return ProbeCheck("community slots", False, "; ".join(problems[:6]))
    return ProbeCheck("community slots", True, "rules and public updates are bound and visible")


def _resolve_probe_hub_channel(
    guild: discord.Guild,
    channel_id: str,
    *,
    mod_category: discord.CategoryChannel | None,
    network_category: discord.CategoryChannel | None,
    leaders_category: discord.CategoryChannel | None,
) -> discord.TextChannel | None:
    if channel_id == HUB_CHANNEL_JOIN_THE_NETWORK:
        category_id = None if network_category is None else network_category.id
    elif channel_id in {HUB_CHANNEL_LEADERS, HUB_CHANNEL_CHANGELOG}:
        category_id = None if leaders_category is None else leaders_category.id
    else:
        category_id = None if mod_category is None else mod_category.id

    include_announcement = channel_id != HUB_CHANNEL_NETWORK_ANNOUNCEMENTS
    channel = resolve_hub_channel(
        guild,
        channel_id,
        category_id=category_id,
        include_announcement=include_announcement,
    )
    if channel_id == HUB_CHANNEL_LEADERS and channel is None:
        channel = resolve_hub_channel(guild, channel_id)
    return channel


def _check_bot_channel_access(guild: discord.Guild, bot_member: discord.Member) -> ProbeCheck:
    mod_category = resolve_hub_category(guild, HUB_CATEGORY_MODERATION)
    network_category = resolve_hub_category(guild, HUB_CATEGORY_NETWORK)
    leaders_category = resolve_hub_category(guild, HUB_CATEGORY_LEADERS)
    channel_ids = (
        HUB_CHANNEL_COMMANDS,
        HUB_CHANNEL_JOIN_REQUESTS,
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        HUB_CHANNEL_JOIN_THE_NETWORK,
        HUB_CHANNEL_RULES,
        HUB_CHANNEL_MODERATOR_ONLY,
        HUB_CHANNEL_LEADERS,
        HUB_CHANNEL_CHANGELOG,
    )
    blocked: list[str] = []
    present = 0
    for channel_id in channel_ids:
        channel = _resolve_probe_hub_channel(
            guild,
            channel_id,
            mod_category=mod_category,
            network_category=network_category,
            leaders_category=leaders_category,
        )
        if channel is None:
            continue
        present += 1
        if not channel.permissions_for(bot_member).view_channel:
            blocked.append(f"#{channel.name}")
    if present == 0:
        return ProbeCheck(
            "bot channel access",
            False,
            "no hub channels found — run `/server init`",
        )
    if blocked:
        return ProbeCheck(
            "bot channel access",
            False,
            "bot cannot view " + ", ".join(blocked[:6]),
        )
    return ProbeCheck(
        "bot channel access",
        True,
        f"bot can view {present} hub channel(s)",
    )


def _check_announcements_channel(guild: discord.Guild) -> ProbeCheck:
    mod_category = resolve_hub_category(guild, HUB_CATEGORY_MODERATION)
    channel = resolve_hub_channel(
        guild,
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        category_id=None if mod_category is None else mod_category.id,
        include_announcement=False,
    )
    moderation_name = hub_category_name(HUB_CATEGORY_MODERATION)
    announcements_name = hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)
    if channel is None:
        return ProbeCheck(
            "announcements channel",
            False,
            f"#{announcements_name} missing — run `/server init`",
        )
    if mod_category is not None and channel.category_id != mod_category.id:
        return ProbeCheck(
            "announcements channel",
            False,
            f"#{channel.name} is outside **{moderation_name}**",
        )
    if channel.is_news():
        return ProbeCheck(
            "announcements channel",
            False,
            f"#{channel.name} must be a regular text channel — run `/server init`",
        )
    return ProbeCheck(
        "announcements channel",
        True,
        f"{channel.mention} ready for moderator network broadcasts",
    )


async def _check_leaders_access(guild: discord.Guild, context: BotContext) -> ProbeCheck:
    category = resolve_hub_category(guild, HUB_CATEGORY_LEADERS)
    leaders_cat_id = None if category is None else category.id
    leaders = resolve_hub_channel(
        guild,
        HUB_CHANNEL_LEADERS,
        category_id=leaders_cat_id,
    )
    if leaders is None:
        leaders = resolve_hub_channel(guild, HUB_CHANNEL_LEADERS)
    changelog = resolve_hub_channel(
        guild,
        HUB_CHANNEL_CHANGELOG,
        category_id=leaders_cat_id,
    )
    if category is None or leaders is None or changelog is None:
        return ProbeCheck(
            "leaders access",
            False,
            "Leaders layout incomplete — run `/server init`",
        )

    gaps: list[str] = []
    clients = [
        client
        for client in await context.store.clients.list_all()
        if client.guild_id == guild.id
    ]
    for client in clients:
        role = guild.get_role(client.client_role_id)
        if role is None:
            gaps.append(f"{client.server_name}: role missing")
            continue
        for label, channel in (
            ("Leaders category", category),
            (hub_channel_name(HUB_CHANNEL_LEADERS), leaders),
            (hub_channel_name(HUB_CHANNEL_CHANGELOG), changelog),
        ):
            if not _role_can_view_channel(channel, role):
                gaps.append(f"{client.server_name}: cannot view {label}")

    if gaps:
        return ProbeCheck("leaders access", False, "; ".join(gaps[:5]))
    if not clients:
        return ProbeCheck("leaders access", True, "no registered clients — nothing to verify")
    return ProbeCheck(
        "leaders access",
        True,
        f"all {len(clients)} client role(s) can view Leaders",
    )


async def run_server_probe(
    guild: discord.Guild,
    bot_member: discord.Member,
    *,
    settings: Settings,
    context: BotContext,
) -> ServerProbeReport:
    """Run read-only hub health checks (safe on production)."""
    report = ServerProbeReport(
        checks=[
            _check_operator_setup(guild, bot_member, settings),
            _check_bot_access_role(bot_member, guild),
            _check_manage_server(bot_member),
            _check_hub_layout(guild, bot_member, settings),
            _check_community_slots(guild, bot_member, settings),
            _check_bot_channel_access(guild, bot_member),
            _check_announcements_channel(guild),
            await _check_leaders_access(guild, context),
        ]
    )
    return report
