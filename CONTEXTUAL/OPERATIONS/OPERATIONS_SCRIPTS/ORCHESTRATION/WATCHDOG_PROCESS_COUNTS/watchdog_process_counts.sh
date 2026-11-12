#!/usr/bin/env bash
# Purpose: Monitor pipeline process counts and report unexpected growth.

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
LOG_DIR="${BASE_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS/ANCILLARY/OPERATIONS/WATCHDOG_PROCESS_COUNTS"
LOG_FILE="${LOG_FILE:-$LOG_DIR/watchdog_process_counts.log}"
LOCK_FILE="/tmp/dataflow_watchdog_process_counts.lock"
CRON_FILE="${WATCHDOG_CRON_FILE:-$BASE_DIR/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/analysis_pc.crontab}"
CRON_REPORT_ENABLED="${WATCHDOG_CRON_REPORT_ENABLED:-1}"
CRON_REPORT_DIFF_ONLY="${WATCHDOG_CRON_REPORT_DIFF_ONLY:-1}"
CRON_REPORT_STATE_FILE="${WATCHDOG_CRON_REPORT_STATE_FILE:-$LOG_DIR/cron_report_state.txt}"
CRON_REPORT_EXCLUDE_REGEX="${WATCHDOG_CRON_EXCLUDE_REGEX:-/bin/mkdir|/usr/bin/crontab}"
CRON_PROMOTE_ENABLED="${WATCHDOG_CRON_PROMOTE_ENABLED:-1}"
CRON_PROMOTE_FILE="${WATCHDOG_CRON_PROMOTE_FILE:-$LOG_DIR/high_risk_promoted.list}"
CRON_PROMOTE_MIN_COUNT="${WATCHDOG_CRON_PROMOTE_MIN_COUNT:-3}"
CRON_PROMOTE_DELTA="${WATCHDOG_CRON_PROMOTE_DELTA:-3}"
CRON_PROMOTE_FACTOR="${WATCHDOG_CRON_PROMOTE_FACTOR:-2}"

mkdir -p "$LOG_DIR"

WATCHDOG_DRY_RUN="${WATCHDOG_DRY_RUN:-0}"
WATCHDOG_GRACE_SECONDS="${WATCHDOG_GRACE_SECONDS:-8}"

MAX_GUIDE_RAW_PER_STATION="${WATCHDOG_GUIDE_RAW_PER_STATION:-1}"
MAX_GUIDE_STEP2_TOTAL="${WATCHDOG_GUIDE_STEP2_TOTAL:-1}"
MAX_GUIDE_STEP3_TOTAL="${WATCHDOG_GUIDE_STEP3_TOTAL:-1}"
MAX_BRING_REPROC_PER_STATION="${WATCHDOG_BRING_REPROC_PER_STATION:-1}"
MAX_UNPACK_REPROC_PER_STATION="${WATCHDOG_UNPACK_REPROC_PER_STATION:-3}"
MAX_BRING_NEWFILES_PER_STATION="${WATCHDOG_BRING_NEWFILES_PER_STATION:-1}"
MAX_SIM_RUN_STEP_TOTAL="${WATCHDOG_SIM_RUN_STEP_TOTAL:-1}"
MAX_SIM_STEP0_SETUP_TOTAL="${WATCHDOG_SIM_STEP0_SETUP_TOTAL:-1}"
MAX_SIM_STEPFINAL_TOTAL="${WATCHDOG_SIM_STEPFINAL_TOTAL:-1}"
MAX_SIM_SANITIZE_TOTAL="${WATCHDOG_SIM_SANITIZE_TOTAL:-1}"
MAX_SIM_RESET_TOTAL="${WATCHDOG_SIM_RESET_TOTAL:-1}"
MAX_SIM_INGEST_TOTAL="${WATCHDOG_SIM_INGEST_TOTAL:-1}"
MAX_COPERNICUS_PER_STATION="${WATCHDOG_COPERNICUS_PER_STATION:-1}"

log_line() {
  local msg="$1"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  printf '[%s] [WATCHDOG] %s\n' "$ts" "$msg" >>"$LOG_FILE"
}

