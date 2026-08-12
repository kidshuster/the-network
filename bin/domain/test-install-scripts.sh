#!/usr/bin/env bash
# Validate the-network-install launcher scripts (syntax, guards, compose contract).
# Does not start the bot or contact Discord.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

INSTALL="${THE_NETWORK_INSTALL_DIR:-${ROOT}/install}"
GITHUB_USER="${GITHUB_USER:-kidshuster}"
SKIP_COMPOSE_CONFIG="${SKIP_COMPOSE_CONFIG:-0}"
REQUIRE_VERSION_MATCH="${REQUIRE_VERSION_MATCH:-1}"

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

SCRIPTS=(
  start.sh
  stop.sh
  update.sh
  enable.sh
  disable.sh
  logs.sh
  lib.sh
)

for name in "${SCRIPTS[@]}"; do
  path="${INSTALL}/scripts/${name}"
  test -f "${path}"
  if [[ "${name}" != "lib.sh" ]]; then
    test -x "${path}"
  fi
  bash -n "${path}"
done

# Production start must reject test mode before requiring .env.
if ! ENABLE_TEST_COMMANDS=true "${INSTALL}/scripts/start.sh" >/tmp/the-network-install-start-test.out 2>&1; then
  :
else
  echo "install/scripts/start.sh must reject ENABLE_TEST_COMMANDS=true" >&2
  cat /tmp/the-network-install-start-test.out >&2 || true
  exit 1
fi
if ! grep -qi 'test commands cannot be enabled' /tmp/the-network-install-start-test.out; then
  echo "install/scripts/start.sh rejection message missing" >&2
  cat /tmp/the-network-install-start-test.out >&2 || true
  exit 1
fi
rm -f /tmp/the-network-install-start-test.out

# Keep launchers Docker-compose based (no source-tree bot entrypoints).
bad_refs="$(
  grep -RInE 'bin/start\.sh|python -m bot\.main|ENABLE_TEST_COMMANDS=true' \
    "${INSTALL}/scripts" "${INSTALL}/docker-compose.yml" 2>/dev/null \
    | grep -vE 'scripts/start\.sh:.*ENABLE_TEST_COMMANDS' || true
)"
if [[ -n "${bad_refs}" ]]; then
  echo "Install scripts must not invoke source-tree bot entrypoints or enable test mode:" >&2
  echo "${bad_refs}" >&2
  exit 1
fi

test -f "${INSTALL}/.env.example"
test -f "${INSTALL}/VERSION"
test -f "${INSTALL}/README.md"

if ! grep -qE '^\s*-\s*\./data:/app/data\s*$' "${INSTALL}/docker-compose.yml"; then
  echo "install/docker-compose.yml must mount ./data:/app/data" >&2
  exit 1
fi
if ! grep -qE '^\s*env_file:' "${INSTALL}/docker-compose.yml"; then
  echo "install/docker-compose.yml must declare env_file" >&2
  exit 1
fi

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
IMAGE="ghcr.io/${GITHUB_USER}/the-network:${VERSION}"

if [[ "${REQUIRE_VERSION_MATCH}" -eq 1 ]]; then
  test "$(cat "${INSTALL}/VERSION")" = "${VERSION}"
  grep -q "image: ${IMAGE}" "${INSTALL}/docker-compose.yml"
  grep -q "${GITHUB_USER}/the-network-install" "${INSTALL}/README.md"
  grep -qF "${IMAGE}" "${INSTALL}/README.md"
fi

if grep -rE '__IMAGE_TAG__|__GITHUB_USER__' "${INSTALL}" \
  --exclude-dir=.git \
  --exclude='docker-compose.local.yml' >/dev/null 2>&1; then
  echo "Unsubstituted placeholders remain in install/:" >&2
  grep -rE '__IMAGE_TAG__|__GITHUB_USER__' "${INSTALL}" \
    --exclude-dir=.git \
    --exclude='docker-compose.local.yml' >&2 || true
  exit 1
fi

if [[ "${SKIP_COMPOSE_CONFIG}" -eq 0 ]] && command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    created_env=0
    if [[ ! -f "${INSTALL}/.env" ]]; then
      cat >"${INSTALL}/.env" <<EOF
DISCORD_TOKEN=dummy-token-for-compose-config
GUILD_ID=123456789012345678
DATABASE_PATH=/app/data/relay.db
LOG_LEVEL=INFO
EOF
      created_env=1
    fi
    (
      cd "${INSTALL}"
      docker compose -f docker-compose.yml config >/dev/null
    )
    if [[ "${created_env}" -eq 1 ]]; then
      rm -f "${INSTALL}/.env"
    fi
    echo "OK: docker compose config validated"
  else
    echo "WARN: docker daemon unavailable; skipped compose config check"
  fi
fi

echo "OK: install scripts look good (${IMAGE})"
