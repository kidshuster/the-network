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
    --stress) RECIPE="stress" ;;
    --skip-quota-check) CHECK_QUOTA=0 ;; # Backward-compatible no-op.
    -h|--help)
      cat <<'EOF'
Usage: tests/live/smoke_testwork.sh [--no-restart] [--check-quota] [--stress]

Primary Testwork entry point. Probe code lives under tests/core/; this directory
contains only live shell launchers.

Runs the YAML `full` recipe in one Discord session. Use `--stress` to run the
destructive rectification recipe instead.

Options:
  --check-quota  Destructive six-call bucket diagnostic (off by default)
  --stress       Run the server-init burn-in recipe instead of the full recipe
  --no-restart   Leave the bot stopped when finished (default for ./test --full)

Targeted entry points:
  python -m tests.core.runner list
  python -m tests.core.runner probe hub.layout
  python -m tests.core.runner recipe audit

Related entry points:
  smoke_cleanup_artifacts.sh   Pre-flight stale artifact cleanup
  smoke_check_quota.sh         Rate-limit bucket diagnostic
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

RECIPE="${RECIPE:-full}"

if pgrep -f "python -m bot.main" >/dev/null 2>&1; then
  echo "Stopping running bot..." >&2
  pkill -f "python -m bot.main" || true
  sleep 2
fi

if [[ "$CHECK_QUOTA" -eq 1 ]]; then
  "$ROOT/tests/live/smoke_check_quota.sh"
fi

python -m tests.core.runner recipe "$RECIPE"
echo "OK: live recipe '$RECIPE' passed"

if [[ "$RESTART_BOT" -eq 1 ]]; then
  nohup python -m bot.main > /tmp/the-network-bot.log 2>&1 &
  sleep 3
  pgrep -f "python -m bot.main" >/dev/null 2>&1 || {
    echo "WARN: bot did not stay running; inspect /tmp/the-network-bot.log" >&2
    exit 1
  }
  echo "OK: bot restarted"
fi
