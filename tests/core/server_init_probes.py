from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from bot.app.widgets import PersistentViewRegistry
from bot.config import Settings
from bot.core.clients.names import slugify_client_name
from bot.core.networks.roles import (
    resolve_access_role,
    resolve_operator_role_by_name,
    validate_hub_permissions,
)
from bot.features.channels.layout import LayoutContext, compile_client, compile_hub
from bot.features.channels.layout.compiler import ResourceKind
from bot.features.channels.layout.managed import (
    hub_category_names,
    hub_channel_aliases,
    preserved_channel_names,
)
from bot.features.channels.resolve import (
    CATEGORY_LEADERS,
    CATEGORY_MODERATION,
    CHANNEL_ADMIN,
    CHANNEL_CHANGELOG,
    CHANNEL_LEADERS,
    resolve_changelog_channel,
    resolve_human_moderator_role,
    resolve_leaders_category,
    resolve_leaders_channel,
)
from bot.features.recipes.hub.initialize import initialize_guild
from bot.features.recipes.hub.leaders import ensure_leaders_channels
from tests.core.constants import SERVER_INIT_PROBE_REASON
from tests.core.provision_flow import run_configured_permission_provision_probe
from tests.core.resource_guard import guild_test_resource_guard, is_smoke_client_server_name

if TYPE_CHECKING:
    from bot.app.bot import NetworkRelayBot
    from bot.app.context import BotContext

logger = logging.getLogger(__name__)

_PROBE_REASON = SERVER_INIT_PROBE_REASON


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
    for client in await context.store.clients.list_all():
        if client.guild_id != guild.id:
            continue
        role = guild.get_role(client.client_role_id)
        if role is None:
            continue
        clients.append((client.server_name, role))
    return sorted(clients, key=lambda item: (not is_smoke_client_server_name(item[0]), item[0]))


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


