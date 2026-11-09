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
# Task scripts run by absolute path; include the repository root so package imports resolve after layout changes.
export PYTHONPATH="${DATAFLOW_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/guide_raw_to_corrected.sh
# Purpose: log_file="${LOG_FILE:-~/cron_logs/bring_and_analyze_events_${station}.log}".
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/guide_raw_to_corrected.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# log_file="${LOG_FILE:-~/cron_logs/bring_and_analyze_events_${station}.log}"
# mkdir -p "$(dirname "$log_file")"

# Station specific -----------------------------
original_args=("$@")
original_args_string="$*"

log_ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
  printf '[%s] [STEP_1] %s\n' "$(log_ts)" "$*"
}

log_warn() {
  printf '[%s] [STEP_1] [WARN] %s\n' "$(log_ts)" "$*" >&2
}

log_err() {
  printf '[%s] [STEP_1] [ERROR] %s\n' "$(log_ts)" "$*" >&2
}

is_tty() {
  [[ -t 1 ]]
}

declare -A LAST_LOG_TS=()

log_rate_limited() {
  local key="$1"
  local interval="$2"
  shift 2
  local now last
  now=$(date +%s)
  last="${LAST_LOG_TS[$key]:-0}"
  if (( now - last >= interval )); then
    LAST_LOG_TS["$key"]="$now"
    log_info "$*"
  fi
}

log_rate_limited_warn() {
  local key="$1"
  local interval="$2"
  shift 2
  local now last
  now=$(date +%s)
  last="${LAST_LOG_TS[$key]:-0}"
  if (( now - last >= interval )); then
    LAST_LOG_TS["$key"]="$now"
    log_warn "$*"
  fi
}

print_help() {
  cat <<'EOF'
guide_raw_to_corrected.sh
Launches the STAGE_1 EVENT_DATA STEP_1 pipeline for a station.

Usage:
  guide_raw_to_corrected.sh [--station <list>] [--task <list>] [--self-trigger] [--run-anyway] [--verbose]

Options:
  -s, --station   Station numbers (0-4). Comma-separated or space-separated. Default: all.
  -t, --task      Task IDs to run (default: all tasks for selected flow).
  --self-trigger  Select the parallel self-trigger task sequence instead of coincidence Tasks 0-5.
                  Self-trigger tasks run as a parallel numbered sequence (currently 1-2).
  --run-anyway    Skip the check that prevents overlapping guide_raw_to_corrected.sh runs.
  -v, --verbose   Pass --verbose to each inner STEP_1 Python task script.
  -h, --help      Show this help message and exit.

When multiple stations and tasks are provided, tasks are executed in task-major
order (e.g., stations 1,2 and tasks 0,1 run as: 1-0, 2-0, 1-1, 2-1),
looping continuously. If another guide_raw_to_corrected.sh is already running
for a station, that station is skipped for this invocation.

This script also re-reads config_step_1.yaml on every outer loop iteration to
optionally enable/disable station-task pairs via the selected run matrix.
EOF
}

station_filter_raw="all"
task_filter_raw="all"
run_anyway=false
task_verbose=false
self_trigger_mode=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--station)
      station_filter_raw="${2:-}"
      shift 2
      ;;
    -t|--task)
      task_filter_raw="${2:-}"
      shift 2
      ;;
    --self-trigger)
      self_trigger_mode=true
      shift
      ;;
    --run-anyway)
      run_anyway=true
      shift
      ;;
    -v|--verbose)
      task_verbose=true
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      exit 1
      ;;
  esac
done

TASK_VERBOSE_ARGS=()
if [[ "$task_verbose" == true ]]; then
  TASK_VERBOSE_ARGS+=(--verbose)
fi


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "${MASTER_DIR}" != "/" && "$(basename "${MASTER_DIR}")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
    MASTER_DIR="$(dirname "${MASTER_DIR}")"
done
STATUS_HELPER="${MASTER_DIR}/SUPPORT/SHARED_CODE/status_csv.py"
STATUS_TIMESTAMP=""
# STATUS_CSV=""

TASK_SCRIPTS=(
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_0/script_0_acq_to_raw.py"
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_1/script_1_raw_to_clean.py"
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_2/script_2_clean_to_cal.py"
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_3/script_3_cal_to_list.py"
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_4/script_4_list_to_fit.py"
  "$SCRIPT_DIR/COIN_TRIGGER/TASK_5/script_5_fit_to_post.py"
)

