#!/usr/bin/env bash
# Spotter API 自检：默认只做进程内 CRUD（无需起服务）。
# 加 --http-backend 会探测 http://127.0.0.1:5001（需后端已启动）。
# 加 --http-vite 会探测 http://127.0.0.1:3000/api（需 npm run dev）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi
export SCHEDULER_ENABLED="${SCHEDULER_ENABLED:-false}"
export PYTHONPATH=.
exec python "$ROOT/scripts/verify_spotter_api.py" "$@"
