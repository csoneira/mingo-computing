#!/bin/bash

# Resolve the checkout from this script's location when the caller did not provide it.
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
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/guide_accumulated_to_joined.sh
# Purpose: Guide accumulated to joined.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/guide_accumulated_to_joined.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

log_ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
  printf '[%s] [STEP_3] %s\n' "$(log_ts)" "$*"
}

log_warn() {
  printf '[%s] [STEP_3] [WARN] %s\n' "$(log_ts)" "$*" >&2
}

print_help() {
  cat <<'EOF'
guide_accumulated_to_joined.sh
Launches STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA for one or more stations.

Usage:
  guide_accumulated_to_joined.sh [--station <list>] [--run-anyway]

Options:
  -s, --station   Station numbers (1-8). Comma/space-separated. Default: all.
  --run-anyway    Skip the check that prevents overlapping runs.
  -h, --help      Show this help message and exit.

When run without arguments (typical cron usage), the script loops
continuously, processing stations according to the traffic-light queue
persisted in CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/TRAFFIC_LIGHT. Each station is moved to the end
of the queue as soon as it is selected, so the next invocation continues with
the following station even if the current run exits early.
EOF
}

station_filter_raw="all"
station_filter_overridden=false
run_anyway=false
no_loop=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--station)
      station_filter_raw="${2:-}"
      station_filter_overridden=true
      shift 2
      ;;
    --station=*)
      station_filter_raw="${1#*=}"
      station_filter_overridden=true
      shift
      ;;
    --run-anyway)
      run_anyway=true
      shift
      ;;
    --no-loop)
      no_loop=true
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    [0-4])
      station_filter_raw="$1"
      station_filter_overridden=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      exit 1
      ;;
  esac
done

ALL_STATIONS=(0 1 2 3 4)
TRAFFIC_LIGHT_DIR="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/TRAFFIC_LIGHT"
TRAFFIC_QUEUE_FILE="$TRAFFIC_LIGHT_DIR/stage2_event_step2_daily_event_data_station_queue.txt"

SELF_INVOCATION_PIDS=()

collect_self_invocation_pids() {
  local pid="$$"
  local guard=0

  while [[ -n "$pid" && "$pid" =~ ^[0-9]+$ && $pid -gt 1 && $guard -lt 20 ]]; do
    SELF_INVOCATION_PIDS+=("$pid")
    pid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    guard=$((guard + 1))
    [[ -z "$pid" ]] && break
  done

  if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]]; then
    SELF_INVOCATION_PIDS+=("$pid")
  fi

  if [[ -n "${PPID:-}" && "$PPID" =~ ^[0-9]+$ ]]; then
    SELF_INVOCATION_PIDS+=("$PPID")
  fi
}

collect_self_invocation_pids

pid_is_self_or_ancestor() {
  local candidate="$1"
  for spid in "${SELF_INVOCATION_PIDS[@]}"; do
    if [[ -n "$spid" && "$candidate" == "$spid" ]]; then
      return 0
    fi
  done
  return 1
}

parse_list() {
  local raw="$1"
  local default_array_name="$2"
  local out_var="$3"

  if [[ -z "$raw" || "$raw" == "all" ]]; then
    eval "$out_var=(\"\${${default_array_name}[@]}\")"
    return
  fi

  local tmp=()
  IFS=', ' read -r -a parts <<<"$raw"
  for p in "${parts[@]}"; do
    [[ -z "$p" ]] && continue
    tmp+=("$p")
  done
  eval "$out_var=(\"\${tmp[@]}\")"
}

