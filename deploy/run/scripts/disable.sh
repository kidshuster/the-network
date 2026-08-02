#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

UNIT_NAME="$(service_name).service"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  SUDO=(sudo)
else
  SUDO=()
fi

if [[ -f "${UNIT_PATH}" ]]; then
  "${SUDO[@]}" systemctl stop "${UNIT_NAME}" 2>/dev/null || true
  "${SUDO[@]}" systemctl disable "${UNIT_NAME}" 2>/dev/null || true
  "${SUDO[@]}" rm -f "${UNIT_PATH}"
  "${SUDO[@]}" systemctl daemon-reload
  echo "Disabled and removed ${UNIT_NAME}."
else
  echo "No systemd unit at ${UNIT_PATH}."
fi

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  compose_cmd down 2>/dev/null || true
fi