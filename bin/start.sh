#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA_DIR="${DATA_DIR:-$ROOT/data}"
PID_FILE="${PID_FILE:-$DATA_DIR/bot.pid}"
LOG_FILE="${LOG_FILE:-$DATA_DIR/bot.log}"
PYTHON="${PYTHON:-python3}"

mkdir -p "$DATA_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "The Network is already running (pid ${existing_pid})" >&2
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

pip install -q -e .

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi

nohup python -m bot.main >>"$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" >"$PID_FILE"

sleep 2
if ! kill -0 "$pid" 2>/dev/null; then
  echo "The Network failed to start — check ${LOG_FILE}" >&2
  rm -f "$PID_FILE"
  tail -20 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "The Network started (pid ${pid}, log ${LOG_FILE})"
