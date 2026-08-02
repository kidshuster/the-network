#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PACKAGE_SKIP_BUILD=1
export GITHUB_USER=test-user
./bin/package.sh

PUBLISH="${THE_NETWORK_PUBLISH_DIR:-${ROOT}/publish}"

test -f "${PUBLISH}/docker-compose.yml"
test -f "${PUBLISH}/.env.example"
test -f "${PUBLISH}/VERSION"
test -x "${PUBLISH}/scripts/start.sh"
test -x "${PUBLISH}/scripts/enable.sh"

grep -q 'ghcr.io/test-user/the-network:' "${PUBLISH}/docker-compose.yml"
grep -q 'test-user/the-network-run' "${PUBLISH}/README.md" || grep -q 'test-user' "${PUBLISH}/README.md"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
test "$(cat "${PUBLISH}/VERSION")" = "${VERSION}"

if grep -r '__IMAGE_TAG__\|__GITHUB_USER__' "${PUBLISH}" >/dev/null 2>&1; then
  echo "Unsubstituted placeholders remain in publish/:" >&2
  grep -r '__IMAGE_TAG__\|__GITHUB_USER__' "${PUBLISH}" >&2 || true
  exit 1
fi

echo "Deploy bundle checks passed."
