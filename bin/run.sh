#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/data/bot.pid"
LOGFILE="$ROOT/data/bot.log"

cd "$ROOT"
mkdir -p data

if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "Bot already running (pid $pid). Use bin/stop.sh first."
    exit 1
  fi
  rm -f "$PIDFILE"
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Missing .venv. Create it with: python -m venv .venv && pip install -e '.[dev]'"
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing .env. Copy .env.example and configure credentials."
  exit 1
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

nohup python -m bot.main >>"$LOGFILE" 2>&1 &
echo "$!" >"$PIDFILE"
echo "Bot started (pid $(cat "$PIDFILE")). Logs: $LOGFILE"
