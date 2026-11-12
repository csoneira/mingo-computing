#!/usr/bin/env bash
# Purpose: Run a command only when the configured CPU and memory limits permit it.

# Walk up from this file to find the checkout unless DATAFLOW_ROOT is set.
if [[ -z "${DATAFLOW_ROOT:-}" ]]; then
  _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
    _repo_probe="$(dirname -- "$_repo_probe")"
  done
  if [[ -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh"
  else
    echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  fi
fi
unset _repo_probe
set -euo pipefail

BASE_DIR="${BASE_DIR:-${DATAFLOW_ROOT}}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/config_step_1.yaml}"
LOG_DIR="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/OPERATIONS/RESOURCE_GATE"
LOG_FILE="${LOG_FILE:-$LOG_DIR/resource_gate.log}"

TAG="resource_gate"
MAX_MEM_PCT=""
MAX_SWAP_PCT=""
MAX_SWAP_KB=""
MAX_CPU_PCT=""

usage() {
  cat <<'EOF'
resource_gate.sh
Lightweight resource guard for cron commands.

Usage:
  resource_gate.sh [--tag <name>] [--log-file <path>] [--max-mem-pct N]
                   [--max-swap-pct N] [--max-swap-kb N] [--max-cpu-pct N] -- <command...>

If resource limits are exceeded, the command is skipped (exit 0) and a log entry is written.
Defaults load from config_step_1.yaml -> event_data_resource_limits.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="${2:-$TAG}"
      shift 2
      ;;
    --log-file)
      LOG_FILE="${2:-$LOG_FILE}"
      shift 2
      ;;
    --max-mem-pct)
      MAX_MEM_PCT="${2:-}"
      shift 2
      ;;
    --max-swap-pct)
      MAX_SWAP_PCT="${2:-}"
      shift 2
      ;;
    --max-swap-kb)
      MAX_SWAP_KB="${2:-}"
      shift 2
      ;;
    --max-cpu-pct)
      MAX_CPU_PCT="${2:-}"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

mkdir -p "$LOG_DIR"

if [[ -f "$CONFIG_FILE" ]]; then
  cfg=$(python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || true
import sys
try:
    import yaml
except Exception:
    sys.exit(0)
path = sys.argv[1]
try:
    data = yaml.safe_load(open(path)) or {}
except Exception:
    sys.exit(0)
node = data.get("event_data_resource_limits") or {}
def val(key):
    v = node.get(key)
    return "" if v is None else v
print(f"{val('mem_used_pct_max')},{val('swap_used_pct_max')},{val('swap_used_kb_max')},{val('cpu_used_pct_max')}")
PY
  )
  IFS=',' read -r cfg_mem cfg_swap_pct cfg_swap_kb cfg_cpu <<<"$cfg"
  [[ -z "$MAX_MEM_PCT" && "$cfg_mem" =~ ^[0-9]+$ ]] && MAX_MEM_PCT="$cfg_mem"
  [[ -z "$MAX_SWAP_PCT" && "$cfg_swap_pct" =~ ^[0-9]+$ ]] && MAX_SWAP_PCT="$cfg_swap_pct"
  [[ -z "$MAX_SWAP_KB" && "$cfg_swap_kb" =~ ^[0-9]+$ ]] && MAX_SWAP_KB="$cfg_swap_kb"
  [[ -z "$MAX_CPU_PCT" && "$cfg_cpu" =~ ^[0-9]+$ ]] && MAX_CPU_PCT="$cfg_cpu"
fi

MAX_MEM_PCT="${MAX_MEM_PCT:-95}"
MAX_SWAP_PCT="${MAX_SWAP_PCT:-95}"
MAX_SWAP_KB="${MAX_SWAP_KB:-4194304}"
MAX_CPU_PCT="${MAX_CPU_PCT:-95}"

mem_gate_enabled=0
swap_pct_gate_enabled=0
swap_kb_gate_enabled=0
cpu_gate_enabled=0