TASK_LABELS=(
  "acq_to_raw"
  "raw_to_clean"
  "clean_to_cal"
  "cal_to_list"
  "list_to_fit"
  "fit_to_corr"
)

# A separate numeric namespace for the parallel self-trigger line. Add future
# self-trigger task N scripts at index N without changing coincidence IDs.
SELF_TRIGGER_TASK_SCRIPTS=(
  ""
  "$SCRIPT_DIR/SELF_TRIGGER/TASK_1_SELFTRIGGER/script_1_selftrigger_raw_to_diagnostic.py"
  "$SCRIPT_DIR/SELF_TRIGGER/TASK_2_SELFTRIGGER/script_2_selftrigger_clean_to_cal.py"
)
SELF_TRIGGER_TASK_LABELS=("" "task_1_selftrigger_raw_to_diagnostic" "task_2_selftrigger_clean_to_cal")

TRAFFIC_LIGHT_DIR="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/TRAFFIC_LIGHT"
TRAFFIC_QUEUE_FILE=""
TRAFFIC_QUEUE_FILE_PREFIX="stage1_step1_station_task_queue"
config_file="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/config_step_1.yaml"

# Runtime tuning (overridden by config_step_1.yaml if present)
STEP1_CONFIG_REFRESH_S=${STEP1_CONFIG_REFRESH_S:-30}
STEP1_IDLE_SLEEP_S=${STEP1_IDLE_SLEEP_S:-60}
STEP1_RESOURCE_BACKOFF_S=${STEP1_RESOURCE_BACKOFF_S:-15}
STEP1_ALREADY_RUNNING_LOG_S=${STEP1_ALREADY_RUNNING_LOG_S:-300}
LAST_CONFIG_REFRESH_TS=0
LAST_CONFIG_MTIME=0
GLOBAL_LOG_THROTTLE_DIR="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOG_THROTTLE"

sanitize_key() {
  local key="$1"
  printf '%s\n' "${key//[^A-Za-z0-9_-]/_}"
}

log_rate_limited_global() {
  local key_raw="$1"
  local interval="$2"
  shift 2
  local key now stamp_file last
  key=$(sanitize_key "$key_raw")
  now=$(date +%s)
  mkdir -p "$GLOBAL_LOG_THROTTLE_DIR"
  stamp_file="$GLOBAL_LOG_THROTTLE_DIR/${key}.ts"
  last=0
  if [[ -f "$stamp_file" ]]; then
    last=$(<"$stamp_file") || last=0
    [[ "$last" =~ ^[0-9]+$ ]] || last=0
  fi
  if (( now - last >= interval )); then
    printf '%s' "$now" >"$stamp_file"
    log_info "$*"
  fi
}

build_default_queue_order() {
  local -n out_arr=$1
  out_arr=("${execution_pairs[@]}")
}

station_has_task0_backlog() {
  local station="$1"
  local station_tag station_name stage0_dir task0_unprocessed_dir
  station_tag="$(printf 'mi%02d' "$station")"
  station_name="MINGO$(printf '%02d' "$station")"
  stage0_dir="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/${station_name}/STAGE_0_TO_1"
  task0_unprocessed_dir="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/${station_name}/STAGE_1/EVENT_DATA/STEP_1/TASK_0/INPUT_FILES/UNPROCESSED_DIRECTORY"
  if [[ -d "$stage0_dir" ]] && compgen -G "${stage0_dir}/${station_tag}*.dat" >/dev/null; then
    return 0
  fi
  if [[ -d "$task0_unprocessed_dir" ]] && compgen -G "${task0_unprocessed_dir}/${station_tag}*.dat" >/dev/null; then
    return 0
  fi
  return 1
}

