#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1
python - <<'PY'
import asyncio
import inspect
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

import discord

from bot.cogs.servers import ServerCog
from bot.services.server_request_service import (
    ServerRequestService,
    build_moderator_request_embed,
)
from bot.ui.join_views import JoinNetworkView, ModeratorReviewView
from bot.ui.network_admin_views import NetworkAdminView
from bot.ui.network_views import NetworkProfileView


def _assert_command(cog_cls: type, group: str, name: str) -> None:
    commands = getattr(cog_cls, "__cog_app_commands__", ())
    matches = [cmd for cmd in commands if cmd.name == name]
    if not matches:
        raise SystemExit(f"FAIL: /{group} {name} command not registered")
    print(f"OK: /{group} {name} registered")


_assert_command(ServerCog, "server", "init")
_assert_command(ServerCog, "server", "uninit")
_assert_command(ServerCog, "server", "sync-join-guide")

for fn in (
    ServerRequestService.submit_request,
    ServerRequestService.approve_request,
    ServerRequestService.deny_request,
):
    if not inspect.iscoroutinefunction(fn):
        raise SystemExit(f"FAIL: expected async handler {fn.__qualname__}")

embed = build_moderator_request_embed(
    requester=type("User", (), {"mention": "<@1>"})(),
    server_name="Smoke Server",
    display_name="Smoke",
    request_id=1,
)
if embed.title != "Client join request":
    raise SystemExit("FAIL: moderator request embed title mismatch")

print("OK: button/command parity handlers present")
print("  join network modal   -> Join Network button")
print("  accept/deny buttons  -> join-requests channel")
print("  create/delete network -> #commands admin panel")
print("  server init/uninit   -> hub layout commands")
print("  network-profile view -> Edit Profile + network subscribe buttons")


async def main() -> None:
    from bot.config import Settings

    settings = Settings()
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        guild = client.get_guild(settings.guild_id)
        if guild is None:
            raise SystemExit("FAIL: configured guild not found")

        bot_stub = type("BotStub", (), {"settings": settings, "add_view": lambda *_: None})()
        join_view = JoinNetworkView(bot_stub)
        review_view = ModeratorReviewView(bot_stub, 1)
        admin_view = NetworkAdminView(bot_stub)
        profile_view = NetworkProfileView(bot_stub, 1, ["stingers"])

        if len(join_view.children) != 1:
            raise SystemExit("FAIL: JoinNetworkView missing button")
        if len(review_view.children) != 2:
            raise SystemExit("FAIL: ModeratorReviewView missing Accept/Deny buttons")
        if len(admin_view.children) != 2:
            raise SystemExit("FAIL: NetworkAdminView missing Create/Delete buttons")
        if len(profile_view.children) < 1:
            raise SystemExit("FAIL: NetworkProfileView missing buttons")

        print("OK: persistent views build for live guild", guild.name)
        await client.close()

    await client.start(settings.discord_token)


asyncio.run(main())
PY
