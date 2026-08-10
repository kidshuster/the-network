#!/usr/bin/env bash
# Run `/server uninit` equivalent against the configured guild (bot must be stopped).
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

from bot.config import Settings
from bot.smoke.discord_client import create_smoke_discord_client
from bot.hub.uninit import uninitialize_guild


async def main() -> None:
    settings = Settings()
    client = create_smoke_discord_client(members=True)
    failure: list[BaseException] = []
    ready = asyncio.Event()

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None:
                raise RuntimeError("configured guild not found")
            me = guild.me
            if me is None:
                raise RuntimeError("bot member missing in guild")

            result = await uninitialize_guild(
                guild,
                me,
                access_role_name=settings.network_access_role_name,
                operator_role_name=settings.network_operator_role_name,
            )
            print(f"OK: server uninit finished (success={result.success})")
            if result.deleted_channels:
                print(f"  deleted_channels={len(result.deleted_channels)}")
            if result.deleted_categories:
                print(f"  deleted_categories={len(result.deleted_categories)}")
            if result.deleted_roles:
                print(f"  deleted_roles={len(result.deleted_roles)}")
            if result.failed_steps:
                print("  failed_steps:")
                for step in result.failed_steps:
                    print(f"    - {step}")
            if result.notes:
                for note in result.notes:
                    print(f"  note: {note}")
            if result.reason:
                print(f"  reason: {result.reason}")
        except BaseException as exc:
            failure.append(exc)
        finally:
            ready.set()
            await client.close()

    client_task = asyncio.create_task(client.start(settings.discord_token))
    try:
        await asyncio.wait_for(ready.wait(), timeout=120.0)
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
