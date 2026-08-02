#!/usr/bin/env bash
# Same pre-init smoke checks that `/server init` runs before hub setup.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/bin/smoke_provision_flow.sh" --probe-only
