#!/usr/bin/env bash
# Build the Spotter all-in-one image (frontend + backend).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-spotter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

exec docker build \
  -f "${ROOT}/docker/Dockerfile" \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  "${ROOT}"
