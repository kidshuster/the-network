#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${DATA_DIR:-$ROOT/data}"
PID_FILE="${PID_FILE:-$DATA_DIR/bot.pid}"

if [[ ! -f "$PID_FILE" ]]; then
  echo "The Network is not running (no pid file at ${PID_FILE})"
  exit 0
fi

pid="$(cat "$PID_FILE")"
if ! kill -0 "$pid" 2>/dev/null; then
  echo "Removing stale pid file (process ${pid} not found)"
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping The Network (pid ${pid})"
kill "$pid"

for _ in $(seq 1 30); do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "The Network stopped"
    exit 0
  fi
  sleep 1
done

echo "Process did not exit gracefully; sending SIGKILL" >&2
kill -9 "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
echo "The Network stopped"
