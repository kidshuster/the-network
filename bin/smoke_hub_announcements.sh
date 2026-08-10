#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

python - <<'PY'
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

import discord

from bot.config import Settings
from bot.smoke.provision_flow import create_smoke_context
from bot.smoke.hub_announcements_probes import run_hub_announcements_smoke_flow


class _SmokeBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot_context = None
        self.user = None
        self._guild = None

    def get_guild(self, guild_id: int):
        if self._guild is not None and self._guild.id == guild_id:
            return self._guild
        return None

    def add_view(self, _view: object) -> None:
        return None


async def main() -> None:
    settings = Settings()
    intents = discord.Intents.default()
    intents.members = True
    client = discord.Client(intents=intents)
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
                result = await run_hub_announcements_smoke_flow(
                    guild,
                    smoke_bot,
                    context,
                )
                print("OK: hub announcements smoke passed")
                print(f"  hub_client_id={result.hub_client_id}")
                print(f"  network_key={result.network_key}")
            finally:
                await db.close()
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
            "FAIL: timed out waiting for hub announcements smoke (stop the running bot and retry)"
        ) from exc
    await client_task
    if failure:
        print(f"FAIL: {failure[0]}", file=sys.stderr)
        raise SystemExit(1) from failure[0]


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
PY
