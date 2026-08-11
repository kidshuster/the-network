#!/usr/bin/env bash
# Pre-flight Discord rate-limit probe for live smoke tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
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
from tests.core.rate_limit_probe import check_smoke_quota, format_quota_report


async def main() -> None:
    settings = Settings()
    report = await check_smoke_quota(
        token=settings.discord_token,
        guild_id=settings.guild_id,
    )
    print(format_quota_report(report))
    if not report.ready:
        raise SystemExit(1)


asyncio.run(main())
PY
