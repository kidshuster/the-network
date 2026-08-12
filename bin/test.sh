#!/usr/bin/env bash
# Start the bot with test-only /server test enabled (development checkout).
# Uses the same pid file as bin/start.sh so bin/stop.sh stops it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DATA_DIR="${DATA_DIR:-$ROOT/data}"
PID_FILE="${PID_FILE:-$DATA_DIR/bot.pid}"
LOG_FILE="${LOG_FILE:-$DATA_DIR/bot.log}"
PYTHON="${PYTHON:-python3}"
INSTALL_STAMP="${INSTALL_STAMP:-$ROOT/.venv/.install-stamp}"

if [[ ! -f "${ROOT}/pyproject.toml" || ! -d "${ROOT}/bot" || ! -d "${ROOT}/tests" ]]; then
  echo "ERROR: ${ROOT} does not look like a development the-network checkout with tests/." >&2
  exit 1
fi

_guild_from_env_file() {
  if [[ ! -f "$ROOT/.env" ]]; then
    return 1
  fi
  # Read GUILD_ID without sourcing .env (values with spaces break shell parsing).
  local line
  line="$(grep -E '^GUILD_ID=' "$ROOT/.env" | head -1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  line="${line#GUILD_ID=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s' "$line"
}

if [[ -z "${TEST_GUILD_ID:-}" ]]; then
  if [[ -n "${GUILD_ID:-}" ]]; then
    TEST_GUILD_ID="$GUILD_ID"
  elif guild="$(_guild_from_env_file)"; then
    TEST_GUILD_ID="$guild"
  else
    echo "ERROR: TEST_GUILD_ID is required (or set GUILD_ID / GUILD_ID in .env)." >&2
    exit 1
  fi
fi

export ENABLE_TEST_COMMANDS=true
export TEST_GUILD_ID
export GUILD_ID="$TEST_GUILD_ID"
export TEST_COMMAND_LOG_DIR="${TEST_COMMAND_LOG_DIR:-$ROOT/data/smoke-runs}"
# Faster live pacing for /server test (override individually if needed).
export SMOKE_PHASE_DELAY_SEC="${SMOKE_PHASE_DELAY_SEC:-0.5}"
export SMOKE_PROBE_PHASE_DELAY_SEC="${SMOKE_PROBE_PHASE_DELAY_SEC:-0.5}"
export SMOKE_ROLE_CREATE_DELAY_SEC="${SMOKE_ROLE_CREATE_DELAY_SEC:-0.5}"
export SMOKE_STEP_DELAY_SEC="${SMOKE_STEP_DELAY_SEC:-2}"
export SMOKE_DUPLICATE_PROBE_DELAY_SEC="${SMOKE_DUPLICATE_PROBE_DELAY_SEC:-3}"

mkdir -p "$DATA_DIR" "$TEST_COMMAND_LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "The Network is already running (pid ${existing_pid})" >&2
    echo "Run ./bin/stop.sh first, then ./bin/test.sh" >&2
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
  echo "Installing dependencies (editable + dev)..."
  pip install -q -e ".[dev]"
  touch "$INSTALL_STAMP"
fi

if ! python -c "import bot.app, bot.core, bot.features, bot.main, tests.core.smoke_api" >/dev/null 2>&1; then
  echo "Package import check failed — reinstalling editable package with dev extras..."
  pip install -q -e ".[dev]"
  touch "$INSTALL_STAMP"
  python -c "import bot.app, bot.core, bot.features, bot.main, tests.core.smoke_api"
fi

export PYTHONUNBUFFERED=1
log_lines_before=0
if [[ -f "$LOG_FILE" ]]; then
  log_lines_before=$(wc -l <"$LOG_FILE")
fi

echo "Starting The Network with test commands enabled"
echo "  TEST_GUILD_ID=${TEST_GUILD_ID}"
echo "  GUILD_ID=${GUILD_ID}"
echo "  TEST_COMMAND_LOG_DIR=${TEST_COMMAND_LOG_DIR}"
echo "  log ${LOG_FILE}"

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
    echo "The Network started (pid ${pid}, log ${LOG_FILE}, test commands on)"
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
