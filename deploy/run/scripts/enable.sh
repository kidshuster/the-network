#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_docker
require_env_file

ROOT="$(run_root)"
UNIT_NAME="$(service_name).service"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"

if [[ -n "${SUDO_USER:-}" ]]; then
  RUN_USER="${THE_NETWORK_USER:-$SUDO_USER}"
else
  RUN_USER="${THE_NETWORK_USER:-$(whoami)}"
fi

if [[ "${EUID}" -ne 0 ]]; then
  SUDO=(sudo)
else
  SUDO=()
fi

COMPOSE_FILES="-f ${ROOT}/docker-compose.yml"
if [[ -f "${ROOT}/docker-compose.local.yml" ]]; then
  COMPOSE_FILES="${COMPOSE_FILES} -f ${ROOT}/docker-compose.local.yml"
fi

TMP_UNIT="$(mktemp)"
trap 'rm -f "${TMP_UNIT}"' EXIT

cat >"${TMP_UNIT}" <<EOF
[Unit]
Description=The Network Discord bot (Docker)
Documentation=https://github.com/kidshuster/the-network
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${RUN_USER}
Group=$(id -gn "${RUN_USER}")
WorkingDirectory=${ROOT}
EnvironmentFile=-${ROOT}/.env
ExecStart=/usr/bin/docker compose ${COMPOSE_FILES} up -d --remove-orphans
ExecStop=/usr/bin/docker compose ${COMPOSE_FILES} down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

echo "Installing systemd unit: ${UNIT_PATH}"
"${SUDO[@]}" cp "${TMP_UNIT}" "${UNIT_PATH}"
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable "${UNIT_NAME}"
"${SUDO[@]}" systemctl restart "${UNIT_NAME}"
"${SUDO[@]}" systemctl status "${UNIT_NAME}" --no-pager || true

echo ""
echo "The Network is managed by systemd (${UNIT_NAME})."
echo "  sudo systemctl status ${UNIT_NAME}"
echo "  sudo systemctl restart ${UNIT_NAME}"
echo "  ./scripts/logs.sh"
