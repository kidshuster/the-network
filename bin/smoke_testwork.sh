#!/usr/bin/env bash
# Full live smoke/stress run for the configured Testwork guild (.env).
# NOT part of pytest — hits the real Discord API.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

RESTART_BOT=1
for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART_BOT=0 ;;
    -h|--help)
      cat <<'EOF'
Usage: bin/smoke_testwork.sh [--no-restart]

Runs the full live smoke/stress suite against the guild in .env (Testwork staging).

Stop the running bot first — only one gateway session per token.

Steps:
  1. smoke_button_commands     — slash/view parity
  2. smoke_provision_flow --probe-only
  3. smoke_provision_flow      — join-approval E2E (+ subscribe when network exists)
  4. smoke_setup_welcome       — setup sticky copy + welcome/blacklist behavior
  5. smoke_hub_announcements   — hub client relay + write-only guard
  6. ensure smoke network + hub rebuild smoke
  7. smoke_server_init --stress
  8. smoke_cleanup_artifacts
  9. restart bot (unless --no-restart)

Prerequisites: hub initialized via /server init; operator role fully permissioned.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
  echo "Stopping running bot..." >&2
  pkill -f "python -m bot.main" || true
  sleep 2
fi

run_step() {
  echo ""
  echo "==> $1"
  shift
  "$@"
  # Let Discord release the gateway session before the next live smoke step.
  sleep 3
}

run_step "pre-flight artifact cleanup" "$ROOT/bin/smoke_cleanup_artifacts.sh"

run_step "button/command parity" "$ROOT/bin/smoke_button_commands.sh"
run_step "pre-init provision probe" "$ROOT/bin/smoke_provision_flow.sh" --probe-only
run_step "join-approval E2E" "$ROOT/bin/smoke_provision_flow.sh"

run_step "setup sticky + welcome smoke" "$ROOT/bin/smoke_setup_welcome.sh"

run_step "hub announcements smoke" "$ROOT/bin/smoke_hub_announcements.sh"

run_step "ensure smoke network + hub rebuild" python - <<'PY'
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

import discord

from bot.config import Settings
from bot.smoke.provision_flow import (
    create_smoke_context,
    ensure_smoke_network_key,
    run_hub_rebuild_smoke_flow,
)


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
                network_key = await ensure_smoke_network_key(context, smoke_bot, guild)
                os.environ["SMOKE_NETWORK_KEY"] = network_key
                print(f"OK: using network key {network_key!r}")
                state = await run_hub_rebuild_smoke_flow(
                    guild,
                    smoke_bot,
                    context,
                    skip_cleanup=True,
                )
                print("OK: hub rebuild smoke passed")
                print(f"  client_id={state.client_id}")
                print(f"  network_key={state.network_key}")
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
        raise SystemExit("FAIL: timed out during hub rebuild smoke") from exc
    await client_task
    if failure:
        raise failure[0]


asyncio.run(main())
PY

export SMOKE_NETWORK_KEY="${SMOKE_NETWORK_KEY:-smoke}"
run_step "server init stress probes" "$ROOT/bin/smoke_server_init.sh" --stress
run_step "cleanup smoke artifacts" "$ROOT/bin/smoke_cleanup_artifacts.sh"

echo ""
echo "OK: Testwork smoke/stress suite passed"

if [[ "$RESTART_BOT" -eq 1 ]]; then
  echo "Starting bot..."
  nohup python -m bot.main > /tmp/the-network-bot.log 2>&1 &
  sleep 3
  if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
    echo "OK: bot restarted (log: /tmp/the-network-bot.log)"
  else
    echo "WARN: bot did not stay running — check /tmp/the-network-bot.log" >&2
    exit 1
  fi
fi
