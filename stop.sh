#!/usr/bin/env bash
# Stop Spotter dev servers: Flask (default 5001 local dev) and Vite (3000).
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-${PORT:-5001}}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

kill_port() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    echo "No process listening on port $port ($name)."
    return 0
  fi
  # shellcheck disable=SC2086
  kill -15 $pids 2>/dev/null || true
  sleep 0.5
  pids="$(lsof -ti:"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
  echo "Stopped $name (port $port)."
}

if ! command -v lsof >/dev/null 2>&1; then
  echo "lsof not found; install it or stop node/python processes manually." >&2
  exit 1
fi

kill_port "$BACKEND_PORT" "backend"
kill_port "$FRONTEND_PORT" "frontend"
echo "Done."
