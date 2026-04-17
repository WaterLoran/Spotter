#!/usr/bin/env bash
# Spotter 日志 API 自检：调 reinitialize → 轮询 /api/logs，可选探测 background-tasks。
# 不依赖浏览器；需后端已启动（默认直连 http://127.0.0.1:5001，或经 Vite 3000）。
#
# 用法:
#   ./scripts/spotter_log_api_smoke.sh
#   SPOTTER_API_BASE=http://127.0.0.1:3000 SPOTTER_SYSTEM_ID=7 ./scripts/spotter_log_api_smoke.sh
#   SKIP_REINIT=1 ./scripts/spotter_log_api_smoke.sh   # 只轮询，不清库
#
# 环境变量:
#   SPOTTER_API_BASE   默认 http://127.0.0.1:5001
#   SPOTTER_SYSTEM_ID  默认 7
#   POLL_SECS          轮询总时长秒，默认 45
#   POLL_INTERVAL      每次间隔秒，默认 3
#   SKIP_REINIT        非空则跳过 POST /api/reinitialize
set -euo pipefail

BASE="${SPOTTER_API_BASE:-http://127.0.0.1:5001}"
SID="${SPOTTER_SYSTEM_ID:-7}"
POLL_SECS="${POLL_SECS:-45}"
INTERVAL="${POLL_INTERVAL:-3}"

HDR=(
  -H "X-FastLog-System-Id: ${SID}"
  -H "Accept: application/json"
  -H "Content-Type: application/json"
)

json_get_total() {
  local body="$1"
  python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(int((d.get('data') or {}).get('total') or 0))" "$body" 2>/dev/null || echo 0
}

echo "== Spotter log API smoke =="
echo "BASE=$BASE SYSTEM_ID=$SID POLL_SECS=$POLL_SECS INTERVAL=$INTERVAL"

if [[ -z "${SKIP_REINIT:-}" ]]; then
  echo ""
  echo ">> POST /api/reinitialize"
  R=$(curl -sS -X POST "$BASE/api/reinitialize" "${HDR[@]}" -d '{}' || true)
  echo "$R" | python3 -m json.tool 2>/dev/null || echo "$R"
  if ! echo "$R" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('success') else 1)" 2>/dev/null; then
    echo "ERROR: reinitialize failed" >&2
    exit 1
  fi
else
  echo ">> SKIP reinitialize (SKIP_REINIT set)"
fi

echo ""
echo ">> Poll GET /api/logs (page_size=1 for total only)"
deadline=$(( $(date +%s) + POLL_SECS ))
last=-1
while (( $(date +%s) < deadline )); do
  body=$(curl -sS "$BASE/api/logs?page=1&page_size=1&search=&notes_only=false" "${HDR[@]}" || echo '{"success":false}')
  total=$(json_get_total "$body")
  now_ts=$(date +%H:%M:%S)
  echo "[$now_ts] total=$total"
  if [[ "$total" != "$last" ]]; then
    last=$total
  fi
  if [[ "$total" -gt 0 ]] 2>/dev/null; then
    echo "OK: logs present (total=$total)"
    break
  fi
  sleep "$INTERVAL"
done

echo ""
echo ">> GET /api/background-tasks"
curl -sS "$BASE/api/background-tasks" "${HDR[@]}" | python3 -m json.tool 2>/dev/null || curl -sS "$BASE/api/background-tasks" "${HDR[@]}"

echo ""
if [[ "${last:-0}" -eq 0 ]]; then
  echo "WARN: total still 0 after ${POLL_SECS}s — 检查 SSH、main_log_collection_enabled、init_time_range_minutes、backend/logs/app.log" >&2
  exit 2
fi
echo "Done."
exit 0
