#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
GITHUB_USER="${GITHUB_USER:-kidshuster}"
IMAGE="${THE_NETWORK_IMAGE:-the-network}:${VERSION}"
PUBLISH_DIR="${THE_NETWORK_PUBLISH_DIR:-${ROOT}/publish}"
RUN_TEMPLATE="${ROOT}/deploy/run"

# shellcheck source=lib/docker.sh
source "${ROOT}/bin/lib/docker.sh"

if [[ ! -d "${RUN_TEMPLATE}" ]]; then
  echo "Missing deploy template at ${RUN_TEMPLATE}" >&2
  exit 1
fi

echo "Building ${IMAGE}..."
if [[ "${PACKAGE_SKIP_BUILD:-0}" == "1" ]]; then
  echo "PACKAGE_SKIP_BUILD=1 — skipping docker build."
else
  require_docker_cli || exit 1
  docker build -t "${IMAGE}" -t the-network:latest .
fi

echo ""
echo "Building deploy bundle in ${PUBLISH_DIR}..."
rm -rf "${PUBLISH_DIR}"
mkdir -p "${PUBLISH_DIR}"
rsync -a \
  --exclude '.git' \
  "${RUN_TEMPLATE}/" "${PUBLISH_DIR}/"

chmod +x "${PUBLISH_DIR}"/scripts/*.sh

substitute() {
  local file="$1"
  sed -i \
    -e "s/__IMAGE_TAG__/${VERSION}/g" \
    -e "s/__GITHUB_USER__/${GITHUB_USER}/g" \
    "${file}"
}

while IFS= read -r -d '' file; do
  substitute "${file}"
done < <(find "${PUBLISH_DIR}" -type f -print0)

echo "${VERSION}" >"${PUBLISH_DIR}/VERSION"

if [[ "${PUBLISH_LOCAL:-0}" == "1" ]]; then
  echo "PUBLISH_LOCAL=1 — keeping docker-compose.local.yml for local image."
else
  rm -f "${PUBLISH_DIR}/docker-compose.local.yml"
fi

echo ""
echo "Package ready:"
echo "  Docker image:     ${IMAGE}"
echo "  Deploy bundle:    ${PUBLISH_DIR}"
echo "  GHCR image:       ghcr.io/${GITHUB_USER}/the-network:${VERSION}"
echo ""
echo "Test the bundle locally:"
echo "  cd ${PUBLISH_DIR}"
echo "  cp .env.example .env   # set DISCORD_TOKEN and GUILD_ID"
if [[ "${PUBLISH_LOCAL:-0}" == "1" ]]; then
  echo "  ./scripts/start.sh"
else
  echo "  # pull from registry first, or re-run with PUBLISH_LOCAL=1 after package"
  echo "  ./scripts/start.sh"
fi
echo ""
echo "Publish to registry + deploy repo:"
echo "  ./bin/publish.sh"
