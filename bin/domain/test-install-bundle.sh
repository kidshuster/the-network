#!/usr/bin/env bash
# CI/helper: validate install/ submodule is a self-contained Docker runtime bundle.
# Delegates to test-install-scripts.sh (syntax, guards, compose, VERSION alignment).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

chmod +x "${ROOT}/bin/domain/test-install-scripts.sh"
REQUIRE_VERSION_MATCH="${REQUIRE_VERSION_MATCH:-1}" \
  "${ROOT}/bin/domain/test-install-scripts.sh"
