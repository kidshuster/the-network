#!/usr/bin/env bash
# Release deploy: gate on ./test --dev + install script validation, push main,
# publish the Docker image to GHCR, and update install/ (the-network-install).
# For bare-metal source/systemd deploy, use bin/domain/deploy-source.sh instead.
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
SKIP_TESTS=0
SKIP_GIT_PUSH=0

# shellcheck source=domain/lib/docker.sh
source "${ROOT}/bin/domain/lib/docker.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Release path:
  1. Secret preflight + ./test --dev (no live Discord smoke)
  2. Validate the-network-install scripts
  3. git push origin main
  4. Build/push multi-arch image to GHCR
  5. Update/push install/ submodule and parent gitlink

Options:
  --via-ci           Skip local image push (use after git tag + GitHub Actions)
  --skip-image       Skip image push (update install submodule only)
  --skip-install     Skip install submodule commit/push
  --skip-tests       Skip ./test --dev (recovery only)
  --skip-git-push    Skip pushing this repo (recovery only)
  -h, --help         Show this help

Environment:
  GITHUB_USER              GHCR namespace (default: kidshuster)
  THE_NETWORK_INSTALL_DIR  Install submodule path (default: ./install)

Examples:
  ./bin/deploy.sh
  ./bin/deploy.sh --via-ci
  GITHUB_USER=you ./bin/deploy.sh --skip-image

Bare-metal source/systemd (uncommon):
  ./bin/domain/deploy-source.sh
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
      SKIP_INSTALL=1
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=1
      shift
      ;;
    --skip-git-push)
      SKIP_GIT_PUSH=1
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

ensure_install_submodule() {
  if [[ ! -e "${INSTALL_DIR}" ]]; then
    echo "Missing install submodule at ${INSTALL_DIR}." >&2
    echo "Run: git submodule update --init install" >&2
    exit 1
  fi
  if [[ ! -d "${INSTALL_DIR}/.git" && ! -f "${INSTALL_DIR}/.git" ]]; then
    echo "Missing install submodule metadata at ${INSTALL_DIR}." >&2
    echo "Run: git submodule update --init install" >&2
    exit 1
  fi
  if [[ ! -f "${INSTALL_DIR}/docker-compose.yml" ]]; then
    echo "Install submodule checkout looks empty." >&2
    echo "Run: git submodule update --init install" >&2
    exit 1
  fi
}

ensure_install_start_rejects_test_mode() {
  local start="${INSTALL_DIR}/scripts/start.sh"
  if [[ ! -f "${start}" ]]; then
    echo "Missing ${start}" >&2
    exit 1
  fi
  if grep -q 'ENABLE_TEST_COMMANDS' "${start}"; then
    return 0
  fi
  local tmp
  tmp="$(mktemp)"
  awk '
    BEGIN { inserted=0 }
    /^require_docker$/ && inserted==0 {
      print "if [[ \"${ENABLE_TEST_COMMANDS:-false}\" == \"true\" ]]; then"
      print "  echo \"Test commands cannot be enabled by the production launcher.\" >&2"
      print "  exit 1"
      print "fi"
      print ""
      inserted=1
    }
    { print }
  ' "${start}" >"${tmp}"
  mv "${tmp}" "${start}"
  chmod +x "${start}"
}

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
  chmod +x "${INSTALL_DIR}"/scripts/*.sh 2>/dev/null || true
  ensure_install_start_rejects_test_mode
}

require_main_branch() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "${branch}" != "main" ]]; then
    echo "Deploy must run from main (current: ${branch})." >&2
    exit 1
  fi
}

require_clean_worktree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree must be clean before deploy." >&2
    git status --short >&2
    exit 1
  fi
}

ensure_install_submodule
require_main_branch
require_clean_worktree

echo "==> Secret / test-mode preflight"
chmod +x "${ROOT}/bin/domain/check-no-guild-secrets.sh"
"${ROOT}/bin/domain/check-no-guild-secrets.sh"

if [[ "${SKIP_TESTS}" -eq 0 ]]; then
  echo ""
  echo "==> ./test --dev"
  "${ROOT}/test" --dev
else
  echo ""
  echo "Skipping ./test --dev (--skip-tests)."
fi

echo ""
echo "==> Validate install scripts (pre-bundle)"
chmod +x "${ROOT}/bin/domain/test-install-scripts.sh"
# Version may not match until update_install_bundle runs.
REQUIRE_VERSION_MATCH=0 "${ROOT}/bin/domain/test-install-scripts.sh"

if [[ "${SKIP_GIT_PUSH}" -eq 0 ]]; then
  echo ""
  echo "==> git push origin main"
  git push origin main
else
  echo ""
  echo "Skipping git push (--skip-git-push)."
fi

if [[ "${SKIP_IMAGE_PUSH}" -eq 0 ]]; then
  echo ""
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

if git -C "${INSTALL_DIR}" show-ref --verify --quiet refs/remotes/origin/main; then
  git -C "${INSTALL_DIR}" checkout -B main origin/main
elif git -C "${INSTALL_DIR}" show-ref --verify --quiet refs/heads/main; then
  git -C "${INSTALL_DIR}" checkout main
  git -C "${INSTALL_DIR}" pull --ff-only origin main || true
fi

update_install_bundle "${VERSION}" "${GITHUB_USER}"

echo ""
echo "==> Validate install bundle (VERSION + image)"
REQUIRE_VERSION_MATCH=1 "${ROOT}/bin/domain/test-install-scripts.sh"
# Keep legacy helper green too.
"${ROOT}/bin/domain/test-install-bundle.sh"

git -C "${INSTALL_DIR}" add -A
if git -C "${INSTALL_DIR}" diff --cached --quiet; then
  echo "Install submodule unchanged; nothing to commit."
else
  git -C "${INSTALL_DIR}" commit -m "Release ${VERSION}"
  git -C "${INSTALL_DIR}" push origin HEAD:main
  echo "Pushed install submodule (the-network-install) for ${VERSION}."
fi

git add "${INSTALL_DIR}"
if ! git diff --cached --quiet; then
  git commit -m "Bump install submodule to ${VERSION}"
  if [[ "${SKIP_GIT_PUSH}" -eq 0 ]]; then
    git push origin main
  fi
fi

echo ""
echo "Done."
echo "  Image:   ${REGISTRY_IMAGE}:${VERSION}"
echo "  Install: ${INSTALL_DIR} → the-network-install"
echo ""
echo "On any host:"
echo "  git clone git@github.com:${GITHUB_USER}/the-network-install.git"
echo "  cd the-network-install && cp .env.example .env"
echo "  ./scripts/enable.sh"
