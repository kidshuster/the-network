#!/usr/bin/env bash
# Shared helpers for deploy/run lifecycle scripts.

set -euo pipefail

run_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

compose_cmd() {
  local root
  root="$(run_root)"
  cd "$root"
  if [[ -f docker-compose.local.yml ]]; then
    docker compose -f docker-compose.yml -f docker-compose.local.yml "$@"
  else
    docker compose -f docker-compose.yml "$@"
  fi
}

service_name() {
  echo "${THE_NETWORK_SERVICE:-the-network-docker}"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed. See README.md for setup." >&2
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Cannot connect to Docker. Add your user to the docker group or use sudo." >&2
    exit 1
  fi
}

require_env_file() {
  local root
  root="$(run_root)"
  if [[ ! -f "${root}/.env" ]]; then
    echo "Missing ${root}/.env — copy .env.example and set DISCORD_TOKEN and GUILD_ID." >&2
    exit 1
  fi
  if ! grep -q '^DISCORD_TOKEN=.\+' "${root}/.env" 2>/dev/null; then
    echo "Set DISCORD_TOKEN in ${root}/.env before starting." >&2
    exit 1
  fi
  if ! grep -q '^GUILD_ID=.\+' "${root}/.env" 2>/dev/null; then
    echo "Set GUILD_ID in ${root}/.env before starting." >&2
    exit 1
  fi
}
