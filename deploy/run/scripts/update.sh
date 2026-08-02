#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_docker
require_env_file

root="$(run_root)"
cd "$root"

if [[ -f VERSION ]]; then
  echo "Updating to version $(cat VERSION)..."
fi

compose_cmd pull
compose_cmd up -d --remove-orphans
echo "Update complete."
compose_cmd ps
