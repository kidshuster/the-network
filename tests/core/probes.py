from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord

from bot.config import Settings
from tests.core.client_guard import assert_protected_clients_unchanged
from tests.core.hub_announcements_probes import run_hub_announcements_smoke_flow
from tests.core.provision_flow import (
    ensure_smoke_network_key,
    run_configured_permission_provision_probe,
    run_hub_rebuild_smoke_flow,
    run_join_approval_smoke_flow,
)
from tests.core.resource_guard import cleanup_guild_test_artifacts
from tests.core.server_init_probes import (
    ProbeResult,
    probe_client_layout_reinit,
    probe_hub_announcements,
    probe_hub_layout,
    probe_leaders_access_current,
    probe_leaders_delete_double_reinit,
    probe_leaders_drift_resync,
    probe_leaders_idempotent_reinit,
    probe_manage_server_permission,
    probe_moderator_only_channel,
    probe_operator_setup,
    probe_reinit_rectifies_clients,
)
from tests.core.setup_welcome_probes import run_setup_welcome_smoke_flow
from tests.core.teardown import teardown_smoke_guild

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.database.connection import Database
    from bot.core.runtime import BotContext
    from tests.core.client_guard import ProtectedClient


@dataclass
class LiveContext:
    guild: discord.Guild
    bot_member: discord.Member
    bot: NetworkRelayBot
    settings: Settings
    database: Database
    runtime: BotContext
    protected_clients: tuple[ProtectedClient, ...]


@dataclass(frozen=True)
class ProbeOutcome:
    name: str
    detail: str


Probe = Callable[[LiveContext], Awaitable[ProbeOutcome]]
PROBES: dict[str, Probe] = {}


def register(name: str) -> Callable[[Probe], Probe]:
    def decorator(probe: Probe) -> Probe:
        if name in PROBES:
            raise RuntimeError(f"Duplicate live probe: {name}")
        PROBES[name] = probe
        return probe

    return decorator


def _checked(result: ProbeResult) -> ProbeOutcome:
    if not result.passed:
        raise RuntimeError(result.detail)
    return ProbeOutcome(result.name, result.detail)


async def _guard(context: LiveContext, phase: str) -> None:
    await assert_protected_clients_unchanged(
        context.guild,
        context.runtime,
        context.protected_clients,
        phase=phase,
    )


@register("artifacts.cleanup")
async def cleanup_artifacts(context: LiveContext) -> ProbeOutcome:
    removed = await cleanup_guild_test_artifacts(context.guild)
    return ProbeOutcome("artifact cleanup", f"removed {len(removed)} stale artifact(s)")


@register("permissions.provision")
async def permissions_provision(context: LiveContext) -> ProbeOutcome:
    result = await run_configured_permission_provision_probe(
        context.guild, context.bot_member, context.settings
    )
    count = len(result.operator_steps) + len(result.provision_steps)
    return ProbeOutcome("permission/provision", f"{count} API steps passed")


@register("onboarding.join_approval")
async def onboarding_join_approval(context: LiveContext) -> ProbeOutcome:
    result = await run_join_approval_smoke_flow(
        context.guild, context.bot, context.runtime
    )
    return ProbeOutcome("join approval", f"request {result.accepted_request_id}")


@register("relay.setup_welcome")
async def relay_setup_welcome(context: LiveContext) -> ProbeOutcome:
    result = await run_setup_welcome_smoke_flow(
        context.guild, context.bot, context.runtime
    )
    return ProbeOutcome("setup/welcome relay", result.network_key)


@register("relay.hub_announcement")
async def relay_hub_announcement(context: LiveContext) -> ProbeOutcome:
    result = await run_hub_announcements_smoke_flow(
        context.guild, context.bot, context.runtime
    )
    return ProbeOutcome("hub announcement relay", result.network_key)


@register("hub.rebuild")
async def hub_rebuild(context: LiveContext) -> ProbeOutcome:
    network_key = await ensure_smoke_network_key(
        context.runtime, context.bot, context.guild
    )
    result = await run_hub_rebuild_smoke_flow(
        context.guild,
        context.bot,
        context.runtime,
        network_key=network_key,
        skip_cleanup=True,
    )
    return ProbeOutcome("hub rebuild", f"preserved client {result.client_id}")


@register("hub.operator")
async def hub_operator(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_operator_setup(context.guild, context.bot_member, context.settings)
    )


@register("hub.manage_server")
async def hub_manage_server(context: LiveContext) -> ProbeOutcome:
    return _checked(await probe_manage_server_permission(context.guild, context.bot_member))


@register("hub.moderator_channel")
async def hub_moderator_channel(context: LiveContext) -> ProbeOutcome:
    return _checked(await probe_moderator_only_channel(context.guild, context.bot_member))


@register("hub.layout")
async def hub_layout(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_hub_layout(context.guild, context.bot_member, context.settings)
    )


@register("hub.announcement_channel")
async def hub_announcement_channel(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_hub_announcements(context.guild, context.runtime, context.settings)
    )


@register("hub.leaders_access")
async def hub_leaders_access(context: LiveContext) -> ProbeOutcome:
    return _checked(await probe_leaders_access_current(context.guild, context.runtime))


@register("hub.leaders_drift")
async def hub_leaders_drift(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_leaders_drift_resync(
            context.guild, context.bot_member, context.runtime, context.settings
        )
    )


@register("hub.client_layout_reinit")
async def hub_client_layout_reinit(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_client_layout_reinit(
            context.guild,
            context.bot_member,
            context.bot,
            context.runtime,
            context.settings,
        )
    )


@register("hub.reinit")
async def hub_reinit(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_reinit_rectifies_clients(
            context.guild,
            context.bot_member,
            context.bot,
            context.runtime,
            context.settings,
        )
    )


@register("hub.leaders_delete_reinit")
async def hub_leaders_delete_reinit(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_leaders_delete_double_reinit(
            context.guild,
            context.bot_member,
            context.bot,
            context.runtime,
            context.settings,
        )
    )


@register("hub.leaders_idempotent_reinit")
async def hub_leaders_idempotent_reinit(context: LiveContext) -> ProbeOutcome:
    return _checked(
        await probe_leaders_idempotent_reinit(
            context.guild,
            context.bot_member,
            context.bot,
            context.runtime,
            context.settings,
        )
    )


@register("clients.protected")
async def clients_protected(context: LiveContext) -> ProbeOutcome:
    await _guard(context, "explicit protected-client probe")
    return ProbeOutcome(
        "protected clients", f"{len(context.protected_clients)} client(s) unchanged"
    )


@register("artifacts.teardown")
async def teardown(context: LiveContext) -> ProbeOutcome:
    result = await teardown_smoke_guild(
        context.guild, context.runtime, context.bot_member
    )
    if result.errors:
        raise RuntimeError("; ".join(result.errors))
    return ProbeOutcome(
        "smoke teardown",
        f"removed {len(result.removed_clients)} client(s), "
        f"{len(result.removed_artifacts)} artifact(s)",
    )


def get_probe(name: str) -> Probe:
    try:
        return PROBES[name]
    except KeyError as exc:
        available = ", ".join(sorted(PROBES))
        raise KeyError(f"Unknown live probe {name!r}; available: {available}") from exc
