#!/usr/bin/env bash
# Live Discord server-init probes — NOT part of pytest / CI.
# Targets the guild in .env (use bin/use-staging-env.sh for staging).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

MODE="audit"
for arg in "$@"; do
  case "$arg" in
    --audit) MODE="audit" ;;
    --stress) MODE="stress" ;;
    --leaders-drift) MODE="leaders-drift" ;;
    --leaders-delete-reinit) MODE="leaders-delete-reinit" ;;
    --reinit) MODE="reinit" ;;
    -h|--help)
      cat <<'EOF'
Usage: tests/live/smoke_server_init.sh [--audit|--stress|--leaders-drift|--leaders-delete-reinit|--reinit]

Live server-init probes against the configured guild (.env). These scripts hit
the real Discord API and are intentionally excluded from pytest.

Stop the running bot before probing (only one gateway session per token).

Modes:
  --audit         Read-only checks + current Leaders access audit (default)
  --leaders-drift Simulate missing client Leaders overwrites and verify resync
  --leaders-delete-reinit Delete #leaders-channel, reinit twice (permissions + no false warnings)
  --reinit        Run initialize_guild and verify client/Leaders rectification
  --stress        audit + leaders-drift + reinit

Requires hub layout from `/server init` for layout-dependent probes.
Leaders drift/reinit probes need at least one registered client — run
Run `./test --full` first if the database has no smoke client available.
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
  echo "WARN: bot process is running — stop it first to avoid gateway conflicts." >&2
fi

python - <<PY
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"))

from bot.config import Settings
from tests.live.discord_client import create_smoke_discord_client
from tests.live.provision_flow import create_smoke_context
from tests.live.server_init_probes import (
    format_probe_report,
    probe_leaders_drift_resync,
    probe_leaders_delete_double_reinit,
    probe_reinit_rectifies_clients,
    run_server_init_audit,
    run_server_init_stress_probes,
)


class _ProbeBot:
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
    mode = "${MODE}"

    client = create_smoke_discord_client(members=True)
    probe_bot = _ProbeBot(settings)
    ready = asyncio.Event()
    failure: list[BaseException] = []
    report_holder: dict[str, object] = {}

    @client.event
    async def on_ready() -> None:
        try:
            guild = client.get_guild(settings.guild_id)
            if guild is None:
                raise RuntimeError("configured guild not found")
            me = guild.me
            if me is None:
                raise RuntimeError("bot member missing in guild")

            probe_bot.user = client.user
            probe_bot._guild = guild

            db, context = await create_smoke_context(settings)
            probe_bot.bot_context = context
            try:
                if mode == "audit":
                    report = await run_server_init_audit(guild, me, context, settings)
                elif mode == "leaders-drift":
                    from tests.live.server_init_probes import ServerInitProbeReport

                    report = ServerInitProbeReport()
                    probe = await probe_leaders_drift_resync(guild, me, context, settings)
                    report.add(probe)
                elif mode == "leaders-delete-reinit":
                    from tests.live.server_init_probes import ServerInitProbeReport

                    report = ServerInitProbeReport()
                    probe = await probe_leaders_delete_double_reinit(
                        guild,
                        me,
                        probe_bot,
                        context,
                        settings,
                    )
                    report.add(probe)
                elif mode == "reinit":
                    from tests.live.server_init_probes import ServerInitProbeReport

                    report = ServerInitProbeReport()
                    probe = await probe_reinit_rectifies_clients(
                        guild,
                        me,
                        probe_bot,
                        context,
                        settings,
                    )
                    report.add(probe)
                elif mode == "stress":
                    report = await run_server_init_stress_probes(
                        guild,
                        me,
                        probe_bot,
                        context,
                        settings,
                    )
                else:
                    raise RuntimeError(f"unknown mode: {mode}")

                report_holder["report"] = report
                print(format_probe_report(report))
            finally:
                await db.close()
        except BaseException as exc:
            failure.append(exc)
        finally:
            ready.set()
            await client.close()

    client_task = asyncio.create_task(client.start(settings.discord_token))
    timeout = 900.0 if mode == "stress" else 300.0
    try:
        await asyncio.wait_for(ready.wait(), timeout=timeout)
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
    report = report_holder.get("report")
    if report is None or not getattr(report, "passed", False):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
PY