[[ "$MAX_MEM_PCT" =~ ^-?[0-9]+$ && "$MAX_MEM_PCT" -gt 0 ]] && mem_gate_enabled=1
[[ "$MAX_SWAP_PCT" =~ ^-?[0-9]+$ && "$MAX_SWAP_PCT" -gt 0 ]] && swap_pct_gate_enabled=1
[[ "$MAX_SWAP_KB" =~ ^-?[0-9]+$ && "$MAX_SWAP_KB" -gt 0 ]] && swap_kb_gate_enabled=1
[[ "$MAX_CPU_PCT" =~ ^-?[0-9]+$ && "$MAX_CPU_PCT" -gt 0 ]] && cpu_gate_enabled=1

log_line() {
  local level="$1"
  local msg="$2"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  printf '[%s] [RESOURCE_GATE] [%s] [%s] %s\n' "$ts" "$TAG" "$level" "$msg" >>"$LOG_FILE"
}

max_cpu_usage_pct() {
  local line1 line2
  line1=$(grep '^cpu ' /proc/stat) || { echo 0; return; }
  sleep 1
  line2=$(grep '^cpu ' /proc/stat) || { echo 0; return; }
  local _ u1 n1 s1 i1 w1 irq1 sirq1 st1 stl1 u2 n2 s2 i2 w2 irq2 sirq2 st2 stl2
  read -r _ u1 n1 s1 i1 w1 irq1 sirq1 st1 stl1 _ <<<"$line1"
  read -r _ u2 n2 s2 i2 w2 irq2 sirq2 st2 stl2 _ <<<"$line2"
  local idle=$(( (i2 - i1) + (w2 - w1) ))
  local total=$(( (u2-u1) + (n2-n1) + (s2-s1) + (i2-i1) + (w2-w1) + (irq2-irq1) + (sirq2-sirq1) + (st2-st1) + (stl2-stl1) ))
  [[ $total -le 0 ]] && { echo 0; return; }
  local busy_pct=$(( (100 * (total - idle)) / total ))
  echo "$busy_pct"
}

read -r mem_total mem_avail swap_total swap_free < <(awk '/MemTotal:/ {t=$2} /MemAvailable:/ {a=$2} /SwapTotal:/ {st=$2} /SwapFree:/ {sf=$2} END {print t, a, st, sf}' /proc/meminfo)
if [[ -z "${mem_total:-}" || -z "${mem_avail:-}" || "$mem_total" -eq 0 ]]; then
  log_line "WARN" "Unable to read /proc/meminfo; allowing command."
  exec "$@"
fi

mem_used_pct=$(( (100 * (mem_total - mem_avail)) / mem_total ))
swap_used_pct=0
swap_used_kb=0
if [[ -n "${swap_total:-}" && "$swap_total" -gt 0 ]]; then
  swap_used_pct=$(( (100 * (swap_total - swap_free)) / swap_total ))
  swap_used_kb=$((swap_total - swap_free))
fi

cpu_used_pct="$(max_cpu_usage_pct || echo 0)"

if (( (mem_gate_enabled == 1 && mem_used_pct >= MAX_MEM_PCT) || \
      (swap_pct_gate_enabled == 1 && swap_used_pct >= MAX_SWAP_PCT) || \
      (swap_kb_gate_enabled == 1 && swap_used_kb >= MAX_SWAP_KB) || \
      (cpu_gate_enabled == 1 && cpu_used_pct >= MAX_CPU_PCT) )); then
  log_line "WARN" "Resources high: Mem ${mem_used_pct}% (limit ${MAX_MEM_PCT}), Swap ${swap_used_pct}%/${swap_used_kb}k (limit ${MAX_SWAP_PCT}%/${MAX_SWAP_KB}k), CPU ${cpu_used_pct}% (limit ${MAX_CPU_PCT}). Skipping command."
  exit 0
fi

exec "$@"
