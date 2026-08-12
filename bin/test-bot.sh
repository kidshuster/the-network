#!/usr/bin/env bash
# Launch the bot with test-only /server test enabled (development checkout).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

if [[ ! -f "${ROOT}/pyproject.toml" || ! -d "${ROOT}/bot" || ! -d "${ROOT}/tests" ]]; then
  echo "ERROR: ${ROOT} does not look like a development the-network checkout with tests/." >&2
  exit 1
fi

if [[ -z "${TEST_GUILD_ID:-}" ]]; then
  echo "ERROR: TEST_GUILD_ID is required for bin/test-bot.sh" >&2
  exit 1
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creating virtualenv at ${ROOT}/.venv"
  "$PYTHON" -m venv "$ROOT/.venv"
fi

# shellcheck source=/dev/null
source "$ROOT/.venv/bin/activate"

# Development install must include tests extras where declared; editable is enough.
pip install -q -e ".[dev]" >/dev/null

export ENABLE_TEST_COMMANDS=true
export TEST_GUILD_ID
export GUILD_ID="${GUILD_ID:-$TEST_GUILD_ID}"
export TEST_COMMAND_LOG_DIR="${TEST_COMMAND_LOG_DIR:-$ROOT/data/smoke-runs}"
mkdir -p "$TEST_COMMAND_LOG_DIR"

echo "Starting The Network with test commands enabled"
echo "  TEST_GUILD_ID=${TEST_GUILD_ID}"
echo "  GUILD_ID=${GUILD_ID}"
echo "  TEST_COMMAND_LOG_DIR=${TEST_COMMAND_LOG_DIR}"
echo "  (token redacted)"

exec python -m bot.main
