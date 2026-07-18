#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
IMAGE="${THE_NETWORK_IMAGE:-the-network}:${VERSION}"

echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" -t the-network:latest .

echo ""
echo "Package ready:"
echo "  Docker image: ${IMAGE}"
echo ""
echo "Run locally:"
echo "  docker compose up -d"
echo ""
echo "Or:"
echo "  docker run --env-file .env -v \"${ROOT}/data:/app/data\" --restart unless-stopped -d ${IMAGE}"
echo ""
echo "Next: follow deploy/TOPGG.md to list on top.gg"
