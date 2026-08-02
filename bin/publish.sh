#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
GITHUB_USER="${GITHUB_USER:-kidshuster}"
REGISTRY_IMAGE="ghcr.io/${GITHUB_USER}/the-network"
PUBLISH_DIR="${THE_NETWORK_PUBLISH_DIR:-${ROOT}/publish}"
DEPLOY_REPO="${THE_NETWORK_DEPLOY_REPO:-git@github.com:${GITHUB_USER}/the-network-install.git}"
VIA_CI=0
SKIP_DEPLOY_REPO=0
SKIP_IMAGE_PUSH=0

# shellcheck source=lib/docker.sh
source "${ROOT}/bin/lib/docker.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Build the deploy bundle, push the Docker image to GHCR, and push publish/ to the
deploy repo (the-network-install).

Options:
  --via-ci           Skip local image push (use after git tag + GitHub Actions)
  --skip-image       Skip image push (bundle + deploy repo only)
  --skip-deploy-repo Skip pushing publish/ to THE_NETWORK_DEPLOY_REPO
  -h, --help         Show this help

Environment:
  GITHUB_USER              GHCR namespace (default: kidshuster)
  THE_NETWORK_DEPLOY_REPO  Deploy repo git remote
  THE_NETWORK_PUBLISH_DIR  Output directory (default: ./publish)
  PUBLISH_LOCAL            Pass to package.sh to use local image in bundle

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
    --skip-deploy-repo)
      SKIP_DEPLOY_REPO=1
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

if [[ "${VIA_CI}" -eq 0 && "${SKIP_IMAGE_PUSH}" -eq 0 ]]; then
  export PUBLISH_LOCAL=0
  "${ROOT}/bin/package.sh"
else
  export PUBLISH_LOCAL=0
  "${ROOT}/bin/package.sh"
fi

if [[ "${SKIP_IMAGE_PUSH}" -eq 0 ]]; then
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
  echo ""
  echo "Skipping image push (--via-ci). Ensure GitHub Actions published ${REGISTRY_IMAGE}:${VERSION}."
fi

if [[ "${SKIP_DEPLOY_REPO}" -eq 1 ]]; then
  echo ""
  echo "Skipping deploy repo push (--skip-deploy-repo)."
  exit 0
fi

if [[ ! -d "${PUBLISH_DIR}" ]]; then
  echo "Missing publish directory at ${PUBLISH_DIR}" >&2
  exit 1
fi

echo ""
echo "Publishing deploy bundle to ${DEPLOY_REPO}..."

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

if git ls-remote "${DEPLOY_REPO}" HEAD >/dev/null 2>&1; then
  git clone --depth 1 "${DEPLOY_REPO}" "${WORK}/repo"
else
  echo "Deploy repo not found at ${DEPLOY_REPO}; initializing new repo."
  mkdir -p "${WORK}/repo"
  git -C "${WORK}/repo" init -b main
  git -C "${WORK}/repo" remote add origin "${DEPLOY_REPO}"
fi

rsync -a --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'data/relay.db' \
  --exclude 'data/*.db' \
  "${PUBLISH_DIR}/" "${WORK}/repo/"

git -C "${WORK}/repo" add -A
if git -C "${WORK}/repo" diff --cached --quiet; then
  echo "Deploy repo unchanged; nothing to commit."
else
  git -C "${WORK}/repo" commit -m "Release ${VERSION}"
  git -C "${WORK}/repo" push -u origin HEAD
  echo "Deploy repo updated for release ${VERSION}."
fi

echo ""
echo "Done."
echo "  Image:  ${REGISTRY_IMAGE}:${VERSION}"
echo "  Deploy: ${DEPLOY_REPO}"
echo ""
echo "On Raspberry Pi (or any host):"
echo "  git clone ${DEPLOY_REPO}"
echo "  cd the-network-install && cp .env.example .env"
echo "  ./scripts/enable.sh"
