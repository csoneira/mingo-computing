#!/usr/bin/env bash
# Purpose: Report the slowest pipeline executions from execution metadata.

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
LOG_DIR="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/OPERATIONS/EXECUTION_TOP_OFFENDERS"
LOG_FILE="${LOG_FILE:-$LOG_DIR/execution_top_offenders.log}"
LOCK_FILE="/tmp/dataflow_execution_top_offenders.lock"

TOP_N="${TOP_N:-15}"
INCLUDE_ALL_USERS=0
ONLY_DATAFLOW=1
CSV_OUT=""
QUIET=0

usage() {
  cat <<'EOF'
execution_top_offenders.sh
Show the top execution offenders (CPU/RAM/process duplicates) right now.

Usage:
  execution_top_offenders.sh [options]

Options:
  --top N           Number of rows per section (default: 15)
  --all-users       Include all users (default: current user only)
  --all-commands    Include commands outside DATAFLOW_v3
  --csv PATH        Write aggregated offenders to CSV
  --quiet           Do not append to the log file (print to stdout only)
  -h, --help        Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --top)
      TOP_N="${2:-}"
      shift 2
      ;;
    --all-users)
      INCLUDE_ALL_USERS=1
      shift
      ;;
    --all-commands)
      ONLY_DATAFLOW=0
      shift
      ;;
    --csv)
      CSV_OUT="${2:-}"
      shift 2
      ;;
    --quiet)
      QUIET=1
      shift
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

if [[ ! "$TOP_N" =~ ^[0-9]+$ ]] || [[ "$TOP_N" -lt 1 ]]; then
  echo "--top must be a positive integer" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

