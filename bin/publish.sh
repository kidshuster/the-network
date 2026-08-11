#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
GITHUB_USER="${GITHUB_USER:-kidshuster}"
REGISTRY_IMAGE="ghcr.io/${GITHUB_USER}/the-network"
INSTALL_DIR="${THE_NETWORK_INSTALL_DIR:-${ROOT}/install}"
VIA_CI=0
SKIP_INSTALL=0
SKIP_IMAGE_PUSH=0

# shellcheck source=lib/docker.sh
source "${ROOT}/bin/lib/docker.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build/push the Docker image to GHCR and update the install/ submodule
(the-network-install) with the new version tag.

Options:
  --via-ci         Skip local image push (use after git tag + GitHub Actions)
  --skip-image     Skip image push (update install submodule only)
  --skip-install   Skip install submodule commit/push
  -h, --help       Show this help

Environment:
  GITHUB_USER              GHCR namespace (default: kidshuster)
  THE_NETWORK_INSTALL_DIR  Install submodule path (default: ./install)

Examples:
  ./bin/publish.sh
  ./bin/publish.sh --via-ci
  GITHUB_USER=you ./bin/publish.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --via-ci)
      VIA_CI=1
      SKIP_IMAGE_PUSH=1
      shift
      ;;
    --skip-image)
      SKIP_IMAGE_PUSH=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --skip-deploy-repo)
      # Backward-compatible alias
      SKIP_INSTALL=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "${INSTALL_DIR}/.git" && ! -f "${INSTALL_DIR}/.git" ]]; then
  echo "Missing install submodule at ${INSTALL_DIR}." >&2
  echo "Run: git submodule update --init install" >&2
  exit 1
fi

update_install_bundle() {
  local version="$1"
  local user="$2"
  local image="ghcr.io/${user}/the-network:${version}"

  echo "${version}" >"${INSTALL_DIR}/VERSION"

  cat >"${INSTALL_DIR}/docker-compose.yml" <<EOF
# The Network — runtime compose
services:
  the-network:
    image: ${image}
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
EOF

  if [[ -f "${INSTALL_DIR}/README.md" ]]; then
    sed -i \
      -e "s|ghcr.io/[^/]*/the-network:[0-9][^[:space:]\`]*|${image}|g" \
      -e "s|git@github.com:[^/]*/the-network-install.git|git@github.com:${user}/the-network-install.git|g" \
      -e "s|https://github.com/[^/]*/the-network-install|https://github.com/${user}/the-network-install|g" \
      -e "s|https://github.com/[^/]*/the-network)|https://github.com/${user}/the-network)|g" \
      "${INSTALL_DIR}/README.md"
  fi

  rm -f "${INSTALL_DIR}/docker-compose.local.yml"
}

if [[ "${SKIP_IMAGE_PUSH}" -eq 0 ]]; then
  echo "Building local image tag the-network:${VERSION}..."
  require_docker_cli || exit 1
  docker build -t "the-network:${VERSION}" -t the-network:latest .

  echo ""
  echo "Pushing multi-arch image to ${REGISTRY_IMAGE}..."
  require_docker_buildx || exit 1

  BUILDER="${THE_NETWORK_BUILDX_BUILDER:-the-network-builder}"
  if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
    docker buildx create --name "${BUILDER}" --use
  else
    docker buildx use "${BUILDER}"
  fi

  docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "${REGISTRY_IMAGE}:${VERSION}" \
    --tag "${REGISTRY_IMAGE}:latest" \
    --push \
    .
  echo "Pushed ${REGISTRY_IMAGE}:${VERSION} and :latest"
elif [[ "${VIA_CI}" -eq 1 ]]; then
  echo "Skipping image push (--via-ci). Ensure GitHub Actions published ${REGISTRY_IMAGE}:${VERSION}."
else
  echo "Skipping image push (--skip-image)."
fi

if [[ "${SKIP_INSTALL}" -eq 1 ]]; then
  echo ""
  echo "Skipping install submodule update (--skip-install)."
  exit 0
fi

echo ""
echo "Updating install submodule for ${VERSION}..."
update_install_bundle "${VERSION}" "${GITHUB_USER}"

git -C "${INSTALL_DIR}" add -A
if git -C "${INSTALL_DIR}" diff --cached --quiet; then
  echo "Install submodule unchanged; nothing to commit."
else
  git -C "${INSTALL_DIR}" commit -m "Release ${VERSION}"
  git -C "${INSTALL_DIR}" push origin HEAD
  echo "Pushed install submodule (the-network-install) for ${VERSION}."
fi

echo ""
echo "Done."
echo "  Image:   ${REGISTRY_IMAGE}:${VERSION}"
echo "  Install: ${INSTALL_DIR} → the-network-install"
echo ""
echo "Commit the updated submodule pointer in this repo when ready:"
echo "  git add install && git commit -m \"Bump install submodule to ${VERSION}\""
echo ""
echo "On any host:"
echo "  git clone git@github.com:${GITHUB_USER}/the-network-install.git"
echo "  cd the-network-install && cp .env.example .env"
echo "  ./scripts/enable.sh"
