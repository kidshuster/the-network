#!/usr/bin/env bash
# Bare-metal source-tree deploy (venv + systemd).
# Prefer Docker via ./bin/deploy.sh + the-network-install on production hosts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

SERVICE_NAME="${THE_NETWORK_SERVICE:-the-network}"
SOURCE_DIR="$(cd "${THE_NETWORK_DIR:-$ROOT}" && pwd)"
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

if [[ ! -f "${SOURCE_DIR}/pyproject.toml" || ! -d "${SOURCE_DIR}/bot" ]]; then
  echo "ERROR: ${SOURCE_DIR} does not look like the the-network source tree." >&2
  echo "For Docker hosts, use the-network-install:" >&2
  echo "  git clone git@github.com:kidshuster/the-network-install.git" >&2
  echo "  cd the-network-install && ./scripts/enable.sh" >&2
  exit 1
fi

echo "Deploying The Network (source / bare metal)"
echo "  source dir:  ${SOURCE_DIR}"
echo "  service:     ${SERVICE_NAME}"
echo "  run as:      ${RUN_USER}"

if [[ -d "${SOURCE_DIR}/.git" || -f "${SOURCE_DIR}/.git" ]]; then
  echo "Pulling latest changes..."
  git -C "${SOURCE_DIR}" pull --ff-only
  if [[ -f "${SOURCE_DIR}/.gitmodules" ]]; then
    git -C "${SOURCE_DIR}" submodule update --init --recursive
  fi
fi

chmod +x "${SOURCE_DIR}/bin/start.sh" "${SOURCE_DIR}/bin/stop.sh"

if [[ ! -f "${SOURCE_DIR}/.env" ]]; then
  cp "${SOURCE_DIR}/.env.example" "${SOURCE_DIR}/.env"
  echo ""
  echo "Created ${SOURCE_DIR}/.env from .env.example"
  echo "Edit it with DISCORD_TOKEN and GUILD_ID before the bot can start."
  echo ""
fi

mkdir -p "${SOURCE_DIR}/data"

if [[ ! -d "${SOURCE_DIR}/.venv" ]]; then
  echo "Creating virtualenv..."
  "$PYTHON" -m venv "${SOURCE_DIR}/.venv"
fi

# shellcheck source=/dev/null
source "${SOURCE_DIR}/.venv/bin/activate"
pip install -q -e "${SOURCE_DIR}"

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
WorkingDirectory=${SOURCE_DIR}
EnvironmentFile=-${SOURCE_DIR}/.env
ExecStart=${SOURCE_DIR}/bin/start.sh
ExecStop=${SOURCE_DIR}/bin/stop.sh
PIDFile=${SOURCE_DIR}/data/bot.pid
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

if grep -q '^DISCORD_TOKEN=.\+' "${SOURCE_DIR}/.env" 2>/dev/null \
  && grep -q '^GUILD_ID=.\+' "${SOURCE_DIR}/.env" 2>/dev/null; then
  echo "Starting ${SERVICE_NAME}.service..."
  "${SUDO[@]}" systemctl restart "${SERVICE_NAME}.service"
  "${SUDO[@]}" systemctl status "${SERVICE_NAME}.service" --no-pager || true
else
  echo ""
  echo "Service installed but not started — set DISCORD_TOKEN and GUILD_ID in ${SOURCE_DIR}/.env"
  echo "Then run: sudo systemctl start ${SERVICE_NAME}.service"
fi

echo ""
echo "Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}.service"
echo "  sudo systemctl restart ${SERVICE_NAME}.service"
echo "  sudo journalctl -u ${SERVICE_NAME}.service -f"
echo "  tail -f ${SOURCE_DIR}/data/bot.log"
