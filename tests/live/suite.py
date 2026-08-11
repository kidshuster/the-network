from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, cast

import discord

from bot.config import Settings
from tests.live.client_guard import (
    assert_protected_clients_unchanged,
    snapshot_protected_clients,
)
from tests.live.discord_client import create_smoke_discord_client
from tests.live.hub_announcements_probes import run_hub_announcements_smoke_flow
from tests.live.provision_flow import (
    create_smoke_context,
    ensure_smoke_network_key,
    run_configured_permission_provision_probe,
    run_hub_rebuild_smoke_flow,
    run_join_approval_smoke_flow,
)
from tests.live.resource_guard import cleanup_guild_test_artifacts
from tests.live.server_init_probes import (
    format_probe_report,
    run_server_init_functional_probes,
)
from tests.live.setup_welcome_probes import run_setup_welcome_smoke_flow
from tests.live.teardown import teardown_smoke_guild

if TYPE_CHECKING:
    from bot.client import NetworkRelayBot
    from bot.core.runtime import BotContext


class SmokeBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot_context: BotContext | None = None
        self.user: discord.ClientUser | None = None
        self._guild: discord.Guild | None = None

    def get_guild(self, guild_id: int) -> Any:
        if self._guild is not None and self._guild.id == guild_id:
            return self._guild
        return None

    def add_view(self, _view: object) -> None:
        return None


async def _phase_pause() -> None:
    delay = max(0.0, float(os.getenv("SMOKE_PHASE_DELAY_SEC", "2")))
    if delay:
        await asyncio.sleep(delay)


async def run_live_suite(
    guild: discord.Guild,
    bot: SmokeBot,
    settings: Settings,
) -> None:
    bot_member = guild.me
    if bot_member is None:
        raise RuntimeError("Bot member is unavailable in the configured guild.")

    db, context = await create_smoke_context(settings)
    bot.bot_context = context
    runtime_bot = cast("NetworkRelayBot", bot)
    protected = await snapshot_protected_clients(context, guild.id)
    try:
        removed = await cleanup_guild_test_artifacts(guild)
        print(f"OK: pre-flight cleanup removed {len(removed)} stale artifact(s)")
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="pre-flight cleanup",
        )

        permission_report = await run_configured_permission_provision_probe(
            guild,
            bot_member,
            settings,
        )
        print(
            "OK: permission/provision probe passed "
            "("
            f"{len(permission_report.operator_steps) + len(permission_report.provision_steps)} "
            "steps)"
        )
        await _phase_pause()

        join = await run_join_approval_smoke_flow(guild, runtime_bot, context)
        print(f"OK: join approval passed (request {join.accepted_request_id})")
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="join approval",
        )
        await _phase_pause()

        welcome = await run_setup_welcome_smoke_flow(guild, runtime_bot, context)
        print(f"OK: setup/welcome relay passed ({welcome.network_key})")
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="setup and welcome relay",
        )
        await _phase_pause()

        announcement = await run_hub_announcements_smoke_flow(guild, runtime_bot, context)
        print(f"OK: hub announcement relay passed ({announcement.network_key})")
        await _phase_pause()

        network_key = await ensure_smoke_network_key(context, runtime_bot, guild)
        rebuild = await run_hub_rebuild_smoke_flow(
            guild,
            runtime_bot,
            context,
            network_key=network_key,
            skip_cleanup=True,
        )
        print(f"OK: hub rebuild preserved client {rebuild.client_id} ({network_key})")
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="hub uninit/init and network rebuild",
        )
        await _phase_pause()

        report = await run_server_init_functional_probes(
            guild,
            bot_member,
            runtime_bot,
            context,
            settings,
        )
        if not report.passed:
            raise RuntimeError(format_probe_report(report))
        print(format_probe_report(report))
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="permission and layout rectification",
        )
    finally:
        teardown = await teardown_smoke_guild(guild, context, bot_member)
        await assert_protected_clients_unchanged(
            guild,
            context,
            protected,
            phase="final smoke teardown",
        )
        await db.close()
        if teardown.errors:
            raise RuntimeError("Smoke teardown failed: " + "; ".join(teardown.errors))


async def main() -> None:
    settings = Settings()
    client = create_smoke_discord_client(members=True)
    bot = SmokeBot(settings)
    ready = asyncio.Event()
    failures: list[BaseException] = []

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None:
                raise RuntimeError("Configured live-test guild was not found.")
            bot.user = client.user
            bot._guild = guild
            await run_live_suite(guild, bot, settings)
        except BaseException as exc:
            failures.append(exc)
        finally:
            ready.set()
            await client.close()

    task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=1800.0)
    except TimeoutError as exc:
        task.cancel()
        raise RuntimeError("Live suite timed out after 30 minutes.") from exc
    await task
    if failures:
        raise failures[0]


if __name__ == "__main__":
    asyncio.run(main())
