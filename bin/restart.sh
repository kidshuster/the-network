#!/usr/bin/env bash
# Restart the source-tree bot (stop.sh then start.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec_dir="$ROOT/bin"

"$exec_dir/stop.sh"
exec "$exec_dir/start.sh"
