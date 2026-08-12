#!/usr/bin/env bash
# Start the bot from a source checkout (venv). Docker hosts should use install/scripts/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${ENABLE_TEST_COMMANDS:-false}" == "true" ]]; then
  echo "Test commands cannot be enabled by the production launcher." >&2
  exit 1
fi

DATA_DIR="${DATA_DIR:-$ROOT/data}"
PID_FILE="${PID_FILE:-$DATA_DIR/bot.pid}"
LOG_FILE="${LOG_FILE:-$DATA_DIR/bot.log}"
PYTHON="${PYTHON:-python3}"
INSTALL_STAMP="${INSTALL_STAMP:-$ROOT/.venv/.install-stamp}"

if [[ ! -f "${ROOT}/pyproject.toml" || ! -d "${ROOT}/bot" ]]; then
  echo "ERROR: ${ROOT} does not look like the the-network source tree." >&2
  echo "For Docker runtime, use the-network-install (./scripts/start.sh)." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "The Network is already running (pid ${existing_pid})" >&2
    echo "Run ./bin/stop.sh first, then ./bin/start.sh" >&2
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating virtualenv at ${ROOT}/.venv"
  "$PYTHON" -m venv "$ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

need_install=0
if [[ ! -f "$INSTALL_STAMP" ]]; then
  need_install=1
elif [[ "$ROOT/pyproject.toml" -nt "$INSTALL_STAMP" ]]; then
  need_install=1
fi

if [[ "$need_install" -eq 1 ]]; then
  echo "Installing dependencies (editable)..."
  pip install -q -e .
  touch "$INSTALL_STAMP"
fi

# Fail fast if the editable install is stale relative to the app/core/features layout.
if ! python -c "import bot.app, bot.core, bot.features, bot.main" >/dev/null 2>&1; then
  echo "Package import check failed — reinstalling editable package..."
  pip install -q -e .
  touch "$INSTALL_STAMP"
  python -c "import bot.app, bot.core, bot.features, bot.main"
fi

# Do not `source` .env here — values with spaces (role names) break shell parsing.
# bot.main loads Settings from .env via pydantic-settings.

export PYTHONUNBUFFERED=1
log_lines_before=0
if [[ -f "$LOG_FILE" ]]; then
  log_lines_before=$(wc -l <"$LOG_FILE")
fi
nohup python -m bot.main >>"$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" >"$PID_FILE"

for _ in $(seq 1 15); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "The Network failed to start — check ${LOG_FILE}" >&2
    rm -f "$PID_FILE"
    tail -30 "$LOG_FILE" >&2 || true
    exit 1
  fi
  if tail -n +"$((log_lines_before + 1))" "$LOG_FILE" 2>/dev/null | grep -q '"message": "Bot ready"'; then
    echo "The Network started (pid ${pid}, log ${LOG_FILE})"
    exit 0
  fi
  sleep 1
done

if kill -0 "$pid" 2>/dev/null; then
  echo "The Network is starting (pid ${pid}, log ${LOG_FILE})" >&2
  echo "Process is alive but has not logged 'Bot ready' yet — check ${LOG_FILE}" >&2
  tail -10 "$LOG_FILE" >&2 || true
  exit 0
fi

echo "The Network failed to start — check ${LOG_FILE}" >&2
rm -f "$PID_FILE"
tail -30 "$LOG_FILE" >&2 || true
exit 1
