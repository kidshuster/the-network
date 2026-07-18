#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/data/bot.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pid file found — bot is not running."
  exit 0
fi

pid="$(cat "$PIDFILE")"

if ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo "Removed stale pid file — bot was not running."
  exit 0
fi

kill "$pid"
echo "Stopping bot (pid $pid)..."

for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Bot stopped."
    exit 0
  fi
  sleep 1
done

kill -9 "$pid" 2>/dev/null || true
rm -f "$PIDFILE"
echo "Bot force-stopped."
