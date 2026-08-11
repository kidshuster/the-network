#!/usr/bin/env bash
# Switch active .env between staging (Testwork) and production backups.
# Needed so live smoke can target Testwork without overwriting a production .env by hand.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-staging}"

print_env_summary() {
  local guild path
  guild="$(grep '^GUILD_ID=' .env | cut -d= -f2- || true)"
  path="$(grep '^DATABASE_PATH=' .env | cut -d= -f2- || true)"
  echo "OK: using ${1} env"
  echo "  GUILD_ID=${guild}"
  echo "  DATABASE_PATH=${path:-./data/relay.db}"
}

case "$MODE" in
  staging)
    if [[ ! -f .env.staging ]]; then
      echo "Missing .env.staging — create it with GUILD_ID and DATABASE_PATH first." >&2
      echo "Example:" >&2
      echo "  cp .env.example .env.staging" >&2
      echo "  # set GUILD_ID to Testwork and DATABASE_PATH=./data/staging-relay.db" >&2
      exit 1
    fi
    cp .env.staging .env
    print_env_summary staging
    echo "Live smoke: ./test --full"
    echo "Targeted:   python -m tests.core.runner recipe full"
    ;;
  production|prod)
    if [[ ! -f .env.production ]]; then
      echo "Missing .env.production backup." >&2
      exit 1
    fi
    cp .env.production .env
    print_env_summary production
    ;;
  *)
    echo "Usage: $0 [staging|production]" >&2
    exit 2
    ;;
esac