sanitize_queue_file() {
  local -a default_pairs sanitized prioritized remainder
  build_default_queue_order default_pairs

  declare -A valid_map=()
  for pair in "${default_pairs[@]}"; do
    valid_map["$pair"]=1
  done

  sanitized=()
  declare -A seen_pairs=()
  if [[ -s "$TRAFFIC_QUEUE_FILE" ]]; then
    while IFS= read -r line; do
      line="${line//$'\r'/}"
      line="${line//[$'\t ']/}"
      [[ -z "$line" ]] && continue
      if [[ -n "${valid_map[$line]:-}" && -z "${seen_pairs[$line]:-}" ]]; then
        sanitized+=("$line")
        seen_pairs["$line"]=1
      fi
    done <"$TRAFFIC_QUEUE_FILE"
  fi

  for pair in "${default_pairs[@]}"; do
    if [[ -z "${seen_pairs[$pair]:-}" ]]; then
      sanitized+=("$pair")
    fi
  done

  if [[ ${#sanitized[@]} -eq 0 ]]; then
    sanitized=("${default_pairs[@]}")
  fi

  prioritized=()
  remainder=()
  for pair in "${sanitized[@]}"; do
    IFS='-' read -r pair_station pair_task <<<"$pair"
    if [[ "$pair_task" == "0" ]] && station_has_task0_backlog "$pair_station"; then
      prioritized+=("$pair")
    else
      remainder+=("$pair")
    fi
  done
  if [[ ${#prioritized[@]} -gt 0 ]]; then
    sanitized=("${prioritized[@]}" "${remainder[@]}")
  fi

  {
    for pair in "${sanitized[@]}"; do
      echo "$pair"
    done
  } >"$TRAFFIC_QUEUE_FILE"
}

traffic_light_queue_init() {
  mkdir -p "$TRAFFIC_LIGHT_DIR"
  sanitize_queue_file
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

build_iteration_pairs_from_queue() {
  local -n out_arr=$1
  local -A requested_map=()
  for pair in "${execution_pairs[@]}"; do
    requested_map["$pair"]=0
  done

  local -a queue_snapshot
  load_queue_snapshot queue_snapshot

  out_arr=()
  for pair in "${queue_snapshot[@]}"; do
    if [[ -n "${requested_map[$pair]:-}" ]]; then
      out_arr+=("$pair")
      requested_map["$pair"]=1
    fi
  done

  for pair in "${execution_pairs[@]}"; do
    if [[ "${requested_map[$pair]}" -ne 1 ]]; then
      out_arr+=("$pair")
    fi
  done

  if [[ ${#out_arr[@]} -eq 0 ]]; then
    out_arr=("${execution_pairs[@]}")
  fi
}

rotate_pair_to_queue_end() {
  local pair="$1"
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
    if [[ "$entry" == "$pair" && "$moved" == false ]]; then
      moved=true
      continue
    fi
    new_order+=("$entry")
  done
  new_order+=("$pair")

  {
    for entry in "${new_order[@]}"; do
      echo "$entry"
    done
  } >"$TRAFFIC_QUEUE_FILE"
}

parse_list() {
  local raw="$1"
  local default_array_name="$2"
  local out_var="$3"

  # Use the provided defaults if raw is empty/all
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

ALL_STATIONS=(0 1 2 3 4)
COINCIDENCE_TASK_IDS=(0 1 2 3 4 5)
SELF_TRIGGER_TASK_IDS=(1 2)
if [[ "$self_trigger_mode" == true ]]; then
  ALL_TASK_IDS=("${SELF_TRIGGER_TASK_IDS[@]}")
  TRAFFIC_QUEUE_FILE_PREFIX="stage1_selftrigger_station_task_queue"
  RUN_MATRIX_KEY="self_trigger_step1_run_matrix"
else
  ALL_TASK_IDS=("${COINCIDENCE_TASK_IDS[@]}")
  RUN_MATRIX_KEY="event_data_step1_run_matrix"
fi

LOCK_BASE_DIR="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/guide_raw_to_corrected"
ARG_LOCK_FILE=""
ARG_LOCK_FD=""
LOCK_SIGNATURE_DESC=""

format_original_args() {
  if (( ${#original_args[@]} == 0 )); then
    printf '[no explicit args]'
    return
  fi
  local rendered=()
  local arg
  for arg in "${original_args[@]}"; do
    rendered+=("$(printf '%q' "$arg")")
  done
  printf '%s' "${rendered[*]}"
}

prepare_argument_signature() {
  local payload=""
  if (( ${#original_args[@]} == 0 )); then
    payload="__default__"
    LOCK_SIGNATURE_DESC="[no explicit args]"
  else
    LOCK_SIGNATURE_DESC="$(format_original_args)"
    payload=$(printf '%s\037' "${original_args[@]}")
  fi
  local hash
  hash=$(printf '%s' "$payload" | md5sum | awk '{print $1}')
  ARG_LOCK_FILE="${LOCK_BASE_DIR}/${hash}.lock"
}

acquire_argument_lock() {
  prepare_argument_signature
  mkdir -p "$LOCK_BASE_DIR"
  exec {ARG_LOCK_FD}> "$ARG_LOCK_FILE"
  if ! flock -n "$ARG_LOCK_FD"; then
    # Under cron this is expected and extremely frequent; avoid log spam.
    if is_tty; then
      log_warn "Another guide_raw_to_corrected.sh with identical arguments (${LOCK_SIGNATURE_DESC}) is already running."
      log_info "Lock file: ${ARG_LOCK_FILE}"
      log_info "Use --run-anyway to override this safety check."
    fi
    return 1
  fi
  log_info "Acquired run lock for argument set ${LOCK_SIGNATURE_DESC} (lock: ${ARG_LOCK_FILE})."
  return 0
}

release_argument_lock() {
  if [[ -n "${ARG_LOCK_FD:-}" ]]; then
    flock -u "$ARG_LOCK_FD" 2>/dev/null || true
    eval "exec ${ARG_LOCK_FD}>&-" 2>/dev/null || true
    ARG_LOCK_FD=""
    if [[ -n "${ARG_LOCK_FILE:-}" ]]; then
      rm -f "$ARG_LOCK_FILE"
      ARG_LOCK_FILE=""
    fi
  fi
}

# Collect the PID chain (this shell plus ancestors spawned by cron/bash -c) so
# the duplicate detector can ignore them when scanning for real other runs.
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

parse_list "$station_filter_raw" ALL_STATIONS stations_requested
parse_list "$task_filter_raw" ALL_TASK_IDS tasks_requested

validate_stations() {
  local arr=("$@")
  local validated=()
  for s in "${arr[@]}"; do
    if [[ "$s" =~ ^[0-4]$ ]]; then
      validated+=("$s")
    else
      log_warn "ignoring invalid station '$s' (must be 0-4)"
    fi
  done
  if [[ ${#validated[@]} -eq 0 ]]; then
    echo "Error: no valid stations to process." >&2
    exit 1
  fi
  stations_requested=("${validated[@]}")
}

validate_tasks() {
  local arr=("$@")
  local validated=()
  for t in "${arr[@]}"; do
    if [[ "$self_trigger_mode" == true ]]; then
      if [[ "$t" =~ ^[1-9][0-9]*$ ]] && (( t < ${#SELF_TRIGGER_TASK_SCRIPTS[@]} )) && [[ -n "${SELF_TRIGGER_TASK_SCRIPTS[$t]:-}" ]]; then
        validated+=("$t")
      else
        local registered_ids=()
        local registered_id
        for registered_id in "${!SELF_TRIGGER_TASK_SCRIPTS[@]}"; do
          [[ -n "${SELF_TRIGGER_TASK_SCRIPTS[$registered_id]:-}" ]] && registered_ids+=("$registered_id")
        done
        log_warn "ignoring invalid self-trigger task '$t' (registered IDs: ${registered_ids[*]})"
      fi
    else
      if [[ "$t" =~ ^[0-5]$ ]]; then
        validated+=("$t")
      else
        log_warn "ignoring invalid coincidence task '$t' (must be 0-5)"
      fi
    fi
  done
  if [[ ${#validated[@]} -eq 0 ]]; then
    echo "Error: no valid tasks to process in the selected flow." >&2
    exit 1
  fi
  tasks_requested=("${validated[@]}")
}

validate_stations "${stations_requested[@]}"
validate_tasks "${tasks_requested[@]}"

queue_station_key="$(IFS='-'; echo "${stations_requested[*]}")"
queue_task_key="$(IFS='-'; echo "${tasks_requested[*]}")"
queue_signature="$(sanitize_key "s${queue_station_key}_t${queue_task_key}")"
TRAFFIC_QUEUE_FILE="${TRAFFIC_LIGHT_DIR}/${TRAFFIC_QUEUE_FILE_PREFIX}_${queue_signature}.txt"

refresh_execution_pairs_from_config() {
  local cfg_path="$config_file"
  local force="${1:-false}"
  local stations_csv tasks_csv result now mtime
  stations_csv="$(IFS=,; echo "${stations_requested[*]}")"
  tasks_csv="$(IFS=,; echo "${tasks_requested[*]}")"

  now=$(date +%s)
  mtime=0
  if [[ -f "$cfg_path" ]]; then
    mtime=$(stat -c %Y "$cfg_path" 2>/dev/null || echo 0)
  fi
  if [[ "$force" != "true" ]]; then
    if (( now - LAST_CONFIG_REFRESH_TS < STEP1_CONFIG_REFRESH_S )) && (( mtime == LAST_CONFIG_MTIME )); then
      return 1
    fi
  fi
  LAST_CONFIG_REFRESH_TS=$now
  LAST_CONFIG_MTIME=$mtime

  execution_pairs=()

  if [[ ! -f "$cfg_path" ]]; then
    for task_id in "${tasks_requested[@]}"; do
      for st in "${stations_requested[@]}"; do
        execution_pairs+=("${st}-${task_id}")
      done
    done
    return 0
  fi

  result=$(python3 - "$cfg_path" "$stations_csv" "$tasks_csv" "$RUN_MATRIX_KEY" <<'PY'
import sys

cfg_path, stations_csv, tasks_csv, matrix_key = sys.argv[1:5]

stations = [s.strip() for s in stations_csv.split(",") if s.strip()]
tasks_raw = [t.strip() for t in tasks_csv.split(",") if t.strip()]

idle_sleep = None
already_log = None
config_refresh = None
resource_backoff = None

def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def emit_cfg():
    def fmt(val):
        return "" if val is None else val
    print(
        "@CFG "
        f"idle_sleep_seconds={fmt(idle_sleep)} "
        f"already_running_log_seconds={fmt(already_log)} "
        f"config_refresh_seconds={fmt(config_refresh)} "
        f"resource_backoff_seconds={fmt(resource_backoff)}"
    )

try:
    import yaml
except ImportError:
    emit_cfg()
    for t in tasks_raw:
        for s in stations:
            print(f"{s}-{t}")
    raise SystemExit(0)

try:
    data = yaml.safe_load(open(cfg_path)) or {}
except Exception:
    data = {}

runtime = data.get(matrix_key) or {}
resource_limits = data.get("event_data_resource_limits") or {}

idle_sleep = _to_int(runtime.get("idle_sleep_seconds"))
already_log = _to_int(runtime.get("already_running_log_seconds"))
config_refresh = _to_int(runtime.get("config_refresh_seconds"))
resource_backoff = _to_int(resource_limits.get("resource_backoff_seconds"))
emit_cfg()

node = data.get(matrix_key) or {}
enabled = bool(node.get("enabled", False))

def normalize_tasks(value):
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "all":
            return "all"
        if not text:
            return []
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        out = []
        for part in parts:
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(value, (int, float)):
        try:
            return [int(value)]
        except (TypeError, ValueError):
            return []
    return []

tasks = []
for token in tasks_raw:
    try:
        tasks.append(int(token))
    except ValueError:
        continue

if not enabled:
    for t in tasks:
        for s in stations:
            print(f"{s}-{t}")
    raise SystemExit(0)

mode = str(node.get("mode", "whitelist")).strip().lower()
stations_node = node.get("stations") or {}
default_tasks = normalize_tasks(node.get("default_tasks", []))
station_tasks = {str(k): normalize_tasks(v) for k, v in stations_node.items()}

for t in tasks:
    for s in stations:
        key = str(s)
        st_val = station_tasks.get(key)

        if mode == "blacklist":
            disabled = False
            if st_val == "all":
                disabled = True
            elif isinstance(st_val, list) and t in st_val:
                disabled = True
            if not disabled:
                print(f"{s}-{t}")
            continue

        # whitelist (default)
        allowed = False
        if st_val is None:
            if default_tasks == "all":
                allowed = True
            elif isinstance(default_tasks, list) and t in default_tasks:
                allowed = True
        else:
            if st_val == "all":
                allowed = True
            elif isinstance(st_val, list) and t in st_val:
                allowed = True

        if allowed:
            print(f"{s}-{t}")
PY
  )

  while IFS= read -r line; do
    line="${line//$'\r'/}"
    [[ -z "$line" ]] && continue
    if [[ "$line" == "@CFG "* ]]; then
      local kv key val
      for kv in ${line#@CFG }; do
        key="${kv%%=*}"
        val="${kv#*=}"
        case "$key" in
          idle_sleep_seconds)
            [[ "$val" =~ ^[0-9]+$ ]] && STEP1_IDLE_SLEEP_S="$val"
            ;;
          already_running_log_seconds)
            [[ "$val" =~ ^[0-9]+$ ]] && STEP1_ALREADY_RUNNING_LOG_S="$val"
            ;;
          config_refresh_seconds)
            [[ "$val" =~ ^[0-9]+$ ]] && STEP1_CONFIG_REFRESH_S="$val"
            ;;
          resource_backoff_seconds)
            [[ "$val" =~ ^[0-9]+$ ]] && STEP1_RESOURCE_BACKOFF_S="$val"
            ;;
        esac
      done
      continue
    fi
    line="${line//[$'\t ']/}"
    [[ -z "$line" ]] && continue
    execution_pairs+=("$line")
  done <<<"$result"
}

cleanup() {
  release_argument_lock
}
trap cleanup EXIT

if [[ "$self_trigger_mode" == true ]]; then
  log_info "guide_raw_to_corrected.sh started (flow=self-trigger stations=${stations_requested[*]} tasks=${tasks_requested[*]})."
else
  log_info "guide_raw_to_corrected.sh started (flow=coincidence stations=${stations_requested[*]} tasks=${tasks_requested[*]})."
fi
refresh_execution_pairs_from_config true
log_info "Enabled station-task pairs: ${execution_pairs[*]}"


# dat_files_directory="/media/externalDisk/gate/system/devices/TRB3/data/daqData/asci"

# Resource gate defaults (overridden by config_step_1.yaml if present)
mem_limit_pct=90
swap_limit_pct=70
swap_limit_kb=$((4 * 1024 * 1024)) # 4 GB
cpu_limit_pct=95

# STATUS_CSV="$base_working_directory/raw_to_list_events_status.csv"
# if ! STATUS_TIMESTAMP="$(python3 "$STATUS_HELPER" append "$STATUS_CSV")"; then
#     echo "Warning: unable to record status in $STATUS_CSV" >&2
#     STATUS_TIMESTAMP=""
# fi

# finish() {
#     local exit_code="$1"
#     if [[ ${exit_code} -eq 0 && -n "${STATUS_TIMESTAMP:-}" && -n "${STATUS_CSV:-}" ]]; then
#         python3 "$STATUS_HELPER" complete "$STATUS_CSV" "$STATUS_TIMESTAMP" >/dev/null 2>&1 || true
#     fi
# }

# trap 'finish $?' EXIT

load_resource_limits() {
  local cfg_path="$config_file"
  local result
  if [[ -f "$cfg_path" ]]; then
    if result=$(python3 - "$cfg_path" <<'PY'
import sys
cfg_path = sys.argv[1]
try:
    import yaml
except ImportError:
    print(",,,,".strip(","))
    sys.exit(0)
try:
    data = yaml.safe_load(open(cfg_path)) or {}
except Exception:
    print(",,,,".strip(","))
    sys.exit(0)
node = data.get("event_data_resource_limits") or {}
def val(key):
    v = node.get(key)
    return "" if v is None else v
print(f"{val('mem_used_pct_max')},{val('swap_used_pct_max')},{val('swap_used_kb_max')},{val('cpu_used_pct_max')}")
PY
    ); then
      IFS=',' read -r cfg_mem cfg_swap_pct cfg_swap_kb cfg_cpu <<<"$result"
      if [[ $cfg_mem =~ ^[0-9]+$ ]]; then mem_limit_pct=$cfg_mem; fi
      if [[ $cfg_swap_pct =~ ^[0-9]+$ ]]; then swap_limit_pct=$cfg_swap_pct; fi
      if [[ $cfg_swap_kb =~ ^[0-9]+$ ]]; then swap_limit_kb=$cfg_swap_kb; fi
      if [[ $cfg_cpu =~ ^[0-9]+$ ]]; then cpu_limit_pct=$cfg_cpu; fi
    fi
  fi
}

max_cpu_usage_pct() {
  # Returns overall CPU utilization over ~1s window (any core peak is close to overall when busy)
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

wait_for_resources() {
  read -r mem_total mem_avail swap_total swap_free < <(awk '/MemTotal:/ {t=$2} /MemAvailable:/ {a=$2} /SwapTotal:/ {st=$2} /SwapFree:/ {sf=$2} END {print t, a, st, sf}' /proc/meminfo)
  if [[ -z "${mem_total:-}" || -z "${mem_avail:-}" || "$mem_total" -eq 0 ]]; then
    log_rate_limited_warn "warn_meminfo_missing" 300 "unable to read memory info; continuing"
    return 0
  fi
  mem_used_pct=$(( (100 * (mem_total - mem_avail)) / mem_total ))
  swap_used_pct=0
  swap_used_kb=0
  if [[ -n "${swap_total:-}" && "$swap_total" -gt 0 ]]; then
    swap_used_pct=$(( (100 * (swap_total - swap_free)) / swap_total ))
    swap_used_kb=$((swap_total - swap_free))
  fi

  max_cpu_pct=$(max_cpu_usage_pct || echo 0)
  if [[ -z "${max_cpu_pct:-}" ]]; then
    max_cpu_pct=0
  fi

  if (( mem_used_pct < mem_limit_pct && swap_used_pct < swap_limit_pct && swap_used_kb < swap_limit_kb && max_cpu_pct < cpu_limit_pct )); then
    return 0
  fi

  log_rate_limited_warn "resources_high" 60 "Resources high: Mem ${mem_used_pct}% (avail ${mem_avail}k/${mem_total}k, limit <${mem_limit_pct}), Swap ${swap_used_pct}% (${swap_used_kb}k used, limits <${swap_limit_pct}% and <${swap_limit_kb}k), Max CPU ${max_cpu_pct}% (limit <${cpu_limit_pct})."
  return 1
}

pipeline_already_running() {
  local target_station="$1"

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local pid="${line%% *}"
    pid="${pid//[[:space:]]/}"
    local rest="${line#* }"
    local comm="${rest%% *}"
    local cmd="${rest#* }"
    [[ -z "$pid" || "$pid" == "$line" ]] && continue
    [[ ! "$pid" =~ ^[0-9]+$ ]] && continue

    if pid_is_self_or_ancestor "$pid"; then
      continue
    fi
    case "$comm" in
      bash|sh|flock)
        ;;
      *)
        continue
        ;;
    esac
    [[ "$cmd" != *"guide_raw_to_corrected.sh"* ]] && continue
    # cron_run_logged.sh runs the cron command through a pipeline. Its logging
    # subshell is a sibling, not an ancestor, and its command line includes the
    # guide arguments. It is not another guide execution.
    [[ "$cmd" == *"/CRON_RUN_LOGGED/cron_run_logged.sh"* ]] && continue

    # Coincidence and self-trigger runs are separate flows. They can overlap;
    # duplicate runs within the same flow and station remain blocked.
    if ! command_matches_selected_flow "$cmd"; then
      continue
    fi

    if command_targets_station "$cmd" "$target_station"; then
      if is_tty; then
        log_info "Detected running guide_raw_to_corrected.sh for station ${target_station}: ${pid} ${cmd}"
      fi
      return 0
    fi
  done < <(ps -eo pid=,comm=,args=)
  return 1
}

command_matches_selected_flow() {
  local cmd="$1"
  local process_self_trigger=false
  local -a tokens=()
  # shellcheck disable=SC2206
  read -ra tokens <<< "$cmd"
  local token
  for token in "${tokens[@]}"; do
    if [[ "$token" == "--self-trigger" ]]; then
      process_self_trigger=true
      break
    fi
  done
  [[ "$process_self_trigger" == "$self_trigger_mode" ]]
}

station_value_matches_target() {
  local value="$1"
  local target="$2"
  local lowered="${value,,}"
  [[ -z "$value" ]] && return 1
  if [[ "$lowered" == "all" ]]; then
    return 0
  fi
  IFS=',' read -ra parts <<<"$value"
  local part cleaned
  for part in "${parts[@]}"; do
    cleaned="${part//[^0-9]/}"
    [[ -z "$cleaned" ]] && continue
    if (( 10#$cleaned == 10#$target )); then
      return 0
    fi
  done
  return 1
}

command_targets_station() {
  local cmd="$1"
  local target="$2"
  local expect_value=false
  local saw_station_arg=false
  local -a tokens=()
  # shellcheck disable=SC2206
  read -ra tokens <<< "$cmd"
  local token value
  for token in "${tokens[@]}"; do
    if $expect_value; then
      expect_value=false
      saw_station_arg=true
      [[ -z "$token" ]] && continue
      if station_value_matches_target "$token" "$target"; then
        return 0
      fi
      continue
    fi
    case "$token" in
      --station|-s)
        expect_value=true
        continue
        ;;
      --station=*)
        saw_station_arg=true
        value="${token#*=}"
        if station_value_matches_target "$value" "$target"; then
          return 0
        fi
        ;;
      -s*)
        saw_station_arg=true
        value="${token#-s}"
        if [[ -n "$value" ]] && station_value_matches_target "$value" "$target"; then
          return 0
        fi
        ;;
    esac
  done
  if [[ "$saw_station_arg" != true ]]; then
    # Default behavior processes all stations.
    return 0
  fi
  return 1
}


load_resource_limits

traffic_light_queue_init

iteration=1
if [[ "$run_anyway" != true ]]; then
  if ! acquire_argument_lock; then
    exit 0
  fi
else
  log_warn "--run-anyway set; skipping same-argument locking."
fi


while true; do
  refresh_execution_pairs_from_config
  if [[ ${#execution_pairs[@]} -eq 0 ]]; then
    log_rate_limited_global "no_enabled_pairs_${stations_requested[*]}_${tasks_requested[*]}" "$STEP1_IDLE_SLEEP_S" \
      "No enabled station-task pairs (${RUN_MATRIX_KEY}). Sleeping ${STEP1_IDLE_SLEEP_S}s..."
    sleep "$STEP1_IDLE_SLEEP_S"
    iteration=$((iteration + 1))
    continue
  fi
  sanitize_queue_file
  build_iteration_pairs_from_queue iteration_pairs
  for pair in "${iteration_pairs[@]}"; do
    IFS='-' read -r station task_id <<<"$pair"
    refresh_execution_pairs_from_config
    allowed=false
    for allowed_pair in "${execution_pairs[@]}"; do
      if [[ "$allowed_pair" == "$pair" ]]; then
        allowed=true
        break
      fi
    done
    if [[ "$allowed" != true ]]; then
      log_rate_limited "disabled_pair_${pair}" 300 "Skipping station $station task${task_id}: disabled by ${RUN_MATRIX_KEY}."
      continue
    fi
    task_index=$((task_id))
    if [[ "$self_trigger_mode" == true ]]; then
      task_script="${SELF_TRIGGER_TASK_SCRIPTS[$task_index]:-}"
      task_label="${SELF_TRIGGER_TASK_LABELS[$task_index]:-}"
    else
      task_script="${TASK_SCRIPTS[$task_index]:-}"
      task_label="${TASK_LABELS[$task_index]:-}"
    fi
    if [[ -z "$task_script" ]]; then
      log_warn "No script is registered for task ${task_id} in the selected flow. Skipping."
      continue
    fi
    rotate_pair_to_queue_end "$pair"
    if pipeline_already_running "$station"; then
      if is_tty; then
        log_warn "Station $station already handled by another guide_raw_to_corrected.sh; exiting to avoid waiting indefinitely."
      else
        log_rate_limited_global "station_busy_${station}" "$STEP1_ALREADY_RUNNING_LOG_S" \
          "Station $station already handled by another guide_raw_to_corrected.sh; exiting to avoid waiting indefinitely."
      fi
      exit 0
    fi
    if [[ ! -x "$task_script" ]]; then
      log_warn "Task script $task_script not found or not executable. Skipping."
      continue
    fi
    if ! wait_for_resources; then
      sleep "$STEP1_RESOURCE_BACKOFF_S"
      continue
    fi
    selection_order="${STEP1_SELECTION_ORDER_DEFAULT:-latest}"
    if [[ "$station" == "0" ]]; then
      selection_order="${STEP1_SELECTION_ORDER_MINGO00:-oldest}"
    fi
    if [[ "$self_trigger_mode" == true ]]; then
      log_info "Running station $station self-trigger task${task_id} (${task_label}) [selection_order=${selection_order}] ..."
    else
      log_info "Running station $station task${task_id} (${task_label}) [selection_order=${selection_order}] ..."
    fi

    if DATAFLOW_STEP1_SELECTION_ORDER="${selection_order}" python3 -u "$task_script" "$station" "${TASK_VERBOSE_ARGS[@]}"; then
      if [[ "$self_trigger_mode" == true ]]; then
        log_info "Completed station $station self-trigger task${task_id} (${task_label})."
      else
        log_info "Completed station $station task${task_id} (${task_label})."
      fi
      log_info "----------"
    else
      task_rc=$?
      log_warn "Task $(basename "$task_script") failed for station $station with exit_code=${task_rc}; continuing to next pair."
      continue
    fi
  done
  iteration=$((iteration + 1))
done
