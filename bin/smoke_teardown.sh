#!/usr/bin/env bash
# Full smoke teardown — removes smoke clients, channels, categories, roles, and emojis.
# Run once after a batch of live smoke tests (not between each test in the batch).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
  echo "WARN: bot process is running — stop it first to avoid gateway conflicts." >&2
fi

python - <<'PY'
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

import discord

from bot.config import Settings
from bot.smoke.provision_flow import create_smoke_context
from bot.smoke.teardown import teardown_smoke_guild


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
                result = await teardown_smoke_guild(guild, context, bot_member)
            finally:
                await db.close()

            if result.removed_clients:
                print(f"OK: removed {len(result.removed_clients)} smoke client(s)")
                for name in result.removed_clients:
                    print(f"  - client:{name}")
            else:
                print("OK: no smoke clients in database")

            if result.removed_artifacts:
                print(f"OK: removed {len(result.removed_artifacts)} Discord artifact(s)")
                for item in result.removed_artifacts:
                    print(f"  - {item}")
            else:
                print("OK: no stale smoke channels, categories, roles, or emojis")

            if result.manual_channels:
                print(
                    f"WARN: {len(result.manual_channels)} channel(s) need manual deletion:",
                    file=sys.stderr,
                )
                for item in result.manual_channels:
                    print(f"  - {item}", file=sys.stderr)

            if result.errors:
                print("WARN: teardown completed with errors:", file=sys.stderr)
                for item in result.errors:
                    print(f"  - {item}", file=sys.stderr)
                raise SystemExit(1)
        except BaseException as exc:
            failure.append(exc)
        finally:
            ready.set()
            await client.close()

    task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=180.0)
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
