#!/usr/bin/env bash
# Start Spotter: backend (Flask :5000) and frontend (Vite :3000) in separate terminal windows.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

backend_run() {
  cd "$ROOT/backend"
  export PYTHONPATH=.
  # Default 5001: on macOS, 5000 is often taken by AirPlay Receiver
  export PORT="${PORT:-5001}"
  if [[ -f .venv/bin/activate ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    exec python app.py
  else
    exec python3 app.py
  fi
}

frontend_run() {
  cd "$ROOT/frontend"
  exec npm run dev
}


# Invoked by Terminal/gnome-terminal as worker (do not use directly for normal start)
if [[ "${1:-}" == "_backend" ]]; then
  backend_run
  exit 0
fi
if [[ "${1:-}" == "_frontend" ]]; then
  frontend_run
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    osascript \
      -e 'tell application "Terminal" to activate' \
      -e "tell application \"Terminal\" to do script \"$(printf '%q' "$ROOT")/start.sh _backend\"" \
      -e "tell application \"Terminal\" to do script \"$(printf '%q' "$ROOT")/start.sh _frontend\""
    echo "Started: two Terminal windows — backend http://127.0.0.1:${PORT:-5001} , frontend http://127.0.0.1:3000"
    ;;
  Linux)
    if command -v gnome-terminal >/dev/null 2>&1; then
      gnome-terminal -- bash -c "$(printf '%q' "$ROOT")/start.sh _backend; exec bash" &
      gnome-terminal -- bash -c "$(printf '%q' "$ROOT")/start.sh _frontend; exec bash" &
      echo "Started: two gnome-terminal windows."
    else
      echo "Install gnome-terminal or run manually in two shells:"
      echo "  $(printf '%q' "$ROOT")/start.sh _backend"
      echo "  $(printf '%q' "$ROOT")/start.sh _frontend"
      exit 1
    fi
    ;;
  *)
    echo "Run in two terminals:"
    echo "  BACKEND:  $(printf '%q' "$ROOT")/start.sh _backend"
    echo "  FRONTEND: $(printf '%q' "$ROOT")/start.sh _frontend"
    exit 1
    ;;
esac
