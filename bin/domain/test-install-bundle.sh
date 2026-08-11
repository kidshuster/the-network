#!/usr/bin/env bash
# CI/helper: validate install/ submodule is a self-contained Docker runtime bundle.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

INSTALL="${THE_NETWORK_INSTALL_DIR:-${ROOT}/install}"
GITHUB_USER="${GITHUB_USER:-kidshuster}"

if [[ ! -d "${INSTALL}" ]]; then
  echo "Missing install submodule at ${INSTALL}" >&2
  echo "Run: git submodule update --init install" >&2
  exit 1
fi

if [[ ! -f "${INSTALL}/docker-compose.yml" ]]; then
  echo "Install submodule checkout looks empty at ${INSTALL}" >&2
  echo "Run: git submodule update --init install" >&2
  exit 1
fi

test -f "${INSTALL}/.env.example"
test -f "${INSTALL}/VERSION"
test -f "${INSTALL}/README.md"
test -x "${INSTALL}/scripts/start.sh"
test -x "${INSTALL}/scripts/enable.sh"
test -x "${INSTALL}/scripts/update.sh"
test -x "${INSTALL}/scripts/stop.sh"
test -x "${INSTALL}/scripts/logs.sh"
test -x "${INSTALL}/scripts/disable.sh"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
test "$(cat "${INSTALL}/VERSION")" = "${VERSION}"

IMAGE="ghcr.io/${GITHUB_USER}/the-network:${VERSION}"
grep -q "image: ${IMAGE}" "${INSTALL}/docker-compose.yml"
grep -q "${GITHUB_USER}/the-network-install" "${INSTALL}/README.md"
grep -qF "${IMAGE}" "${INSTALL}/README.md"

if grep -rE '__IMAGE_TAG__|__GITHUB_USER__' "${INSTALL}" \
  --exclude-dir=.git \
  --exclude='docker-compose.local.yml' >/dev/null 2>&1; then
  echo "Unsubstituted placeholders remain in install/:" >&2
  grep -rE '__IMAGE_TAG__|__GITHUB_USER__' "${INSTALL}" \
    --exclude-dir=.git \
    --exclude='docker-compose.local.yml' >&2 || true
  exit 1
fi

echo "OK: install submodule bundle looks good (${IMAGE})"
