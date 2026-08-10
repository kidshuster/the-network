#!/usr/bin/env bash
# Remove leftover probe/diag Discord artifacts (lightweight pre-flight cleanup).
# For full smoke client + guild teardown after a test batch, use bin/smoke_teardown.sh.
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
from bot.smoke.provision_flow import cleanup_all_hub_rebuild_smoke_clients, create_smoke_context
from bot.smoke.resource_guard import cleanup_guild_test_artifacts


async def main() -> None:
    settings = Settings()
    client = discord.Client(intents=discord.Intents.default())
    ready = asyncio.Event()
    failure: list[BaseException] = []

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None:
                raise RuntimeError("configured guild not found")
            bot_member = guild.me
            if bot_member is None:
                raise RuntimeError("bot member unavailable")

            db, context = await create_smoke_context(settings)
            try:
                removed = await cleanup_guild_test_artifacts(guild)
                manual = await cleanup_all_hub_rebuild_smoke_clients(
                    guild,
                    context,
                    bot_member,
                )
            finally:
                await db.close()

            if removed:
                print(f"OK: removed {len(removed)} test artifact(s)")
                for item in removed:
                    print(f"  - {item}")
            else:
                print("OK: no stale probe/diag artifacts")

            if manual:
                print(
                    f"WARN: {len(manual)} orphan channel(s) need manual deletion in Discord "
                    "(Server Settings → Channels):",
                    file=sys.stderr,
                )
                for item in manual:
                    print(f"  - {item}", file=sys.stderr)
        except BaseException as exc:
            failure.append(exc)
        finally:
            ready.set()
            await client.close()

    task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=90.0)
    except TimeoutError as exc:
        task.cancel()
        raise SystemExit(
            "FAIL: timed out waiting for Discord (stop the running bot and retry)"
        ) from exc
    await task
    if failure:
        exc = failure[0]
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


asyncio.run(main())
PY