async def probe_permission_provision(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> ProbeResult:
    """Run the standalone permission and provisioning API probe."""
    try:
        smoke = await run_configured_permission_provision_probe(guild, bot_member, settings)
    except Exception as exc:
        return ProbeResult("permission/provision probe", False, str(exc))

    steps = [*smoke.operator_steps, *smoke.provision_steps]
    return ProbeResult(
        "permission/provision probe",
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


async def probe_admin_channel(
    guild: discord.Guild,
    bot_member: discord.Member,
) -> ProbeResult:
    for channel in guild.text_channels:
        if channel.name.casefold() != CHANNEL_ADMIN:
            continue
        perms = channel.permissions_for(bot_member)
        if not perms.view_channel:
            return ProbeResult(
                "admin channel",
                False,
                (
                    f"#{channel.name} exists outside hub control and denies bot view "
                    f"(category={channel.category.name if channel.category else 'none'}) — "
                    "init cannot move it; delete it or grant **The Testwork +** view access"
                ),
            )
        if channel.category is None or channel.category.name != CATEGORY_MODERATION:
            return ProbeResult(
                "admin channel",
                False,
                (
                    f"#{channel.name} is visible but not in **{CATEGORY_MODERATION}** — "
                    "re-run `/server init` after fixing layout"
                ),
            )
        return ProbeResult(
            "admin channel",
            True,
            f"#{CHANNEL_ADMIN} is in **{CATEGORY_MODERATION}**",
        )
    return ProbeResult(
        "admin channel",
        True,
        f"no #{CHANNEL_ADMIN} channel present (init will create one)",
    )


def _hub_layout_context(
    guild: discord.Guild,
    bot_member: discord.Member,
    settings: Settings,
) -> LayoutContext:
    access = resolve_access_role(guild, role_name=settings.network_access_role_name)
    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    return LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access,
        moderator_role=resolve_human_moderator_role(guild),
        operator_role=operator,
        reason=_PROBE_REASON,
    )


def _channel_by_name(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    target = name.casefold()
    for channel in guild.text_channels:
        if channel.name.casefold() == target:
            return channel
    return None


def _channel_by_names(
    guild: discord.Guild,
    names: tuple[str, ...] | list[str],
) -> discord.TextChannel | None:
    for name in names:
        found = _channel_by_name(guild, name)
        if found is not None:
            return found
    return None


def _overwrite_matches(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
    desired: discord.PermissionOverwrite,
) -> bool:
    current = channel.overwrites_for(role)
    return (
        current.pair()[0].value == desired.pair()[0].value
        and current.pair()[1].value == desired.pair()[1].value
    )


async def probe_hub_layout(
    guild: discord.Guild,
    bot_member: discord.Member | None = None,
    settings: Settings | None = None,
) -> ProbeResult:
    """Assert live hub categories/channels match YAML compile_hub output."""
    expected_categories = hub_category_names()
    missing_cats = [
        name
        for name in sorted(expected_categories)
        if not any(cat.name.casefold() == name for cat in guild.categories)
    ]
    if missing_cats:
        return ProbeResult(
            "hub layout",
            False,
            f"missing categories: {', '.join(missing_cats)} — run `/server init` first",
        )

    # Prefer compiled names when roles are available; fall back to YAML names.
    expected_channels: list[tuple[str, tuple[str, ...]]] = []
    community_missing: list[str] = []
    if bot_member is not None and settings is not None:
        try:
            ctx = _hub_layout_context(guild, bot_member, settings)
            for resource in compile_hub(ctx):
                if resource.kind is ResourceKind.CATEGORY:
                    continue
                aliases = hub_channel_aliases(resource.id)
                expected_channels.append((resource.name, aliases))
                if resource.community_slot is not None:
                    found = _channel_by_names(guild, aliases)
                    if found is None:
                        community_missing.append(resource.name)
                    elif (
                        resource.community_slot == "rules"
                        and guild.rules_channel is not None
                        and guild.rules_channel.id != found.id
                    ):
                        community_missing.append(
                            f"{resource.name} (not bound as guild.rules_channel)"
                        )
        except Exception as exc:
            return ProbeResult("hub layout", False, f"compile_hub failed: {exc}")
    else:
        from bot.features.channels.layout.loader import load_layout

        for category in load_layout().layout.categories.values():
            for channel_id, channel in category.channels.items():
                aliases = hub_channel_aliases(channel_id)
                expected_channels.append((channel.name, aliases))

    missing_channels = [
        name
        for name, aliases in expected_channels
        if _channel_by_names(guild, aliases) is None
    ]
    # Allow legacy leaders name (retired alias, not in layout.legacy_names).
    if "leaders-channel" in missing_channels and _channel_by_name(guild, "leaders"):
        missing_channels.remove("leaders-channel")

    problems = [
        *(f"category:{n}" for n in missing_cats),
        *(f"channel:{n}" for n in missing_channels),
        *(f"community:{n}" for n in community_missing),
    ]
    if problems:
        return ProbeResult(
            "hub layout",
            False,
            "missing YAML hub resources: " + ", ".join(problems[:8]),
        )

    preserved = preserved_channel_names()
    detail = (
        f"{len(expected_categories)} hub categories, {len(expected_channels)} channels; "
        f"preserved/community={', '.join(sorted(preserved)) or 'none'}"
    )
    return ProbeResult("hub layout", True, detail)


async def probe_hub_announcements(
    guild: discord.Guild,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    del context, settings
    from bot.features.channels.layout.managed import hub_channel_name
    from bot.features.channels.resolve import (
        HUB_CHANNEL_NETWORK_ANNOUNCEMENTS,
        resolve_moderation_category,
        resolve_network_announcements_channel,
    )

    mod_category = resolve_moderation_category(guild)
    mod_channel = resolve_network_announcements_channel(guild)
    if mod_channel is None:
        return ProbeResult(
            "hub announcements channel",
            False,
            f"#{hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)} missing — run `/server init`",
        )
    if mod_category is not None and mod_channel.category_id != mod_category.id:
        return ProbeResult(
            "hub announcements channel",
            False,
            f"#{hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)} is outside Moderation",
        )
    if mod_channel.is_news():
        return ProbeResult(
            "hub announcements channel",
            False,
            (
                f"#{hub_channel_name(HUB_CHANNEL_NETWORK_ANNOUNCEMENTS)} "
                "must be a regular text channel — run `/server init`"
            ),
        )
    return ProbeResult(
        "hub announcements wiring",
        True,
        f"{mod_channel.mention} is a regular text channel with direct relay dispatch",
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
    """Remove one role overwrite without forcing sync_permissions=False (avoids bot lockout)."""
    if role not in channel.overwrites:
        return
    await channel.set_permissions(role, overwrite=None, reason=_PROBE_REASON)


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
            "the standard `./test --full` suite first",
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


async def probe_client_layout_reinit(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Strip client category/profile overwrites, reinit, assert compile_client match."""
    clients = sorted(
        [
        client for client in await context.store.clients.list_all() if client.guild_id == guild.id
        ],
        key=lambda client: (
            not is_smoke_client_server_name(client.server_name),
            client.server_name,
        ),
    )
    if not clients:
        return ProbeResult(
            "client layout reinit",
            True,
            "skipped — no registered clients",
        )

    client = clients[0]
    client_role = guild.get_role(client.client_role_id)
    category = guild.get_channel(client.category_id)
    profile = guild.get_channel(client.profile_channel_id)
    if client_role is None or not isinstance(category, discord.CategoryChannel):
        return ProbeResult(
            "client layout reinit",
            False,
            f"{client.server_name}: client role or category missing",
        )
    if not isinstance(profile, discord.TextChannel):
        return ProbeResult(
            "client layout reinit",
            False,
            f"{client.server_name}: profile channel missing",
        )

    access = resolve_access_role(guild, role_name=settings.network_access_role_name)
    operator = resolve_operator_role_by_name(
        guild,
        role_name=settings.network_operator_role_name,
    )
    human_mod = resolve_human_moderator_role(guild)
    layout_ctx = LayoutContext(
        guild=guild,
        bot_member=bot_member,
        access_role=access,
        moderator_role=human_mod,
        operator_role=operator,
        client_role=client_role,
        server_name=client.server_name,
        slug=slugify_client_name(client.server_name),
        reason=_PROBE_REASON,
    )
    desired = {
        resource.id: resource
        for resource in compile_client(layout_ctx, channel_ids={"client", "profile"})
    }

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await _strip_role_overwrite(category, client_role)
        await _strip_role_overwrite(profile, client_role)

        view_registry = PersistentViewRegistry(bot)
        result = await initialize_guild(
            guild,
            bot_member,
            access_role_name=settings.network_access_role_name,
            operator_role_name=settings.network_operator_role_name,
            clients=await context.store.clients.list_all(),
            bot=bot,
            context=context,
            view_registry=view_registry,
        )
        if not result.success:
            return ProbeResult(
                "client layout reinit",
                False,
                result.reason or "initialize_guild failed",
            )

        mismatches: list[str] = []
        cat_desired = desired["client"].overwrites.get(client_role)
        if cat_desired is not None and not _overwrite_matches(category, client_role, cat_desired):
            mismatches.append("category client overwrite")
        profile_desired = desired["profile"].overwrites.get(client_role)
        if profile_desired is not None and not _overwrite_matches(
            profile, client_role, profile_desired
        ):
            mismatches.append("profile client overwrite")

        gaps = await _collect_leaders_access_gaps(guild, context)
        client_gaps = [g for g in gaps if g.startswith(f"{client.server_name}:")]
        if mismatches or client_gaps:
            return ProbeResult(
                "client layout reinit",
                False,
                "; ".join([*mismatches, *client_gaps[:3]]),
            )
        return ProbeResult(
            "client layout reinit",
            True,
            f"restored compile_client overwrites + Leaders for **{client.server_name}**",
        )


async def probe_reinit_rectifies_clients(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Run initialize_guild against live layout and verify client/Leaders rectification."""
    clients = await context.store.clients.list_all()
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

        view_registry = PersistentViewRegistry(bot)
        result = await initialize_guild(
            guild,
            bot_member,
            access_role_name=settings.network_access_role_name,
            operator_role_name=settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            view_registry=view_registry,
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


async def probe_leaders_delete_double_reinit(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Delete #leaders-channel, reinit twice — permissions restored, no false warnings."""
    clients = await context.store.clients.list_all()
    guild_clients = [client for client in clients if client.guild_id == guild.id]
    if not guild_clients:
        return ProbeResult(
            "leaders delete reinit",
            True,
            "skipped — no registered clients",
        )

    leaders = resolve_leaders_channel(guild)
    changelog = resolve_changelog_channel(guild)
    if leaders is None or changelog is None:
        return ProbeResult(
            "leaders delete reinit",
            False,
            "Leaders layout missing — run `/server init` first",
        )

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        await leaders.delete(reason=_PROBE_REASON)

        view_registry = PersistentViewRegistry(bot)
        first = await initialize_guild(
            guild,
            bot_member,
            access_role_name=settings.network_access_role_name,
            operator_role_name=settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            view_registry=view_registry,
        )
        if not first.success:
            return ProbeResult(
                "leaders delete reinit",
                False,
                first.reason or "first initialize_guild failed after deleting leaders channel",
            )
        if first.rectification_failures:
            return ProbeResult(
                "leaders delete reinit",
                False,
                "first reinit reported failures: " + "; ".join(first.rectification_failures[:5]),
            )

        restored = resolve_leaders_channel(guild)
        if restored is None:
            return ProbeResult(
                "leaders delete reinit",
                False,
                "#leaders-channel was not recreated",
            )
        gaps = await _collect_leaders_access_gaps(guild, context)
        if gaps:
            return ProbeResult(
                "leaders delete reinit",
                False,
                "Leaders access missing after recreate: " + "; ".join(gaps[:5]),
            )

        second = await initialize_guild(
            guild,
            bot_member,
            access_role_name=settings.network_access_role_name,
            operator_role_name=settings.network_operator_role_name,
            clients=clients,
            bot=bot,
            context=context,
            view_registry=view_registry,
        )
        if not second.success:
            return ProbeResult(
                "leaders delete reinit",
                False,
                second.reason or "second initialize_guild failed",
            )
        if second.rectification_failures:
            return ProbeResult(
                "leaders delete reinit",
                False,
                "second reinit should be clean but reported: "
                + "; ".join(second.rectification_failures[:5]),
            )

    return ProbeResult(
        "leaders delete reinit",
        True,
        f"recreated {restored.mention}; second reinit had no rectification failures",
    )


async def probe_leaders_idempotent_reinit(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ProbeResult:
    """Run initialize_guild twice on unchanged layout — no spurious rectification failures."""
    clients = await context.store.clients.list_all()
    if not [client for client in clients if client.guild_id == guild.id]:
        return ProbeResult(
            "leaders idempotent reinit",
            True,
            "skipped — no registered clients",
        )

    async with guild_test_resource_guard(guild, bot_member=bot_member):
        view_registry = PersistentViewRegistry(bot)
        for pass_label in ("first", "second"):
            result = await initialize_guild(
                guild,
                bot_member,
                access_role_name=settings.network_access_role_name,
                operator_role_name=settings.network_operator_role_name,
                clients=clients,
                bot=bot,
                context=context,
                view_registry=view_registry,
            )
            if not result.success:
                return ProbeResult(
                    "leaders idempotent reinit",
                    False,
                    f"{pass_label} initialize_guild failed: {result.reason or 'unknown'}",
                )
            if result.rectification_failures:
                return ProbeResult(
                    "leaders idempotent reinit",
                    False,
                    f"{pass_label} reinit reported rectification failures: "
                    + "; ".join(result.rectification_failures[:5]),
                )
            gaps = await _collect_leaders_access_gaps(guild, context)
            if gaps:
                return ProbeResult(
                    "leaders idempotent reinit",
                    False,
                    f"{pass_label} reinit left Leaders access gaps: " + "; ".join(gaps[:5]),
                )

    return ProbeResult(
        "leaders idempotent reinit",
        True,
        "two consecutive inits had no rectification failures; client roles retain access",
    )


async def run_server_init_audit(
    guild: discord.Guild,
    bot_member: discord.Member,
    context: BotContext,
    settings: Settings,
) -> ServerInitProbeReport:
    report = ServerInitProbeReport()
    report.add(await probe_operator_setup(guild, bot_member, settings))
    report.add(await probe_permission_provision(guild, bot_member, settings))
    report.add(await probe_manage_server_permission(guild, bot_member))
    report.add(await probe_admin_channel(guild, bot_member))
    report.add(await probe_hub_layout(guild, bot_member, settings))
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
    report.add(await probe_permission_provision(guild, bot_member, settings))
    report.add(await probe_manage_server_permission(guild, bot_member))
    report.add(await probe_admin_channel(guild, bot_member))
    report.add(await probe_hub_layout(guild, bot_member, settings))
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
        report.add(
            await probe_client_layout_reinit(
                guild,
                bot_member,
                bot,
                context,
                settings,
            )
        )
        report.add(
            await probe_leaders_delete_double_reinit(
                guild,
                bot_member,
                bot,
                context,
                settings,
            )
        )
        report.add(
            await probe_leaders_idempotent_reinit(
                guild,
                bot_member,
                bot,
                context,
                settings,
            )
        )
    report.add(await probe_leaders_access_current(guild, context))
    return report


async def run_server_init_functional_probes(
    guild: discord.Guild,
    bot_member: discord.Member,
    bot: NetworkRelayBot,
    context: BotContext,
    settings: Settings,
) -> ServerInitProbeReport:
    """Cover production behavior once without repeating rate-heavy burn-in probes."""
    report = ServerInitProbeReport()
    report.add(await probe_operator_setup(guild, bot_member, settings))
    report.add(await probe_manage_server_permission(guild, bot_member))
    report.add(await probe_admin_channel(guild, bot_member))
    report.add(await probe_hub_layout(guild, bot_member, settings))
    report.add(await probe_hub_announcements(guild, context, settings))
    report.add(await probe_leaders_drift_resync(guild, bot_member, context, settings))
    report.add(await probe_client_layout_reinit(guild, bot_member, bot, context, settings))
    report.add(await probe_leaders_access_current(guild, context))
    return report


def format_probe_report(report: ServerInitProbeReport) -> str:
    lines = ["Server init live probe report:"]
    for probe in report.probes:
        status = "OK" if probe.passed else "FAIL"
        lines.append(f"  [{status}] {probe.name}: {probe.detail}")
    lines.append(f"Overall: {'PASS' if report.passed else 'FAIL'}")
    return "\n".join(lines)
