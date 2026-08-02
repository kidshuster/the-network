#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_docker
require_env_file
compose_cmd up -d --remove-orphans
echo "The Network is running."
compose_cmd ps