report() {
  local ts
  local load_now
  local mem_line
  local swap_line
  local tmp_ps
  local tmp_records
  local tmp_groups
  local -a output_sink_cmd
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  load_now="$(awk '{print $1" "$2" "$3}' /proc/loadavg)"
  mem_line="$(free -m | awk 'NR==2 {printf "mem_used=%sMB mem_free=%sMB mem_available=%sMB", $3, $4, $7}')"
  swap_line="$(free -m | awk 'NR==3 {printf "swap_used=%sMB swap_free=%sMB", $3, $4}')"

  tmp_ps="$(mktemp /tmp/execution_top_offenders_ps.XXXXXX)"
  tmp_records="$(mktemp /tmp/execution_top_offenders_records.XXXXXX)"
  tmp_groups="$(mktemp /tmp/execution_top_offenders_groups.XXXXXX)"
  trap 'rm -f "$tmp_ps" "$tmp_records" "$tmp_groups"' RETURN

  ps -eo pid=,user=,%cpu=,%mem=,rss=,etimes=,args= >"$tmp_ps"

  awk \
    -v base="$BASE_DIR" \
    -v include_all_users="$INCLUDE_ALL_USERS" \
    -v current_user="$USER" \
    -v only_dataflow="$ONLY_DATAFLOW" \
    '
    function trim(s) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
      return s
    }
    function normalize_cmd(cmd,   n, i, token, arr, script) {
      n = split(cmd, arr, /[[:space:]]+/)
      script = ""
      for (i = 1; i <= n; i++) {
        token = arr[i]
        gsub(/^"+|"+$/, "", token)
        if (token ~ /\.(py|sh)$/) {
          script = token
          break
        }
      }
      if (script != "") {
        return script
      }
      if (n >= 2) {
        return arr[1] " " arr[2]
      }
      return arr[1]
    }
    {
      pid = $1
      user = $2
      cpu = $3 + 0
      mem = $4 + 0
      rss = $5 + 0
      etimes = $6 + 0
      $1 = $2 = $3 = $4 = $5 = $6 = ""
      cmd = trim($0)
      if (cmd == "") next
      if (!include_all_users && user != current_user) next
      if (only_dataflow && index(cmd, base) == 0) next
      if (index(cmd, "execution_top_offenders.sh") > 0) next

      key = normalize_cmd(cmd)
      printf "%s\t%s\t%s\t%.3f\t%.3f\t%d\t%d\t%s\n", key, pid, user, cpu, mem, rss, etimes, cmd
    }
  ' "$tmp_ps" >"$tmp_records"

  if [[ ! -s "$tmp_records" ]]; then
    {
      printf '[%s] [TOP_OFFENDERS] load="%s" %s %s\n' "$ts" "$load_now" "$mem_line" "$swap_line"
      echo "No matching running processes found."
    } | tee -a "$LOG_FILE"
    return 0
  fi

  awk -F'\t' '
    {
      key = $1
      count[key] += 1
      cpu_sum[key] += ($4 + 0)
      mem_sum[key] += ($5 + 0)
      rss_sum[key] += ($6 + 0)
      if (($6 + 0) > rss_max[key]) rss_max[key] = ($6 + 0)
      if (($7 + 0) > etimes_max[key]) etimes_max[key] = ($7 + 0)
    }
    END {
      for (k in count) {
        printf "%s\t%d\t%.3f\t%.3f\t%d\t%d\t%d\n", k, count[k], cpu_sum[k], mem_sum[k], rss_sum[k], rss_max[k], etimes_max[k]
      }
    }
  ' "$tmp_records" >"$tmp_groups"

  if [[ -n "$CSV_OUT" ]]; then
    mkdir -p "$(dirname "$CSV_OUT")"
    {
      echo "group_key,count,cpu_sum,mem_sum,rss_sum_kb,rss_max_kb,oldest_runtime_s"
      awk -F'\t' '{
        gsub(/"/, "\"\"", $1)
        printf "\"%s\",%s,%.3f,%.3f,%s,%s,%s\n", $1, $2, $3, $4, $5, $6, $7
      }' "$tmp_groups"
    } >"$CSV_OUT"
  fi

  if [[ "$QUIET" -eq 1 ]]; then
    output_sink_cmd=(cat)
  else
    output_sink_cmd=(tee -a "$LOG_FILE")
  fi

  {
    printf '[%s] [TOP_OFFENDERS] load="%s" %s %s\n' "$ts" "$load_now" "$mem_line" "$swap_line"
    echo "Top grouped offenders (sorted by total CPU):"
    {
      echo -e "rank\tcount\tcpu_sum\tmem_sum\trss_sum_mib\trss_max_mib\toldest_s\tgroup"
      sort -t$'\t' -k3,3nr -k5,5nr "$tmp_groups" \
        | head -n "$TOP_N" \
        | awk -F'\t' '{printf "%d\t%d\t%.2f\t%.2f\t%.1f\t%.1f\t%d\t%s\n", NR, $2, $3, $4, $5/1024.0, $6/1024.0, $7, $1}'
    } | column -t -s $'\t'

    echo
    echo "Top individual offenders by CPU:"
    {
      echo -e "rank\tpid\tcpu\tmem\trss_mib\tetime_s\tcmd"
      sort -t$'\t' -k4,4nr -k6,6nr "$tmp_records" \
        | head -n "$TOP_N" \
        | awk -F'\t' '{printf "%d\t%s\t%.2f\t%.2f\t%.1f\t%d\t%s\n", NR, $2, $4, $5, $6/1024.0, $7, $8}'
    } | column -t -s $'\t'

    echo
    echo "Top individual offenders by RSS:"
    {
      echo -e "rank\tpid\trss_mib\tcpu\tmem\tetime_s\tcmd"
      sort -t$'\t' -k6,6nr -k4,4nr "$tmp_records" \
        | head -n "$TOP_N" \
        | awk -F'\t' '{printf "%d\t%s\t%.1f\t%.2f\t%.2f\t%d\t%s\n", NR, $2, $6/1024.0, $4, $5, $7, $8}'
    } | column -t -s $'\t'

    echo
  } | "${output_sink_cmd[@]}"
}

{
  flock -n 9 || exit 0
  report
} 9>"$LOCK_FILE"
