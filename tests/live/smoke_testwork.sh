#!/usr/bin/env bash
# Full live behavioral suite. Uses one Discord gateway session to minimize API pressure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1

RESTART_BOT=1
CHECK_QUOTA=0
for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART_BOT=0 ;;
    --check-quota) CHECK_QUOTA=1 ;;
    --skip-quota-check) CHECK_QUOTA=0 ;; # Backward-compatible no-op.
    -h|--help)
      cat <<'EOF'
Usage: tests/live/smoke_testwork.sh [--no-restart] [--check-quota]

Runs one consolidated live session covering permissions, provisioning, recipes,
relay behavior, layout rectification, hub rebuild, and protected-client survival.

--check-quota runs a destructive six-call bucket diagnostic. It is normally
omitted to preserve Discord mutation quota.

For repeated destructive burn-in only, run:
  tests/live/smoke_server_init.sh --stress
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
  echo "Stopping running bot..." >&2
  pkill -f "python -m bot.main" || true
  sleep 2
fi

if [[ "$CHECK_QUOTA" -eq 1 ]]; then
  "$ROOT/tests/live/smoke_check_quota.sh"
fi

python -m tests.live.suite
echo "OK: consolidated live suite passed"

if [[ "$RESTART_BOT" -eq 1 ]]; then
  nohup python -m bot.main > /tmp/the-network-bot.log 2>&1 &
  sleep 3
  pgrep -f "python -m bot.main" >/dev/null 2>&1 || {
    echo "WARN: bot did not stay running; inspect /tmp/the-network-bot.log" >&2
    exit 1
  }
  echo "OK: bot restarted"
fi