sanitize_nonneg_int() {
  local value="${1:-0}"
  value="${value%%$'\n'*}"
  value="${value//$'\r'/}"
  value="${value//[[:space:]]/}"
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s' "$value"
  else
    printf '0'
  fi
}

regex_escape() {
  printf '%s' "$1" | sed -e 's/[][\\.^$*+?(){}|]/\\&/g'
}

load_state() {
  local file="$1"
  local line key val
  if [[ -f "$file" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      key="${line%%=*}"
      val="${line#*=}"
      [[ -n "$key" && "$val" =~ ^[0-9]+$ ]] || continue
      LAST_COUNTS["$key"]="$val"
    done <"$file"
  fi
}

save_state() {
  local file="$1"
  : >"$file"
  for key in "${!CURRENT_COUNTS[@]}"; do
    printf '%s=%s\n' "$key" "${CURRENT_COUNTS[$key]}" >>"$file"
  done
}

promote_key() {
  local key="$1"
  local prev="$2"
  local now="$3"
  if [[ -z "$key" ]]; then
    return 0
  fi
  mkdir -p "$LOG_DIR"
  if [[ -f "$CRON_PROMOTE_FILE" ]] && grep -Fxq "$key" "$CRON_PROMOTE_FILE"; then
    return 0
  fi
  printf '%s\n' "$key" >>"$CRON_PROMOTE_FILE"
  log_line "CRON_PROMOTE ${key} prev=${prev} now=${now}"
}

collect_cron_keys() {
  local file="$1"
  local line
  while IFS= read -r line; do
    line="${line//$'\r'/}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*= ]]; then
      continue
    fi

    read -r -a tokens <<<"$line"
    local -a cmd_tokens=()
    if [[ "${tokens[0]:-}" == @* ]]; then
      [[ ${#tokens[@]} -lt 2 ]] && continue
      cmd_tokens=("${tokens[@]:1}")
    else
      [[ ${#tokens[@]} -lt 6 ]] && continue
      cmd_tokens=("${tokens[@]:5}")
    fi

    local key=""
    local tok
    for tok in "${cmd_tokens[@]}"; do
      tok="${tok#\"}"; tok="${tok%\"}"
      tok="${tok#\'}"; tok="${tok%\'}"
      if [[ "$tok" == *"$BASE_DIR"* && ( "$tok" == *.sh || "$tok" == *.py ) ]]; then
        key="$tok"
      fi
    done
    if [[ -z "$key" && ${#cmd_tokens[@]} -gt 0 ]]; then
      key="${cmd_tokens[0]}"
    fi
    [[ -n "$key" ]] && printf '%s\n' "$key"
  done <"$file" | sort -u
}

extract_station_after_script() {
  local cmd="$1"
  local script="$2"
  local station=""
  read -r -a tokens <<<"$cmd"
  for i in "${!tokens[@]}"; do
    if [[ "${tokens[$i]}" == *"$script" ]]; then
      station="${tokens[$((i+1))]:-}"
      break
    fi
  done
  if [[ "$station" =~ ^[0-9]+$ ]]; then
    echo "$station"
  else
    echo ""
  fi
}

extract_station_flag() {
  local cmd="$1"
  local station=""
  read -r -a tokens <<<"$cmd"
  local expect=false
  for tok in "${tokens[@]}"; do
    if $expect; then
      station="$tok"
      break
    fi
    case "$tok" in
      -s|--station)
        expect=true
        ;;
      --station=*)
        station="${tok#*=}"
        break
        ;;
      -s*)
        station="${tok#-s}"
        if [[ -n "$station" ]]; then
          break
        fi
        ;;
    esac
  done
  if [[ "$station" =~ ^[0-9]+$ ]]; then
    echo "$station"
  else
    echo ""
  fi
}

kill_pids() {
  local reason="$1"
  shift
  local -a pids=("$@")
  if (( ${#pids[@]} == 0 )); then
    return 0
  fi

  log_line "Killing ${#pids[@]} process(es) (${reason}): ${pids[*]}"
  if [[ "$WATCHDOG_DRY_RUN" == "1" ]]; then
    log_line "DRY_RUN=1 set; no processes terminated."
    return 0
  fi

  kill -TERM "${pids[@]}" 2>/dev/null || true
  sleep "$WATCHDOG_GRACE_SECONDS"
  local -a still=()
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      still+=("$pid")
    fi
  done
  if (( ${#still[@]} > 0 )); then
    log_line "Escalating to SIGKILL for ${#still[@]} PIDs: ${still[*]}"
    kill -KILL "${still[@]}" 2>/dev/null || true
  fi
}

handle_group() {
  local group="$1"
  local max_allowed="$2"
  local label="$3"
  local items_str="$4"

  IFS=' ' read -r -a items <<<"$items_str"
  local count="${#items[@]}"
  if (( count <= max_allowed )); then
    return 0
  fi

  mapfile -t sorted < <(printf '%s\n' "${items[@]}" | sort -t: -k2,2nr)
  local -a kill_list=()
  for ((i=max_allowed; i<${#sorted[@]}; i++)); do
    pid="${sorted[$i]%%:*}"
    if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ && "$pid" != "$$" && "$pid" != "$PPID" ]]; then
      kill_list+=("$pid")
    fi
  done
  if (( ${#kill_list[@]} > 0 )); then
    kill_pids "${label} (allowed=${max_allowed}, found=${count})" "${kill_list[@]}"
  fi
}

{
  flock -n 9 || exit 0

  declare -A group_items=()
  declare -A group_max=()
  declare -A group_label=()

  while IFS= read -r pid etimes cmd; do
    [[ -z "${pid:-}" || -z "${etimes:-}" ]] && continue
    [[ ! "$pid" =~ ^[0-9]+$ ]] && continue

    if [[ "$cmd" == *"guide_raw_to_corrected.sh"* ]]; then
      station="$(extract_station_flag "$cmd")"
      [[ -z "$station" ]] && continue
      group="guide_raw_${station}"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_GUIDE_RAW_PER_STATION"
      group_label["$group"]="guide_raw_to_corrected station ${station}"
      continue
    fi

    if [[ "$cmd" == *"guide_corrected_to_accumulated.sh"* ]]; then
      group="guide_step2_all"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_GUIDE_STEP2_TOTAL"
      group_label["$group"]="guide_corrected_to_accumulated"
      continue
    fi

    if [[ "$cmd" == *"guide_accumulated_to_joined.sh"* ]]; then
      group="guide_step3_all"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_GUIDE_STEP3_TOTAL"
      group_label["$group"]="guide_accumulated_to_joined"
      continue
    fi

    if [[ "$cmd" == *"bring_reprocessing_files.sh"* ]]; then
      station="$(extract_station_after_script "$cmd" "bring_reprocessing_files.sh")"
      [[ -z "$station" ]] && continue
      group="bring_reproc_${station}"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_BRING_REPROC_PER_STATION"
      group_label["$group"]="bring_reprocessing_files station ${station}"
      continue
    fi

    if [[ "$cmd" == *"unpack_reprocessing_files.sh"* ]]; then
      station="$(extract_station_after_script "$cmd" "unpack_reprocessing_files.sh")"
      [[ -z "$station" ]] && continue
      group="unpack_reproc_${station}"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_UNPACK_REPROC_PER_STATION"
      group_label["$group"]="unpack_reprocessing_files station ${station}"
      continue
    fi

    if [[ "$cmd" == *"bring_data_and_config_files.sh"* ]]; then
      station="$(extract_station_after_script "$cmd" "bring_data_and_config_files.sh")"
      [[ -z "$station" ]] && continue
      group="bring_newfiles_${station}"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_BRING_NEWFILES_PER_STATION"
      group_label["$group"]="bring_data_and_config_files station ${station}"
      continue
    fi

    if [[ "$cmd" == *"run_step.sh"* ]]; then
      group="sim_run_step"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_RUN_STEP_TOTAL"
      group_label["$group"]="simulation run_step.sh"
      continue
    fi

    if [[ "$cmd" == *"step_0_setup_to_blank.py"* ]]; then
      group="sim_step0_setup"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_STEP0_SETUP_TOTAL"
      group_label["$group"]="simulation step_0_setup_to_blank"
      continue
    fi

    if [[ "$cmd" == *"step_final_daq_to_station_dat.py"* ]]; then
      group="sim_step_final"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_STEPFINAL_TOTAL"
      group_label["$group"]="simulation step_final_daq_to_station_dat"
      continue
    fi

    if [[ "$cmd" == *"sanitize_sim_runs.py"* ]]; then
      group="sim_sanitize"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_SANITIZE_TOTAL"
      group_label["$group"]="simulation sanitize_sim_runs"
      continue
    fi

    if [[ "$cmd" == *"reset_param_mesh_from_final.py"* ]]; then
      group="sim_reset"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_RESET_TOTAL"
      group_label["$group"]="simulation reset_param_mesh_from_final"
      continue
    fi

    if [[ "$cmd" == *"ingest_simulated_station_data.py"* ]]; then
      group="sim_ingest"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_SIM_INGEST_TOTAL"
      group_label["$group"]="simulation ingest_simulated_station_data"
      continue
    fi

    if [[ "$cmd" == *"copernicus_bring.py"* ]]; then
      station="$(extract_station_after_script "$cmd" "copernicus_bring.py")"
      [[ -z "$station" ]] && continue
      group="copernicus_${station}"
      group_items["$group"]+="${pid}:${etimes} "
      group_max["$group"]="$MAX_COPERNICUS_PER_STATION"
      group_label["$group"]="copernicus_bring station ${station}"
      continue
    fi
  done < <(ps -eo pid=,etimes=,cmd=)

  for group in "${!group_items[@]}"; do
    handle_group "$group" "${group_max[$group]}" "${group_label[$group]}" "${group_items[$group]}"
  done

  if [[ "$CRON_REPORT_ENABLED" == "1" && -f "$CRON_FILE" ]]; then
    declare -A LAST_COUNTS=()
    declare -A CURRENT_COUNTS=()
    load_state "$CRON_REPORT_STATE_FILE"
    mapfile -t cron_keys < <(collect_cron_keys "$CRON_FILE")
    if (( ${#cron_keys[@]} > 0 )); then
      summary=""
      promote_factor="$CRON_PROMOTE_FACTOR"
      promote_min_count="$(sanitize_nonneg_int "$CRON_PROMOTE_MIN_COUNT")"
      promote_delta="$(sanitize_nonneg_int "$CRON_PROMOTE_DELTA")"
      for key in "${cron_keys[@]}"; do
        if [[ -n "$CRON_REPORT_EXCLUDE_REGEX" ]] && [[ "$key" =~ $CRON_REPORT_EXCLUDE_REGEX ]]; then
          continue
        fi
        pattern="$(regex_escape "$key")"
        count="$(sanitize_nonneg_int "$(pgrep -fc -f "$pattern" 2>/dev/null || true)")"
        CURRENT_COUNTS["$key"]="$count"
        prev="$(sanitize_nonneg_int "${LAST_COUNTS[$key]:-0}")"
        if [[ "$CRON_PROMOTE_ENABLED" == "1" ]]; then
          if (( count >= promote_min_count )); then
            if (( count - prev >= promote_delta )); then
              promote_key "$key" "$prev" "$count"
            elif (( prev > 0 )) && awk -v n="$count" -v p="$prev" -v f="$promote_factor" 'BEGIN{exit !(n >= p*f)}'; then
              promote_key "$key" "$prev" "$count"
            fi
          fi
        fi
        if [[ "$CRON_REPORT_DIFF_ONLY" == "1" ]]; then
          if [[ "$count" != "$prev" ]]; then
            summary+="${key}=${count} (was ${prev}); "
          fi
        else
          summary+="${key}=${count}; "
        fi
      done
      if [[ -n "$summary" ]]; then
        log_line "CRON_REPORT ${summary}"
      fi
    fi
    save_state "$CRON_REPORT_STATE_FILE"
  fi

} 9>"$LOCK_FILE"
