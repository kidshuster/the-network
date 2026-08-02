#!/usr/bin/env bash
# Shared Docker CLI checks for bin/package.sh and bin/publish.sh

require_docker_cli() {
  if ! command -v docker >/dev/null 2>&1; then
    cat >&2 <<'EOF'
docker was not found in PATH.

Install Docker:
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"   # then log out and back in

On WSL with Docker Desktop: enable WSL integration for this distro
  Docker Desktop → Settings → Resources → WSL Integration
EOF
    return 1
  fi

  local info_err
  info_err="$(docker info 2>&1)" || {
    if grep -qi 'permission denied.*docker.sock' <<<"${info_err}"; then
      cat >&2 <<'EOF'
Cannot access the Docker daemon (permission denied on /var/run/docker.sock).

Fix:
  sudo usermod -aG docker "$USER"
  # log out and back in (or reboot), then verify: docker info

Until then you can use: sudo ./bin/publish.sh
EOF
    elif grep -qi 'WSL' <<<"${info_err}"; then
      cat >&2 <<'EOF'
Docker is on PATH but not available inside this WSL distro.

Fix (Docker Desktop on Windows):
  1. Open Docker Desktop
  2. Settings → Resources → WSL Integration
  3. Enable integration for this Linux distro (e.g. Ubuntu)
  4. Apply & Restart, then open a new terminal

Or install the Docker engine inside WSL instead of using Desktop:
  curl -fsSL https://get.docker.com | sh
EOF
    else
      echo "Cannot run docker: ${info_err}" >&2
      echo "Is the Docker daemon running?" >&2
    fi
    return 1
  }
  return 0
}

require_docker_buildx() {
  require_docker_cli || return 1
  if ! docker buildx version >/dev/null 2>&1; then
    echo "docker buildx is required for multi-arch publish." >&2
    echo "Update Docker Desktop or install docker-buildx-plugin." >&2
    return 1
  fi
  return 0
}
