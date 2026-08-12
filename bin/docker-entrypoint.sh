#!/usr/bin/env bash
# Production container entrypoint — rejects test mode before starting the bot.
set -euo pipefail

if [[ "${ENABLE_TEST_COMMANDS:-false}" == "true" ]]; then
  echo "Test commands cannot be enabled by the production entrypoint." >&2
  exit 1
fi

exec python -m bot.main