sanitize_queue_file() {
  mkdir -p "$TRAFFIC_LIGHT_DIR"
  local -a sanitized
  local -A valid_map=()
  for st in "${ALL_STATIONS[@]}"; do
    valid_map["$st"]=1
  done

  sanitized=()
  declare -A seen=()
  if [[ -s "$TRAFFIC_QUEUE_FILE" ]]; then
    while IFS= read -r line; do
      line="${line//$'\r'/}"
      line="${line//[$'\t ']/}"
      [[ -z "$line" ]] && continue
      if [[ -n "${valid_map[$line]:-}" && -z "${seen[$line]:-}" ]]; then
        sanitized+=("$line")
        seen["$line"]=1
      fi
    done <"$TRAFFIC_QUEUE_FILE"
  fi

  for st in "${ALL_STATIONS[@]}"; do
    if [[ -z "${seen[$st]:-}" ]]; then
      sanitized+=("$st")
    fi
  done

  if [[ ${#sanitized[@]} -eq 0 ]]; then
    sanitized=("${ALL_STATIONS[@]}")
  fi

  {
    for st in "${sanitized[@]}"; do
      echo "$st"
    done
  } >"$TRAFFIC_QUEUE_FILE"
}

load_queue_snapshot() {
  local -n out_arr=$1
  out_arr=()
  [[ -f "$TRAFFIC_QUEUE_FILE" ]] || sanitize_queue_file
  if [[ -f "$TRAFFIC_QUEUE_FILE" ]]; then
    while IFS= read -r line; do
      line="${line//$'\r'/}"
      line="${line//[$'\t ']/}"
      [[ -z "$line" ]] && continue
      out_arr+=("$line")
    done <"$TRAFFIC_QUEUE_FILE"
  fi
}

build_iteration_stations() {
  local -n out_arr=$1
  local -A requested_map=()
  for st in "${stations_requested[@]}"; do
    requested_map["$st"]=0
  done

  local -a queue_snapshot
  load_queue_snapshot queue_snapshot

  out_arr=()
  for entry in "${queue_snapshot[@]}"; do
    if [[ -n "${requested_map[$entry]:-}" ]]; then
      out_arr+=("$entry")
      requested_map["$entry"]=1
    fi
  done

  for st in "${stations_requested[@]}"; do
    if [[ "${requested_map[$st]}" -ne 1 ]]; then
      out_arr+=("$st")
    fi
  done

  if [[ ${#out_arr[@]} -eq 0 ]]; then
    out_arr=("${stations_requested[@]}")
  fi
}

rotate_station_to_queue_end() {
  local station="$1"
  [[ -f "$TRAFFIC_QUEUE_FILE" ]] || sanitize_queue_file
  local -a snapshot new_order
  snapshot=()
  if [[ -f "$TRAFFIC_QUEUE_FILE" ]]; then
    while IFS= read -r line; do
      line="${line//$'\r'/}"
      line="${line//[$'\t ']/}"
      [[ -z "$line" ]] && continue
      snapshot+=("$line")
    done <"$TRAFFIC_QUEUE_FILE"
  fi

  local moved=false
  for entry in "${snapshot[@]}"; do
    if [[ "$entry" == "$station" && "$moved" == false ]]; then
      moved=true
      continue
    fi
    new_order+=("$entry")
  done
  new_order+=("$station")

  {
    for entry in "${new_order[@]}"; do
      echo "$entry"
    done
  } >"$TRAFFIC_QUEUE_FILE"
}

parse_list "$station_filter_raw" ALL_STATIONS stations_requested

validate_stations() {
  local arr=("$@")
  local validated=()
  for st in "${arr[@]}"; do
    if [[ "$st" =~ ^[0-4]$ ]]; then
      validated+=("$st")
    else
      log_warn "ignoring invalid station '$st'"
    fi
  done
  if [[ ${#validated[@]} -eq 0 ]]; then
    echo "Error: no valid stations to process." >&2
    exit 1
  fi
  stations_requested=("${validated[@]}")
}

validate_stations "${stations_requested[@]}"

use_traffic_light=true
if [[ "$station_filter_overridden" == true ]]; then
  use_traffic_light=false
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "$MASTER_DIR" != "/" && "$(basename "$MASTER_DIR")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
  MASTER_DIR="$(dirname "$MASTER_DIR")"
done
accumulated_distributor_py="$SCRIPT_DIR/TASK_1/accumulated_distributor.py"
distributed_joiner_py="$SCRIPT_DIR/TASK_2/distributed_joiner.py"

any_pipeline_running() {
  local hits
  local self_pid="$$"
  hits=$(pgrep -af "guide_accumulated_to_joined.sh" || true)
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local pid="${line%% *}"
    [[ -z "$pid" ]] && continue
    [[ ! "$pid" =~ ^[0-9]+$ ]] && continue
    if pid_is_self_or_ancestor "$pid"; then
      continue
    fi
    if (( pid >= self_pid )); then
      continue
    fi
    [[ "$line" == *"pgrep"* ]] && continue
    return 0
  done <<<"$hits"
  return 1
}

process_station() {
  local station="$1"
  log_info "Processing station ${station} (STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA)."

  if ! python3 -u "$accumulated_distributor_py" "$station"; then
    log_warn "Station $station STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA distributor failed; continuing with next station."
    return 1
  fi

  if ! python3 -u "$distributed_joiner_py" "$station"; then
    log_warn "Station $station STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA joiner failed; continuing with next station."
    return 1
  fi

  log_info "Station $station STAGE_2 EVENT_DATA STEP_2_DAILY_EVENT_DATA completed."
  return 0
}

log_info "guide_accumulated_to_joined.sh started (stations=${stations_requested[*]} traffic_light=${use_traffic_light} no_loop=${no_loop})."

if [[ "$use_traffic_light" == true ]]; then
  sanitize_queue_file
fi

if [[ "$run_anyway" != true ]]; then
  if any_pipeline_running; then
    log_warn "Another guide_accumulated_to_joined.sh is already running; exiting. Use --run-anyway to override."
    exit 0
  fi
fi

iteration=1

if [[ "$use_traffic_light" == true ]]; then
  while true; do
    build_iteration_stations iteration_stations
    for station in "${iteration_stations[@]}"; do
      rotate_station_to_queue_end "$station"
      process_station "$station"
    done
    iteration=$((iteration + 1))
    if [[ "$no_loop" == true ]]; then
      log_info "--no-loop flag set; exiting after single pass."
      break
    fi
  done
else
  for station in "${stations_requested[@]}"; do
    process_station "$station"
  done
fi
