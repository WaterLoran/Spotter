#!/usr/bin/env bash
# Tag spotter:latest and push to a registry (default Docker Hub).
# Usage:
#   docker login   # once per machine
#   DOCKER_NAMESPACE=yourhubusername ./docker/push_image.sh
# Optional: IMAGE_NAME IMAGE_TAG REGISTRY
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

IMAGE_NAME="${IMAGE_NAME:-spotter}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGISTRY:-docker.io}"
DOCKER_NAMESPACE="${DOCKER_NAMESPACE:-}"

if [[ -z "$DOCKER_NAMESPACE" ]]; then
  echo "请设置 Docker Hub（或其它仓库）命名空间，例如：" >&2
  echo "  DOCKER_NAMESPACE=yourusername ./docker/push_image.sh" >&2
  exit 1
fi

SRC="${IMAGE_NAME}:${IMAGE_TAG}"
if [[ "$REGISTRY" == "docker.io" ]]; then
  DEST="${DOCKER_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"
else
  DEST="${REGISTRY}/${DOCKER_NAMESPACE}/${IMAGE_NAME}:${IMAGE_TAG}"
fi

docker tag "$SRC" "$DEST"
docker push "$DEST"
echo "已推送: $DEST"

# 相关命令是 DOCKER_NAMESPACE=waterloran ./docker/push_image.sh 
