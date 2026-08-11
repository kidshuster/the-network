#!/usr/bin/env bash
# Thin compatibility entry point. Server-init behavior is defined only in YAML recipes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

BACKEND="live"
RECIPE="server-init-audit"
SCENARIO="healthy"
for arg in "$@"; do
  case "$arg" in
    --audit) RECIPE="server-init-audit" ;;
    --stress) RECIPE="server-init-stress" ;;
    --mock) BACKEND="mock" ;;
    --scenario=*) SCENARIO="${arg#*=}" ;;
    -h|--help)
      echo "Usage: tests/live/smoke_server_init.sh [--audit|--stress] [--mock] [--scenario=NAME]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

python -m tests.core.runner recipe "$RECIPE" --backend "$BACKEND" --scenario "$SCENARIO"
