from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.config import Settings
from bot.services.guild_init import initialize_guild
from bot.services.guild_layout import (
    CATEGORY_LEADERS,
    CATEGORY_MODERATION,
    CATEGORY_NETWORK,
    CHANNEL_CHANGELOG,
    CHANNEL_LEADERS,
    CHANNEL_MODERATOR_ONLY,
    resolve_changelog_channel,
    resolve_human_moderator_role,
    resolve_leaders_category,
    resolve_leaders_channel,
)
from bot.services.leaders_channel import ensure_leaders_channels
from bot.services.network_provision import (
    resolve_access_role,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.smoke.provision_flow import run_pre_init_smoke_checks
from bot.smoke.resource_guard import guild_test_resource_guard

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.context import BotContext

logger = logging.getLogger(__name__)

_PROBE_REASON = "The Network server-init live probe (auto-reverted)"


@dataclass
class ProbeResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ServerInitProbeReport:
    probes: list[ProbeResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(probe.passed for probe in self.probes)

    def add(self, probe: ProbeResult) -> None:
        self.probes.append(probe)


def _role_can_view_channel(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
) -> bool:
    overwrite = channel.overwrites_for(role)
    if overwrite.view_channel is False:
        return False
    return channel.permissions_for(role).view_channel


async def _list_guild_clients(
    guild: discord.Guild,
    context: BotContext,
) -> list[tuple[str, discord.Role]]:
    clients: list[tuple[str, discord.Role]] = []
    for client in await context.client_repo.list_all():
        if client.guild_id != guild.id:
            continue
        role = guild.get_role(client.client_role_id)
        if role is None:
            continue
        clients.append((client.server_name, role))
    return clients


async def _collect_leaders_access_gaps(
    guild: discord.Guild,
    context: BotContext,
) -> list[str]:
    gaps: list[str] = []
    category = resolve_leaders_category(guild)
    leaders = resolve_leaders_channel(guild)
    changelog = resolve_changelog_channel(guild)
    targets: list[tuple[str, discord.abc.GuildChannel | None]] = [
        (f"{CATEGORY_LEADERS} category", category),
        (CHANNEL_LEADERS, leaders),
        (CHANNEL_CHANGELOG, changelog),
    ]
    for server_name, role in await _list_guild_clients(guild, context):
        for label, target in targets:
            if target is None:
                gaps.append(f"{server_name}: {label} not found")
            elif not _role_can_view_channel(target, role):
                gaps.append(f"{server_name}: missing view on {label} ({target.mention})")
    return gaps


async def probe_pre_init_smoke(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeResult:
    """Same permission probes `/server init` runs before hub setup."""
    try:
        smoke = await run_pre_init_smoke_checks(guild, bot_member, settings)
    except Exception as exc:
        return ProbeResult("pre-init smoke", False, str(exc))

    steps = [*smoke.operator_steps, *smoke.provision_steps]
    return ProbeResult(
        "pre-init smoke",
        True,
        f"{len(steps)} steps passed ({', '.join(steps[:3])}{'…' if len(steps) > 3 else ''})",
    )


async def probe_operator_setup(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeResult:
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
        return ProbeResult("operator setup", False, str(exc))
    return ProbeResult(
        "operator setup",
        True,
        f"top role={bot_member.top_role.name}, access role={access_role.name}",
    )


async def probe_manage_server_permission(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> ProbeResult:
    if bot_member.guild_permissions.manage_guild:
        return ProbeResult(
            "manage server",
            True,
            "bot can set guild default notifications during init",
        )
    return ProbeResult(
        "manage server",
        True,
        "optional gap: missing **Manage Server** — init succeeds but notes a notification warning",
    )


async def probe_moderator_only_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> ProbeResult:
    for channel in guild.text_channels:
        if channel.name.casefold() != CHANNEL_MODERATOR_ONLY:
            continue
        perms = channel.permissions_for(bot_member)
        if not perms.view_channel:
            return ProbeResult(
                "moderator-only channel",
                False,
                (
                    f"#{channel.name} exists outside hub control and denies bot view "
                    f"(category={channel.category.name if channel.category else 'none'}) — "
                    "init cannot move it; delete it or grant **The Testwork +** view access"
                ),
            )
        if channel.category is None or channel.category.name != CATEGORY_MODERATION:
            return ProbeResult(
                "moderator-only channel",
                False,
                (
                    f"#{channel.name} is visible but not in **{CATEGORY_MODERATION}** — "
                    "re-run `/server init` after fixing layout"
                ),
            )
        return ProbeResult(
            "moderator-only channel",
            True,
            f"#{CHANNEL_MODERATOR_ONLY} is in **{CATEGORY_MODERATION}**",
        )
    return ProbeResult(
        "moderator-only channel",
        True,
        f"no #{CHANNEL_MODERATOR_ONLY} channel present (init will create one)",
    )


async def probe_hub_layout(
    guild: discord.Guild,
) -> ProbeResult:
    missing: list[str] = []
    for category_name in (CATEGORY_MODERATION, CATEGORY_NETWORK, CATEGORY_LEADERS):
        if not any(cat.name == category_name for cat in guild.categories):
            missing.append(category_name)
    if missing:
        return ProbeResult(
            "hub layout",
            False,
            f"missing categories: {', '.join(missing)} — run `/server init` first",
        )
    return ProbeResult("hub layout", True, "Moderation, Network, and Leaders categories present")


async def probe_hub_announcements(
    guild: discord.Guild,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    from bot.services.guild_layout import (
        resolve_moderation_category,
        resolve_network_announcements_channel,
    )
    from bot.services.hub_announcements import is_hub_announcements_client

    mod_channel = resolve_network_announcements_channel(guild)
    mod_category = resolve_moderation_category(guild)
    if mod_channel is None:
        return ProbeResult(
            "hub announcements channel",
            False,
            "#network-announcements missing — run `/server init`",
        )
    if mod_category is not None and mod_channel.category_id != mod_category.id:
        return ProbeResult(
            "hub announcements channel",
            False,
            "#network-announcements is outside Moderation",
        )

    hub = await context.client_repo.get_by_server_name(
        guild.id,
        settings.hub_announcements_server_name,
    )
    if hub is None:
        return ProbeResult(
            "hub announcements client",
            False,
            "Hub announcements client missing — run `/server init`",
        )
    if not is_hub_announcements_client(hub, settings):
        return ProbeResult(
            "hub announcements client",
            False,
            "Reserved hub announcements client row has unexpected server_name",
        )

    networks = await context.network_repo.list_all()
    if not networks:
        return ProbeResult(
            "hub announcements wiring",
            True,
            "hub client present; no networks registered yet",
        )

    missing: list[str] = []
    for network in networks:
        if not network.enabled:
            continue
        sub = await context.client_repo.get_subscription(hub.id, network.id)
        if sub is None:
            missing.append(network.key)
    if missing:
        return ProbeResult(
            "hub announcements wiring",
            False,
            "missing subscriptions for: " + ", ".join(missing),
        )
    return ProbeResult(
        "hub announcements wiring",
        True,
        f"hub client subscribed to {len(networks)} network(s)",
    )


async def probe_leaders_access_current(
    guild: discord.Guild,
    context: BotContext,
) -> ProbeResult:
    gaps = await _collect_leaders_access_gaps(guild, context)
    if gaps:
        return ProbeResult(
            "leaders access (current)",
            False,
            "; ".join(gaps[:5]) + ("…" if len(gaps) > 5 else ""),
        )
    client_count = len(await _list_guild_clients(guild, context))
    if client_count == 0:
        return ProbeResult(
            "leaders access (current)",
            True,
            "no registered clients — nothing to verify",
        )
    return ProbeResult(
        "leaders access (current)",
        True,
        f"all {client_count} client role(s) can view Leaders category/channels",
    )


async def _strip_role_overwrite(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
) -> None:
    overwrites = dict(channel.overwrites)
    if role not in overwrites:
        return
    del overwrites[role]
    await channel.edit(overwrites=overwrites, sync_permissions=False, reason=_PROBE_REASON)  # type: ignore[attr-defined]


async def probe_leaders_drift_resync(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Simulate stale Leaders overwrites and verify ensure_leaders_channels repairs them."""
    clients = await _list_guild_clients(guild, context)
    if not clients:
        return ProbeResult(
            "leaders drift resync",
            False,
            "no registered clients with live roles — approve a client or run "
            "`./bin/smoke_provision_flow.sh` first",
        )

    server_name, client_role = clients[0]
    category = resolve_leaders_category(guild)
    leaders = resolve_leaders_channel(guild)
    changelog = resolve_changelog_channel(guild)
    if category is None or leaders is None or changelog is None:
        return ProbeResult(
            "leaders drift resync",
            False,
            "Leaders layout incomplete — run `/server init` first",
        )

    access_role = resolve_access_role(guild, role_name=settings.network_access_role_name)
    operator_role = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    human_moderator_role = resolve_human_moderator_role(guild)

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        for target in (category, leaders, changelog):
            await _strip_role_overwrite(target, client_role)

        gaps_after_strip = await _collect_leaders_access_gaps(guild, context)
        if not any(server_name in gap for gap in gaps_after_strip):
            return ProbeResult(
                "leaders drift resync",
                False,
                f"could not simulate drift for **{server_name}** — overwrite strip had no effect",
            )

        _leaders, _changelog, sync_result = await ensure_leaders_channels(
            guild,
            bot_member,
            context,
            access_role=access_role,
            human_moderator_role=human_moderator_role,
            operator_role=operator_role,
            reason=_PROBE_REASON,
        )
        if sync_result.failures:
            return ProbeResult(
                "leaders drift resync",
                False,
                "; ".join(sync_result.failures),
            )

        gaps_after_resync = await _collect_leaders_access_gaps(guild, context)
        if gaps_after_resync:
            return ProbeResult(
                "leaders drift resync",
                False,
                "ensure_leaders_channels did not restore access: "
                + "; ".join(gaps_after_resync[:5]),
            )

    return ProbeResult(
        "leaders drift resync",
        True,
        f"restored Leaders access for **{server_name}** on category, "
        f"#{CHANNEL_LEADERS}, and #{CHANNEL_CHANGELOG}",
    )


async def probe_reinit_rectifies_clients(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Run initialize_guild against live layout and verify client/Leaders rectification."""
    clients = await context.client_repo.list_all()
    guild_clients = [client for client in clients if client.guild_id == guild.id]
    if not guild_clients:
        return ProbeResult(
            "reinit rectification",
            True,
            "skipped — no registered clients",
        )

    server_name, client_role = (await _list_guild_clients(guild, context))[0]
    category = resolve_leaders_category(guild)
    leaders = resolve_leaders_channel(guild)
    if category is None or leaders is None:
        return ProbeResult(
            "reinit rectification",
            False,
            "Leaders layout missing — run `/server init` first",
        )

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await _strip_role_overwrite(category, client_role)
        await _strip_role_overwrite(leaders, client_role)

        result = await initialize_guild(
            guild,
            bot_member,
            access_role_name=settings.network_access_role_name,
            operator_role_name=settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            skip_join_smoke=True,
        )
        if not result.success:
            return ProbeResult(
                "reinit rectification",
                False,
                result.reason or "initialize_guild failed",
            )

        gaps = await _collect_leaders_access_gaps(guild, context)
        if gaps:
            return ProbeResult(
                "reinit rectification",
                False,
                "initialize_guild completed but Leaders access still missing: "
                + "; ".join(gaps[:5]),
            )

        detail_parts = [f"Leaders access restored for **{server_name}**"]
        if result.failed_steps:
            detail_parts.append(
                f"init warnings: {', '.join(result.failed_steps[:3])}"
                + ("…" if len(result.failed_steps) > 3 else "")
            )
        if result.rectification_failures:
            return ProbeResult(
                "reinit rectification",
                False,
                "; ".join(result.rectification_failures[:5]),
            )
        return ProbeResult("reinit rectification", True, "; ".join(detail_parts))


async def run_server_init_audit(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    settings: Settings,
) -> ServerInitProbeReport:
    report = ServerInitProbeReport()
    report.add(await probe_operator_setup(guild, bot_member, settings))
    report.add(await probe_pre_init_smoke(guild, bot_member, settings))
    report.add(await probe_manage_server_permission(guild, bot_member))
    report.add(await probe_moderator_only_channel(guild, bot_member))
    report.add(await probe_hub_layout(guild))
    report.add(await probe_hub_announcements(guild, context, settings))
    report.add(await probe_leaders_access_current(guild, context))
    return report


async def run_server_init_stress_probes(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
    *,
    include_reinit: bool = True,
) -> ServerInitProbeReport:
    report = ServerInitProbeReport()
    report.add(await probe_operator_setup(guild, bot_member, settings))
    report.add(await probe_pre_init_smoke(guild, bot_member, settings))
    report.add(await probe_manage_server_permission(guild, bot_member))
    report.add(await probe_moderator_only_channel(guild, bot_member))
    report.add(await probe_hub_layout(guild))
    report.add(await probe_hub_announcements(guild, context, settings))
    report.add(await probe_leaders_drift_resync(guild, bot_member, context, settings))
    if include_reinit:
        report.add(
            await probe_reinit_rectifies_clients(
                guild,
                bot_member,
                bot,
                context,
                settings,
            )
        )
    report.add(await probe_leaders_access_current(guild, context))
    return report


def format_probe_report(report: ServerInitProbeReport) -> str:
    lines = ["Server init live probe report:"]
    for probe in report.probes:
        status = "OK" if probe.passed else "FAIL"
        lines.append(f"  [{status}] {probe.name}: {probe.detail}")
    lines.append(f"Overall: {'PASS' if report.passed else 'FAIL'}")
    return "\n".join(lines)
