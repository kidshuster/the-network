#!/usr/bin/env bash
# Hub rebuild smoke: provision client → uninit → init → recreate network → verify relink.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

if [[ -z "${SMOKE_NETWORK_KEY:-}" ]]; then
  echo "Set SMOKE_NETWORK_KEY to the network key used for rebuild smoke." >&2
  exit 2
fi

python - <<'PY'
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

import discord

from bot.config import Settings
from bot.smoke.discord_client import create_smoke_discord_client
from bot.smoke.provision_flow import create_smoke_context, run_hub_rebuild_smoke_flow


class _SmokeBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot_context = None
        self.user = None
        self._guild: discord.Guild | None = None

    def get_guild(self, guild_id: int) -> discord.Guild | None:
        if self._guild is not None and self._guild.id == guild_id:
            return self._guild
        return None

    def add_view(self, _view: object) -> None:
        return None


async def main() -> None:
    settings = Settings()
    client = create_smoke_discord_client(members=True)
    smoke_bot = _SmokeBot(settings)
    ready = asyncio.Event()
    failure: list[BaseException] = []

    @client.event
    async def on_ready() -> None:
        try:
            smoke_bot.user = client.user
            guild = client.get_guild(settings.guild_id)
            smoke_bot._guild = guild
            if guild is None:
                raise RuntimeError("configured guild not found")
            db, context = await create_smoke_context(settings)
            smoke_bot.bot_context = context
            try:
                state = await run_hub_rebuild_smoke_flow(guild, smoke_bot, context)
            finally:
                await db.close()
            print("OK: hub rebuild smoke passed")
            print(f"  client_id={state.client_id}")
            print(f"  publish_channel_id={state.publish_channel_id}")
            print(f"  subscribe_channel_id={state.subscribe_channel_id}")
            print(f"  network_key={state.network_key}")
        except BaseException as exc:
            failure.append(exc)
        finally:
            ready.set()
            await client.close()

    client_task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=300.0)
    except asyncio.TimeoutError as exc:
        client_task.cancel()
        raise SystemExit(
            "FAIL: timed out waiting for Discord (stop the running bot and retry)"
        ) from exc
    await client_task
    if failure:
        exc = failure[0]
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


asyncio.run(main())
PY
