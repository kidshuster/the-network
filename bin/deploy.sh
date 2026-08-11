#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SERVICE_NAME="${THE_NETWORK_SERVICE:-the-network}"
INSTALL_DIR="$(cd "${THE_NETWORK_DIR:-$ROOT}" && pwd)"
PYTHON="${PYTHON:-python3}"

if [[ -n "${SUDO_USER:-}" ]]; then
  RUN_USER="${THE_NETWORK_USER:-$SUDO_USER}"
else
  RUN_USER="${THE_NETWORK_USER:-$(whoami)}"
fi
RUN_GROUP="$(id -gn "${RUN_USER}")"

if [[ "${EUID}" -ne 0 ]]; then
  SUDO=(sudo)
else
  SUDO=()
fi

echo "Deploying The Network"
echo "  install dir: ${INSTALL_DIR}"
echo "  service:     ${SERVICE_NAME}"
echo "  run as:      ${RUN_USER}"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
  echo "Pulling latest changes..."
  git -C "${INSTALL_DIR}" pull --ff-only
fi

chmod +x "${INSTALL_DIR}/bin/start.sh" "${INSTALL_DIR}/bin/stop.sh"

if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  echo ""
  echo "Created ${INSTALL_DIR}/.env from .env.example"
  echo "Edit it with DISCORD_TOKEN and GUILD_ID before the bot can start."
  echo ""
fi

mkdir -p "${INSTALL_DIR}/data"

if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
  echo "Creating virtualenv..."
  "$PYTHON" -m venv "${INSTALL_DIR}/.venv"
fi

# shellcheck source=/dev/null
source "${INSTALL_DIR}/.venv/bin/activate"
pip install -q -e "${INSTALL_DIR}"

UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
TMP_UNIT="$(mktemp)"

cat >"${TMP_UNIT}" <<EOF
[Unit]
Description=The Network Discord relay bot
Documentation=https://github.com/kidshuster/the-network
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=-${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/bin/start.sh
ExecStop=${INSTALL_DIR}/bin/stop.sh
PIDFile=${INSTALL_DIR}/data/bot.pid
Restart=on-failure
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

echo "Installing systemd unit at ${UNIT_PATH}"
"${SUDO[@]}" cp "${TMP_UNIT}" "${UNIT_PATH}"
rm -f "${TMP_UNIT}"

"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable "${SERVICE_NAME}.service"

if grep -q '^DISCORD_TOKEN=.\+' "${INSTALL_DIR}/.env" 2>/dev/null \
  && grep -q '^GUILD_ID=.\+' "${INSTALL_DIR}/.env" 2>/dev/null; then
  echo "Starting ${SERVICE_NAME}.service..."
  "${SUDO[@]}" systemctl restart "${SERVICE_NAME}.service"
  "${SUDO[@]}" systemctl status "${SERVICE_NAME}.service" --no-pager || true
else
  echo ""
  echo "Service installed but not started — set DISCORD_TOKEN and GUILD_ID in ${INSTALL_DIR}/.env"
  echo "Then run: sudo systemctl start ${SERVICE_NAME}.service"
fi

echo ""
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}.service"
echo "  sudo systemctl restart ${SERVICE_NAME}.service"
echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"
echo "  tail -f ${INSTALL_DIR}/data/bot.log"
