#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="${1:-staging}"

case "$MODE" in
  staging)
    if [[ ! -f .env.staging ]]; then
      echo "Missing .env.staging — create it with GUILD_ID and DATABASE_PATH first." >&2
      exit 1
    fi
    cp .env.staging .env
    echo "OK: using staging env (GUILD_ID=$(grep '^GUILD_ID=' .env | cut -d= -f2))"
    ;;
  production|prod)
    if [[ ! -f .env.production ]]; then
      echo "Missing .env.production backup." >&2
      exit 1
    fi
    cp .env.production .env
    echo "OK: using production env (GUILD_ID=$(grep '^GUILD_ID=' .env | cut -d= -f2))"
    ;;
  *)
    echo "Usage: $0 [staging|production]" >&2
    exit 2
    ;;
esac
