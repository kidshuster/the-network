#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

PROBE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --probe-only) PROBE_ONLY=1 ;;
    -h|--help)
      echo "Usage: $0 [--probe-only]"
      echo ""
      echo "Runs client onboarding smoke checks against the configured guild."
      echo "  --probe-only   Run pre-init provision probe only (no DB / no network required)"
      echo ""
      echo "Full E2E flow (default) exercises join-approval provisioning; when a network"
      echo "exists it also subscribes the smoke client and verifies publish-channel webhooks."
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

python - <<PY
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

from bot.config import Settings
from bot.smoke.discord_client import create_smoke_discord_client
from bot.smoke.provision_flow import (
    create_smoke_context,
    run_join_approval_smoke_flow,
    run_pre_init_smoke_checks,
)
from bot.smoke.resource_guard import cleanup_guild_test_artifacts


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
    probe_only = ${PROBE_ONLY}

    client = create_smoke_discord_client(members=True)
    smoke_bot = _SmokeBot(settings)
    result_holder: dict[str, object] = {}
    ready = asyncio.Event()
    failure: list[BaseException] = []

    @client.event
    async def on_ready() -> None:
        guild = None
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None:
                raise RuntimeError("configured guild not found")
            me = guild.me
            if me is None:
                raise RuntimeError("bot member missing in guild")

            smoke_bot.user = client.user
            smoke_bot._guild = guild

            smoke = await run_pre_init_smoke_checks(guild, me, settings)
            print("OK: guild init smoke checks passed")
            for step in smoke.operator_steps:
                print(f"  operator: {step}")
            for step in smoke.provision_steps:
                print(f"  provision: {step}")

            if probe_only:
                result_holder["done"] = True
                return

            db, context = await create_smoke_context(settings)
            smoke_bot.bot_context = context
            try:
                flow = await run_join_approval_smoke_flow(
                    guild,
                    smoke_bot,
                    context,
                )
                print("OK: join-approval E2E smoke flow passed")
                print(f"  accepted_request_id={flow.accepted_request_id}")
                print(f"  denied_request_id={flow.denied_request_id}")
                print(f"  profile_channel_id={flow.profile_channel_id}")
                if flow.publish_channel_id is not None:
                    print(
                        f"  publish_channel_id={flow.publish_channel_id} "
                        "(client webhook probe passed)"
                    )
                else:
                    print("  note: no networks registered — skipped subscribe/webhook probe")
            finally:
                await db.close()

            result_holder["done"] = True
        except BaseException as exc:
            failure.append(exc)
        finally:
            if guild is not None:
                removed = await cleanup_guild_test_artifacts(guild)
                if removed:
                    print(f"OK: cleaned up {len(removed)} stale test artifact(s)")
            ready.set()
            await client.close()

    async def _run_client() -> None:
        await client.start(settings.discord_token)

    client_task = asyncio.create_task(_run_client())
    timeout = 180.0
    try:
        await asyncio.wait_for(ready.wait(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        client_task.cancel()
        raise SystemExit(
            "FAIL: timed out waiting for smoke probes (Discord rate limits can stall "
            "role creation — wait a few minutes and retry)"
        ) from exc
    await client_task
    if failure:
        exc = failure[0]
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not result_holder.get("done"):
        raise SystemExit("FAIL: smoke run did not complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
PY
