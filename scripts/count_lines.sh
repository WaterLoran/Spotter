#!/usr/bin/env bash
# 统计 Spotter 项目源码总行数（按语言分类汇总）。
#
# 用法:
#   ./scripts/count_lines.sh        # 从项目根目录执行
#   bash scripts/count_lines.sh     # 同上
#
# 说明:
#   - 统计源码文件（.py .vue .js .ts .sh .css .html .md 等），排除依赖与构建产物目录。
#   - 空行与注释行也计入，反映实际文件规模。
#   - 不依赖第三方工具，仅使用系统自带的 find / wc / awk。

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 统计单个扩展名的总行数
count_ext() {
  local ext="$1"
  find "$ROOT" \
    \( -name ".git" -o -name "node_modules" -o -name "__pycache__" \
       -o -name ".venv" -o -name "venv" -o -name "dist" -o -name "build" \
       -o -name ".mypy_cache" -o -name ".pytest_cache" -o -name "data" \) \
    -prune -o -type f -iname "*.$ext" -print \
    | xargs wc -l 2>/dev/null \
    | awk 'END { print ($1 ? $1 : 0) }'
}

# 格式: "显示名称|扩展名列表(空格分隔)"
LANG_DEFS=(
  "Python|py"
  "Vue|vue"
  "JavaScript|js"
  "TypeScript|ts"
  "Shell|sh"
  "CSS|css"
  "HTML|html"
  "Markdown|md"
  "JSON|json"
  "YAML|yml yaml"
  "TOML|toml"
  "Text|txt"
)

echo ""
echo "════════════════════════════════════════"
echo "  Spotter 项目源码行数统计"
echo "  根目录: $ROOT"
echo "════════════════════════════════════════"
printf "  %-14s %8s\n" "语言" "行数"
echo "  ──────────────────────────"

total=0
results=()

for def in "${LANG_DEFS[@]}"; do
  label="${def%%|*}"
  exts="${def##*|}"
  lines=0
  for ext in $exts; do
    n=$(count_ext "$ext")
    lines=$(( lines + n ))
  done
  if (( lines > 0 )); then
    results+=("$(printf '%08d %s' "$lines" "$label")")
  fi
  total=$(( total + lines ))
done

# 按行数降序输出
printf '%s\n' "${results[@]}" | sort -r | while IFS= read -r entry; do
  n="${entry%% *}"
  label="${entry#* }"
  printf "  %-14s %8d\n" "$label" "$(( 10#$n ))"
done

echo "  ──────────────────────────"
printf "  %-14s %8d\n" "合计" "$total"
echo "════════════════════════════════════════"
echo ""
