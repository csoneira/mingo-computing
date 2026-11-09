#!/usr/bin/env bash

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
# Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_step.sh
# Purpose: Schedule or execute STEP_1 through STEP_10 and explicit STEP_FINAL requests.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_step.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run_step.sh <step_number|all|final|from> [options]
  run_step.sh from <step_number> [options]
  run_step.sh -c|--continuous [options]

Options:
  --no-plots           Skip plot generation
  --plot-only          Only generate plots from existing outputs
  --loop               Repeat the selected run in a loop
  --force              Recompute even if SIM_RUN exists
  --debug              Keep full step stdout/stderr (default in continuous mode is concise logs)
  -c, --continuous     Run "all" in a loop with a lock to prevent overlaps (implies --no-plots)
  -fc, --force-continuous  Terminate the active continuous run and start a new one
  -h, --help           Show this help and exit

Notes:
  -c/--continuous implies "all", "--loop", and "--no-plots" and uses a runtime lock.
  --force-continuous is only valid with -c/--continuous.
  Set RUN_STEP_OBLITERATE_UNINTERESTING_STEP1_LINES=1 to auto-close active
  step_1 lines that have no pending rows compatible with fixed STEP_2 z_positions.
  Set RUN_STEP_AUTOCLEAN_CONFLICTS=0 to disable automatic stale INTERSTEPS cleanup.
EOF
}

RUN_STEP_STRUCTURED_LOG_PATH=""
RUN_STEP_STRUCTURED_LOGGER="run_step"

emit_structured_log() {
  local level="$1"
  shift
  local message="$*"
  if [[ -z "$RUN_STEP_STRUCTURED_LOG_PATH" ]]; then
    return 0
  fi
  if ! declare -F sim_structured_log_emit >/dev/null 2>&1; then
    return 0
  fi
  sim_structured_log_emit "$RUN_STEP_STRUCTURED_LOG_PATH" "$RUN_STEP_STRUCTURED_LOGGER" "$level" "$message" || true
}

log_ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_info() {
  printf '%s [INFO] [run_step] %s\n' "$(log_ts)" "$*"
  emit_structured_log "INFO" "$*"
}

log_warn() {
  printf '%s [WARN] [run_step] %s\n' "$(log_ts)" "$*" >&2
  emit_structured_log "WARN" "$*"
}

log_error() {
  printf '%s [ERROR] [run_step] %s\n' "$(log_ts)" "$*" >&2
  emit_structured_log "ERROR" "$*"
}

simulation_time_csv_path() {
  printf '%s/PLOTTERS/EXECUTION/SIMULATION_TIME/simulation_execution_times.csv' "$DT"
}

ensure_simulation_time_csv() {
  local csv_path
  local header
  local current_header
  local first_line
  local tmp_path
  local backup
  csv_path="$(simulation_time_csv_path)"
  header='exec_time_s,step,timestamp_utc'
  mkdir -p "$(dirname "$csv_path")"
  if [[ ! -f "$csv_path" ]]; then
    printf '%s\n' "$header" > "$csv_path"
    return 0
  fi
  current_header="$(head -n 1 "$csv_path" 2>/dev/null || true)"
  if [[ "$current_header" != "$header" ]]; then
    first_line="$current_header"
    if [[ "$first_line" =~ ^[0-9]+([.][0-9]+)?,[0-9]+,[0-9]{4}-[0-9]{2}-[0-9]{2}T ]]; then
      tmp_path="${csv_path}.tmp.$$"
      {
        printf '%s\n' "$header"
        cat "$csv_path"
      } > "$tmp_path"
      mv "$tmp_path" "$csv_path"
      log_info "simulation timing CSV upgraded from legacy headerless format: $csv_path"
    else
      # unknown mismatch detected; keep existing file intact to preserve history
      log_warn "simulation timing CSV header mismatch (found='$current_header' expected='$header'); preserving existing file"
    fi
  fi
}

append_simulation_time_row() {
  local elapsed="$1"
  local step="$2"
  local csv_path
  csv_path="$(simulation_time_csv_path)"
  ensure_simulation_time_csv
  printf '%s,%s,%s\n' \
    "$elapsed" \
    "$step" \
    "$(log_ts)" >> "$csv_path"
}

elapsed_seconds_between() {
  local start_ts="$1"
  local end_ts="$2"
  LC_ALL=C awk -v s="$start_ts" -v e="$end_ts" 'BEGIN{d=e-s; if (d < 0) d=0; printf "%.6f", d}'
}

NO_PLOTS=""
PLOT_ONLY=""
FINAL_STEP=""
LOOP=""
FORCE=""
CONTINUOUS=""
FORCE_CONTINUOUS=""
DEBUG=""
QUIET_CONTINUOUS=""
ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "-h" || "$arg" == "--help" ]]; then
    usage
    exit 0
  elif [[ "$arg" == "--no-plots" ]]; then
    NO_PLOTS="--no-plots"
  elif [[ "$arg" == "--plot-only" ]]; then
    PLOT_ONLY="--plot-only"
  elif [[ "$arg" == "--final" ]]; then
    FINAL_STEP="--final"
  elif [[ "$arg" == "--loop" ]]; then
    LOOP="1"
  elif [[ "$arg" == "--force" ]]; then
    FORCE="--force"
  elif [[ "$arg" == "--debug" ]]; then
    DEBUG="1"
  elif [[ "$arg" == "-c" || "$arg" == "--continuous" ]]; then
    CONTINUOUS="1"
  elif [[ "$arg" == "-fc" || "$arg" == "--force-continuous" ]]; then
    FORCE_CONTINUOUS="1"
  else
    ARGS+=("$arg")
  fi
done

if [[ -n "$FORCE_CONTINUOUS" && -z "$CONTINUOUS" ]]; then
  log_error "--force-continuous requires -c/--continuous."
  usage
  exit 1
fi

if [[ -z "$CONTINUOUS" && ${#ARGS[@]} -lt 1 ]]; then
  usage
  exit 1
fi

if [[ -n "$CONTINUOUS" ]]; then
  STEP="all"
  LOOP="1"
  NO_PLOTS="--no-plots"
else
  STEP="${ARGS[0]}"
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -d "${SCRIPT_DIR}/MASTER_STEPS" && -d "${SCRIPT_DIR}/SIMULATION_OUTPUTS/INTERSTEPS" ]]; then
  DT="${SCRIPT_DIR}"
else
  DT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi
ROOT_RUNTIME_DIR="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME"
SIM_STRUCTURED_LOGS_ENABLED="${SIM_STRUCTURED_LOGS_ENABLED:-1}"
SIM_LOG_HELPER="$DT/ORCHESTRATOR/helpers/sim_structured_logging.sh"
if [[ -f "$SIM_LOG_HELPER" ]]; then
  # shellcheck disable=SC1090
  source "$SIM_LOG_HELPER"
fi
RUN_STEP_STRUCTURED_LOG_PATH="${ROOT_RUNTIME_DIR}/CRON_LOGS/SIMULATION/STRUCTURED/run_step.jsonl"
# lock used to serialize standalone final-step executions (cron or manual).
FINAL_LOCK="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_final.lock"
RUN_STEP_STATE_DIR="${RUN_STEP_STATE_DIR:-${ROOT_RUNTIME_DIR}/STATE/run_step}"
RUN_STEP_LOG_DIR="${RUN_STEP_LOG_DIR:-${ROOT_RUNTIME_DIR}/CRON_LOGS/SIMULATION/RUN_STEP}"
RUN_STEP_LOCK_DIR="${RUN_STEP_LOCK_DIR:-${ROOT_RUNTIME_DIR}/LOCKS/simulation/run_step_continuous.lock}"
WORK_CACHE_PATH="${RUN_STEP_STATE_DIR}/work_cache.csv"
WORK_STATE_PATH="${RUN_STEP_STATE_DIR}/work_state.csv"
WORK_STUCK_LINES_PATH="${RUN_STEP_STATE_DIR}/work_stuck_lines.csv"
WORK_BROKEN_RUNS_PATH="${RUN_STEP_STATE_DIR}/work_broken_runs.csv"
STRICT_LINE_CLOSURE="${RUN_STEP_STRICT_LINE_CLOSURE:-1}"
STEP1_STUCK_AGE_S="${RUN_STEP_STEP1_STUCK_AGE_S:-1800}"
STEP1_BLOCK_LOG_INTERVAL_S="${RUN_STEP_STEP1_BLOCK_LOG_INTERVAL_S:-300}"
OBLITERATE_UNINTERESTING_STEP1_LINES="${RUN_STEP_OBLITERATE_UNINTERESTING_STEP1_LINES:-0}"
# Opt-out behavior: when set to 0 the scheduler will NOT auto-bootstrap missing
# upstream STEP_2 SIM_RUNs from the param_mesh. Default: enabled (1).
RUN_STEP_AUTO_BOOTSTRAP_UPSTREAM="${RUN_STEP_AUTO_BOOTSTRAP_UPSTREAM:-1}"
# By default, do not enforce/emit param_mesh upstream consistency warnings.
# Set to 1 to enable the checker output in the run-step runtime state directory.
RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY="${RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY:-0}"
# Auto-clean stale/broken conflicting SIM_RUN directories before scheduling work.
RUN_STEP_AUTOCLEAN_CONFLICTS="${RUN_STEP_AUTOCLEAN_CONFLICTS:-1}"
RUN_STEP_AUTOCLEAN_MIN_AGE_S="${RUN_STEP_AUTOCLEAN_MIN_AGE_S:-300}"
RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH="${RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH:-1}"
RUN_STEP_INCLUDE_FINAL_IN_ALL="${RUN_STEP_INCLUDE_FINAL_IN_ALL:-1}"
RUN_STEP_STUCK_ALERTS_ENABLED="${RUN_STEP_STUCK_ALERTS_ENABLED:-1}"
RUN_STEP_STUCK_ALERT_MIN_CYCLES="${RUN_STEP_STUCK_ALERT_MIN_CYCLES:-3}"
RUN_STEP_STUCK_ALERT_REPEAT_CYCLES="${RUN_STEP_STUCK_ALERT_REPEAT_CYCLES:-60}"
RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S="${RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S:-45}"
RUN_STEP_STUCK_ALERT_STATE_PATH="${RUN_STEP_STATE_DIR}/stuck_alert_state.json"
LAST_STEP1_BLOCK_LOG_EPOCH=0
if [[ "$SIM_STRUCTURED_LOGS_ENABLED" != "0" && "$SIM_STRUCTURED_LOGS_ENABLED" != "1" ]]; then
  SIM_STRUCTURED_LOGS_ENABLED="1"
fi
if [[ "$STRICT_LINE_CLOSURE" != "0" && "$STRICT_LINE_CLOSURE" != "1" ]]; then
  STRICT_LINE_CLOSURE="1"
fi
if ! [[ "$STEP1_STUCK_AGE_S" =~ ^[0-9]+$ ]]; then
  STEP1_STUCK_AGE_S="1800"
fi
if ! [[ "$STEP1_BLOCK_LOG_INTERVAL_S" =~ ^[0-9]+$ ]]; then
  STEP1_BLOCK_LOG_INTERVAL_S="300"
fi
if [[ "$OBLITERATE_UNINTERESTING_STEP1_LINES" != "0" && "$OBLITERATE_UNINTERESTING_STEP1_LINES" != "1" && "$OBLITERATE_UNINTERESTING_STEP1_LINES" != "apply" ]]; then
  OBLITERATE_UNINTERESTING_STEP1_LINES="0"
fi
if [[ "$RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY" != "0" && "$RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY" != "1" ]]; then
  RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY="0"
fi
if [[ "$RUN_STEP_AUTOCLEAN_CONFLICTS" != "0" && "$RUN_STEP_AUTOCLEAN_CONFLICTS" != "1" ]]; then
  RUN_STEP_AUTOCLEAN_CONFLICTS="1"
fi
if [[ "$RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH" != "0" && "$RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH" != "1" ]]; then
  RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH="1"
fi
if [[ "$RUN_STEP_INCLUDE_FINAL_IN_ALL" != "0" && "$RUN_STEP_INCLUDE_FINAL_IN_ALL" != "1" ]]; then
  RUN_STEP_INCLUDE_FINAL_IN_ALL="1"
fi
if [[ "$RUN_STEP_STUCK_ALERTS_ENABLED" != "0" && "$RUN_STEP_STUCK_ALERTS_ENABLED" != "1" ]]; then
  RUN_STEP_STUCK_ALERTS_ENABLED="1"
fi
if ! [[ "$RUN_STEP_AUTOCLEAN_MIN_AGE_S" =~ ^[0-9]+$ ]]; then
  RUN_STEP_AUTOCLEAN_MIN_AGE_S="300"
fi
if ! [[ "$RUN_STEP_STUCK_ALERT_MIN_CYCLES" =~ ^[0-9]+$ ]]; then
  RUN_STEP_STUCK_ALERT_MIN_CYCLES="3"
fi
if ! [[ "$RUN_STEP_STUCK_ALERT_REPEAT_CYCLES" =~ ^[0-9]+$ ]]; then
  RUN_STEP_STUCK_ALERT_REPEAT_CYCLES="60"
fi
if ! [[ "$RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S" =~ ^[0-9]+$ ]]; then
  RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S="45"
fi
mkdir -p "$RUN_STEP_STATE_DIR" "$(dirname "$RUN_STEP_LOCK_DIR")"
if [[ -n "$CONTINUOUS" && -z "$DEBUG" ]]; then
  QUIET_CONTINUOUS="1"
fi

if [[ -n "$NO_PLOTS" && -n "$PLOT_ONLY" ]]; then
  log_error "--no-plots and --plot-only cannot be used together."
  exit 1
fi

if [[ -n "$CONTINUOUS" ]]; then
  LOCK_DIR="$RUN_STEP_LOCK_DIR"
  PID_FILE="$LOCK_DIR/pid"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if [[ -n "$FORCE_CONTINUOUS" ]]; then
      if [[ -f "$PID_FILE" ]]; then
        LOCK_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
          CMDLINE="$(tr '\0' ' ' < "/proc/$LOCK_PID/cmdline" 2>/dev/null || true)"
          if [[ "$CMDLINE" == *"run_step.sh"* ]]; then
            kill "$LOCK_PID" 2>/dev/null || true
            sleep 1
            if kill -0 "$LOCK_PID" 2>/dev/null; then
              kill -9 "$LOCK_PID" 2>/dev/null || true
            fi
          fi
        fi
      fi
      rm -rf "$LOCK_DIR"
      mkdir "$LOCK_DIR"
    else
      if [[ -f "$PID_FILE" ]]; then
        LOCK_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
          CMDLINE="$(tr '\0' ' ' < "/proc/$LOCK_PID/cmdline" 2>/dev/null || true)"
          if [[ "$CMDLINE" == *"run_step.sh"* ]]; then
            LOCK_AGE_S="$(ps -o etimes= -p "$LOCK_PID" 2>/dev/null | tr -d ' ' || true)"
            [[ -z "$LOCK_AGE_S" ]] && LOCK_AGE_S="unknown"
            log_warn "Continuous operation already running; pid=$LOCK_PID etimes_s=$LOCK_AGE_S lock_dir=$LOCK_DIR pid_file=$PID_FILE cmdline=$CMDLINE"
            exit 0
          fi
        fi
      fi
      log_warn "Stale continuous lock detected; removing lock_dir=$LOCK_DIR pid_file=$PID_FILE and continuing"
      rm -rf "$LOCK_DIR"
      mkdir "$LOCK_DIR"
    fi
  fi
  echo "$$" > "$PID_FILE"
  cleanup_continuous_lock() {
    rm -f "$PID_FILE" 2>/dev/null || true
    rmdir "$LOCK_DIR" 2>/dev/null || true
  }
  terminate_direct_children() {
    pkill -TERM -P "$$" 2>/dev/null || true
  }
  handle_termination_signal() {
    local code="$1"
    terminate_direct_children
    cleanup_continuous_lock
    exit "$code"
  }
  trap cleanup_continuous_lock EXIT
  trap 'handle_termination_signal 130' INT
  trap 'handle_termination_signal 143' TERM
fi

run_step() {
  local step="$1"
  local -a cmd
  local tmp_log
  local failure_log
  local last_error
  local rc
  case "$step" in
    1) cmd=(python3 "$DT/MASTER_STEPS/STEP_1/step_1_blank_to_generated.py" --config "$DT/MASTER_STEPS/STEP_1/config_step_1_physics.yaml") ;;
    2)
      # Use the fixed-geometry physics config for STEP_2. Per owner request,
      # automatic switching to a param-mesh physics YAML has been removed.
      cmd=(python3 "$DT/MASTER_STEPS/STEP_2/step_2_generated_to_crossing.py" --config "$DT/MASTER_STEPS/STEP_2/config_step_2_physics.yaml" --runtime-config "$DT/MASTER_STEPS/STEP_2/config_step_2_runtime.yaml")
      ;;
    3) cmd=(python3 "$DT/MASTER_STEPS/STEP_3/step_3_crossing_to_hit.py" --config "$DT/MASTER_STEPS/STEP_3/config_step_3_physics.yaml") ;;
    4) cmd=(python3 "$DT/MASTER_STEPS/STEP_4/step_4_hit_to_measured.py" --config "$DT/MASTER_STEPS/STEP_4/config_step_4_physics.yaml") ;;
    5) cmd=(python3 "$DT/MASTER_STEPS/STEP_5/step_5_measured_to_triggered.py" --config "$DT/MASTER_STEPS/STEP_5/config_step_5_physics.yaml") ;;
    6) cmd=(python3 "$DT/MASTER_STEPS/STEP_6/step_6_triggered_to_timing.py" --config "$DT/MASTER_STEPS/STEP_6/config_step_6_physics.yaml") ;;
    7) cmd=(python3 "$DT/MASTER_STEPS/STEP_7/step_7_timing_to_uncalibrated.py" --config "$DT/MASTER_STEPS/STEP_7/config_step_7_physics.yaml") ;;
    8) cmd=(python3 "$DT/MASTER_STEPS/STEP_8/step_8_uncalibrated_to_threshold.py" --config "$DT/MASTER_STEPS/STEP_8/config_step_8_physics.yaml") ;;
    9) cmd=(python3 "$DT/MASTER_STEPS/STEP_9/step_9_threshold_to_trigger.py" --config "$DT/MASTER_STEPS/STEP_9/config_step_9_physics.yaml") ;;
    10) cmd=(python3 "$DT/MASTER_STEPS/STEP_10/step_10_triggered_to_jitter.py" --config "$DT/MASTER_STEPS/STEP_10/config_step_10_physics.yaml") ;;
    final)
      # hold FINAL_LOCK to prevent simultaneous formatting by cron or
      # another run_step invocation.
      cmd=(flock -n "$FINAL_LOCK" python3 "$DT/MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py" --config "$DT/MASTER_STEPS/STEP_FINAL/config_step_final_physics.yaml")
      ;;
    *)
      log_error "Unknown step: $step"
      exit 1
      ;;
  esac
  [[ -n "$NO_PLOTS" ]] && cmd+=("$NO_PLOTS")
  [[ -n "$PLOT_ONLY" ]] && cmd+=("$PLOT_ONLY")
  [[ -n "$FORCE" ]] && cmd+=("$FORCE")

  if [[ -z "$QUIET_CONTINUOUS" ]]; then
    "${cmd[@]}"
    return $?
  fi

  # Successful continuous runs are intentionally silent. Create the capture
  # directory only while it is needed, then remove it if no failure remains.
  mkdir -p "$RUN_STEP_LOG_DIR"
  tmp_log="$(mktemp "${RUN_STEP_LOG_DIR}/step_${step}.XXXXXX.log")"
  if "${cmd[@]}" >"$tmp_log" 2>&1; then
    rm -f "$tmp_log"
    rmdir "$RUN_STEP_LOG_DIR" 2>/dev/null || true
    return 0
  else
    rc=$?
  fi
  failure_log="${RUN_STEP_LOG_DIR}/last_step_${step}.log"
  cp "$tmp_log" "$failure_log" 2>/dev/null || true
  last_error="$(awk 'NF {line=$0} END {print line}' "$tmp_log" 2>/dev/null || true)"
  if [[ -z "$last_error" ]]; then
    last_error="(no output from step process)"
  fi
  log_warn "step=$step failed rc=$rc; last_line=\"$last_error\" (full log: $failure_log, use --debug for verbose output)"
  rm -f "$tmp_log"
  return "$rc"
}

step_output_dir_for_step() {
  case "$1" in
    1) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_1_TO_2' "$DT" ;;
    2) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_2_TO_3' "$DT" ;;
    3) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_3_TO_4' "$DT" ;;
    4) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_4_TO_5' "$DT" ;;
    5) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_5_TO_6' "$DT" ;;
    6) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_6_TO_7' "$DT" ;;
    7) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_7_TO_8' "$DT" ;;
    8) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_8_TO_9' "$DT" ;;
    9) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_9_TO_10' "$DT" ;;
    10) printf '%s/SIMULATION_OUTPUTS/INTERSTEPS/STEP_10_TO_FINAL' "$DT" ;;
    *) return 1 ;;
  esac
}

count_sim_run_dirs() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    printf '0\n'
    return 0
  fi
  find "$dir" -mindepth 1 -maxdepth 1 -type d -name 'SIM_RUN_*' | wc -l | tr -d ' '
  printf '\n'
}

step_has_fallback_work() {
  local step="$1"
  local upstream_dir

  if [[ "$step" -eq 1 ]]; then
    local mesh_path="$DT/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"
    if [[ ! -f "$mesh_path" ]]; then
      return 1
    fi
    awk -F, '
      NR==1 {
        for (i=1; i<=NF; i++) {
          if ($i=="done") done_col=i
        }
        next
      }
      NR>1 {
        done_val = (done_col ? $done_col : "0")
        gsub(/\r/, "", done_val)
        if ((done_val + 0) != 1) {
          found = 1
          exit 0
        }
      }
      END { exit(found ? 0 : 1) }
    ' "$mesh_path"
    return $?
  fi

  upstream_dir="$(step_output_dir_for_step "$((step - 1))")" || return 1
  [[ "$(count_sim_run_dirs "$upstream_dir")" -gt 0 ]]
}

step_has_cached_work() {
  local step="$1"
  local has_work
  if [[ ! -f "$WORK_CACHE_PATH" ]]; then
    step_has_fallback_work "$step"
    return $?
  fi
  has_work="$(awk -F, -v step="$step" 'NR>1 && $1==step {print $2; exit}' "$WORK_CACHE_PATH")"
  has_work="${has_work//$'\r'/}"
  if [[ -z "$has_work" ]]; then
    step_has_fallback_work "$step"
    return $?
  fi
  [[ "$has_work" == "1" ]]
}

work_state_value() {
  local key="$1"
  local default_value="${2:-}"
  local value=""
  if [[ -f "$WORK_STATE_PATH" ]]; then
    value="$(awk -F, -v key="$key" 'NR>1 && $1==key {print $2; exit}' "$WORK_STATE_PATH")"
  fi
  value="${value//$'\r'/}"
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default_value"
  else
    printf '%s\n' "$value"
  fi
}

step1_new_lines_allowed() {
  local allowed
  if [[ "$STRICT_LINE_CLOSURE" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "$WORK_STATE_PATH" ]]; then
    # Fail closed: if we cannot inspect active lines, do not open new ones.
    return 1
  fi
  allowed="$(work_state_value "step1_new_lines_allowed" "0")"
  [[ "$allowed" == "1" ]]
}

maybe_log_step1_blocked() {
  local now_epoch
  local active_lines
  local unopened_lines
  local stuck_lines
  local oldest_age
  local broken_runs
  now_epoch="$(date +%s)"
  if (( now_epoch - LAST_STEP1_BLOCK_LOG_EPOCH < STEP1_BLOCK_LOG_INTERVAL_S )); then
    return 0
  fi
  LAST_STEP1_BLOCK_LOG_EPOCH="$now_epoch"
  active_lines="$(work_state_value "active_open_step1_lines" "unknown")"
  unopened_lines="$(work_state_value "unopened_step1_lines" "unknown")"
  stuck_lines="$(work_state_value "stuck_step1_lines" "unknown")"
  oldest_age="$(work_state_value "oldest_active_step1_age_s" "unknown")"
  broken_runs="$(work_state_value "broken_runs" "unknown")"
  log_warn "step=1 status=blocked reason=active-lines strict_line_closure=$STRICT_LINE_CLOSURE active_open_lines=$active_lines unopened_lines=$unopened_lines stuck_lines=$stuck_lines oldest_age_s=$oldest_age broken_runs=$broken_runs"
  if [[ "$stuck_lines" != "0" ]]; then
    log_warn "step=1 stuck-line report path=$WORK_STUCK_LINES_PATH"
  fi
  if [[ "$broken_runs" != "0" ]]; then
    log_warn "broken SIM_RUN report path=$WORK_BROKEN_RUNS_PATH"
  fi
}

obliterate_uninteresting_step1_lines_if_needed() {
  local helper
  local output
  local rc
  # Require explicit 'apply' to perform destructive edits.  '1' runs dry-run only.
  if [[ "$OBLITERATE_UNINTERESTING_STEP1_LINES" == "0" ]]; then
    return 3
  fi
  helper="$DT/ORCHESTRATOR/maintenance/sim_maintenance.py"
  if [[ ! -f "$helper" ]]; then
    log_warn "step=1 line-obliterate helper missing: $helper"
    return 2
  fi
  if [[ "$OBLITERATE_UNINTERESTING_STEP1_LINES" == "apply" ]]; then
    cmd=(python3 "$helper" close-unproductive-lines --apply)
  else
    cmd=(python3 "$helper" close-unproductive-lines)
  fi
  if output="$("${cmd[@]}" 2>&1)"; then
    rc=0
  else
    rc=$?
    if [[ "$rc" -eq 3 ]]; then
      if [[ -n "$output" ]]; then
        log_info "step=1 line-obliterate $output"
      fi
      return 3
    fi
    if [[ -n "$output" ]]; then
      log_warn "step=1 line-obliterate failed rc=$rc output=$output"
    else
      log_warn "step=1 line-obliterate failed rc=$rc"
    fi
    return 2
  fi
  if [[ -n "$output" ]]; then
    log_info "step=1 line-obliterate $output"
  fi
  return 0
}

refresh_step_work_cache() {
  local mesh_path="$DT/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv"
  local intersteps_dir="$DT/SIMULATION_OUTPUTS/INTERSTEPS"
  local helper="$DT/ORCHESTRATOR/helpers/refresh_step_work_cache.py"
  if [[ ! -f "$helper" ]]; then
    log_warn "work cache refresh skipped (missing helper: $helper)"
    return 1
  fi
  python3 "$helper" \
    "$mesh_path" \
    "$intersteps_dir" \
    "$WORK_CACHE_PATH" \
    "$WORK_STATE_PATH" \
    "$WORK_STUCK_LINES_PATH" \
    "$WORK_BROKEN_RUNS_PATH" \
    "$STRICT_LINE_CLOSURE" \
    "$STEP1_STUCK_AGE_S"
}

refresh_work_cache_or_disable() {
  if refresh_step_work_cache; then
    if [[ -n "$DEBUG" ]]; then
      log_info "work cache refreshed: cache=$WORK_CACHE_PATH state=$WORK_STATE_PATH stuck=$WORK_STUCK_LINES_PATH broken=$WORK_BROKEN_RUNS_PATH"
    fi

    # Optional checker (disabled by default): detects missing upstream SIM_RUNs
    # for pending param_mesh rows. It is diagnostic-only and does not modify data.
    if [[ "$RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY" == "1" ]]; then
      if python3 "$DT/ORCHESTRATOR/diagnostics/check_param_mesh_consistency.py" --mesh "$DT/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1/param_mesh.csv" --intersteps "$DT/SIMULATION_OUTPUTS/INTERSTEPS" --step 3 >"${RUN_STEP_STATE_DIR}/param_mesh_consistency.log" 2>&1; then
        if [[ -n "$DEBUG" ]]; then
          log_info "param_mesh consistency: OK"
        fi
      else
        log_warn "param_mesh consistency check found missing upstream SIM_RUNs; see ${RUN_STEP_STATE_DIR}/param_mesh_consistency.log"
      fi
    elif [[ -n "$DEBUG" ]]; then
      log_info "param_mesh consistency check skipped (RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY=0)"
    fi

    notify_stuck_line_alert_if_needed
    return 0
  fi
  log_warn "failed to refresh work cache; continuing without cache/state"
  rm -f "$WORK_CACHE_PATH" "$WORK_STATE_PATH" "$WORK_STUCK_LINES_PATH" "$WORK_BROKEN_RUNS_PATH" 2>/dev/null || true
  return 0
}

notify_stuck_line_alert_if_needed() {
  local helper
  local output

  if [[ "$RUN_STEP_STUCK_ALERTS_ENABLED" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "$WORK_STATE_PATH" ]]; then
    return 0
  fi

  helper="$DT/ORCHESTRATOR/notifications/notify_stuck_lines.py"
  if [[ ! -f "$helper" ]]; then
    log_warn "stuck alert skipped (missing helper: $helper)"
    return 0
  fi

  if output="$(python3 "$helper" \
    --state-csv "$WORK_STATE_PATH" \
    --stuck-csv "$WORK_STUCK_LINES_PATH" \
    --alert-state-file "$RUN_STEP_STUCK_ALERT_STATE_PATH" \
    --min-cycles "$RUN_STEP_STUCK_ALERT_MIN_CYCLES" \
    --repeat-cycles "$RUN_STEP_STUCK_ALERT_REPEAT_CYCLES" \
    --min-observation-interval-s "$RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S" \
    --enabled "$RUN_STEP_STUCK_ALERTS_ENABLED" \
    --source "run_step" 2>&1)"; then
    case "$output" in
      *status=sent*|*status=send_failed*)
        log_warn "stuck alert $output"
        ;;
      *status=missing_token*|*status=missing_chat_ids*)
        if [[ -n "$DEBUG" ]]; then
          log_warn "stuck alert $output"
        fi
        ;;
      *)
        if [[ -n "$DEBUG" ]]; then
          log_info "stuck alert $output"
        fi
        ;;
    esac
    return 0
  fi

  log_warn "stuck alert helper failed output=$output"
  return 0
}

autoclean_conflicting_runs() {
  local maintenance_cli
  local -a cmd
  local output
  local rc
  local summary

  if [[ "$RUN_STEP_AUTOCLEAN_CONFLICTS" != "1" ]]; then
    return 0
  fi
  if [[ -n "$PLOT_ONLY" ]]; then
    return 0
  fi

  maintenance_cli="$DT/ORCHESTRATOR/maintenance/sim_maintenance.py"
  if [[ ! -f "$maintenance_cli" ]]; then
    log_warn "autoclean skipped (missing maintenance CLI: $maintenance_cli)"
    return 0
  fi

  cmd=(python3 "$maintenance_cli" sanitize-runs --apply --min-age-seconds "$RUN_STEP_AUTOCLEAN_MIN_AGE_S")
  if [[ "$RUN_STEP_AUTOCLEAN_DELETE_NO_MESH_MATCH" == "1" ]]; then
    cmd+=(--delete-no-mesh-match)
  fi

  if output="$("${cmd[@]}" 2>&1)"; then
    summary="$(printf '%s\n' "$output" | awk '/Summary:/ {line=$0} END{print line}')"
    if [[ -z "$summary" ]]; then
      summary="autoclean completed"
    fi
    if [[ -n "$DEBUG" ]]; then
      log_info "$summary"
    else
      log_info "$summary"
    fi
    return 0
  fi

  rc=$?
  summary="$(printf '%s\n' "$output" | awk '/Summary:/ {line=$0} END{print line}')"
  if [[ -n "$summary" ]]; then
    log_warn "autoclean failed rc=$rc ($summary)"
  else
    log_warn "autoclean failed rc=$rc"
  fi
  return 0
}

run_step_with_progress() {
  local step="$1"
  local output_dir
  local before_count
  local after_count
  local start_epoch
  local end_epoch
  local elapsed
  local elapsed_log
  local rc
  output_dir="$(step_output_dir_for_step "$step")"
  before_count="$(count_sim_run_dirs "$output_dir")"
  start_epoch=$(date +%s.%N)
  if run_step "$step"; then
    rc=0
  else
    rc=$?
  fi
  if [[ "$rc" -ne 0 ]]; then
    end_epoch=$(date +%s.%N)
    elapsed="$(elapsed_seconds_between "$start_epoch" "$end_epoch")"
    elapsed_log="$(LC_ALL=C awk -v d="$elapsed" 'BEGIN{printf "%.3f", d}')"
    after_count="$(count_sim_run_dirs "$output_dir")"
    append_simulation_time_row "$elapsed" "$step" || true
    log_warn "step=$step status=failed rc=$rc dirs=${before_count}->${after_count} elapsed_s=$elapsed_log"
    return 2
  fi
  end_epoch=$(date +%s.%N)
  elapsed="$(elapsed_seconds_between "$start_epoch" "$end_epoch")"
  elapsed_log="$(LC_ALL=C awk -v d="$elapsed" 'BEGIN{printf "%.3f", d}')"
  append_simulation_time_row "$elapsed" "$step" || true
  after_count="$(count_sim_run_dirs "$output_dir")"
  if [[ "$after_count" -gt "$before_count" ]]; then
    log_info "step=$step status=progress dirs=${before_count}->${after_count} elapsed_s=$elapsed_log"
    return 0
  fi
  if [[ -n "$DEBUG" ]]; then
    log_info "step=$step status=noop dirs=${before_count}->${after_count} elapsed_s=$elapsed_log"
  fi
  return 1
}

while true; do
  cycle_start_epoch=$(date +%s)
  cycle_end_epoch="$cycle_start_epoch"
  step_failed="0"

  if [[ -n "$CONTINUOUS" ]]; then
    log_info "continuous loop start"
  fi
  case "$STEP" in
    all)
      autoclean_conflicting_runs
      failed_steps=0
      completed_lines=0
      max_completed_lines="${RUN_STEP_MAX_COMPLETED_LINES:-0}"
      if [[ ! "$max_completed_lines" =~ ^[0-9]+$ ]]; then
        log_warn "RUN_STEP_MAX_COMPLETED_LINES must be a nonnegative integer"
        exit 2
      fi
      while true; do
        refresh_work_cache_or_disable
        progressed=0
        attempted=0

        # Strictly prioritize closing existing lines:
        # try highest pending step first (10 -> 1), and stop after first progress.
        for step in $(seq 10 -1 1); do
          if ! step_has_cached_work "$step"; then
            if [[ -n "$DEBUG" ]]; then
              log_info "step=$step status=cache-skip"
            fi
            continue
          fi

          if [[ "$step" -eq 1 ]] && [[ "$STRICT_LINE_CLOSURE" == "1" ]]; then
            if ! step1_new_lines_allowed; then
              attempted=1
              maybe_log_step1_blocked
              if obliterate_uninteresting_step1_lines_if_needed; then
                refresh_work_cache_or_disable
                if step1_new_lines_allowed; then
                  log_info "step=1 status=unblocked reason=obliterated-non-interest-line"
                else
                  if [[ -n "$DEBUG" ]]; then
                    log_info "step=1 status=cache-blocked strict_line_closure=$STRICT_LINE_CLOSURE"
                  fi
                  continue
                fi
              else
                obliterate_rc=$?
                if [[ -n "$DEBUG" ]]; then
                  if [[ "$obliterate_rc" -eq 3 ]]; then
                    log_info "step=1 status=cache-blocked strict_line_closure=$STRICT_LINE_CLOSURE"
                  else
                    log_info "step=1 status=cache-blocked strict_line_closure=$STRICT_LINE_CLOSURE obliterate_rc=$obliterate_rc"
                  fi
                fi
                continue
              fi
            fi
          fi

          attempted=1
          if run_step_with_progress "$step"; then
            progressed=1
            break
          fi

          rc=$?
          if [[ "$rc" -eq 2 ]]; then
            log_warn "step=$step failed; continuing"
            failed_steps=$((failed_steps + 1))
          fi
        done

        # Yield to the outer controller's consumed-intermediate cleanup regularly.
        # A line is complete only after STEP_10 produced a new output directory.
        if [[ "$progressed" -eq 1 && "$step" -eq 10 ]]; then
          completed_lines=$((completed_lines + 1))
          if (( max_completed_lines > 0 && completed_lines >= max_completed_lines )); then
            log_info "batch status=complete completed_lines=$completed_lines; yielding for housekeeping"
            break
          fi
        fi

        # End the "all" cycle when there is no pending cached work,
        # or when no step produced progress in this pass.
        if [[ "$attempted" -eq 0 || "$progressed" -eq 0 ]]; then
          break
        fi
      done
      cycle_end_epoch=$(date +%s)
      cycle_elapsed=$((cycle_end_epoch - cycle_start_epoch))
      log_info "processing batch finished in ${cycle_elapsed}s (completed_lines=${completed_lines})"
      if [[ "$RUN_STEP_INCLUDE_FINAL_IN_ALL" == "1" ]]; then
        # run the final formatting step as well; the standalone
        # run_main_simulation_cycle wrapper normally handles this,
        # but users often call `run_step.sh all --continuous` directly
        # and expect the final script to fire.  add it here so that
        # the continuous loop really covers the entire simulation
        # pipeline.
        if run_step "final"; then
          log_info "final step completed"
        else
          log_warn "final step failed"
        fi
      else
        log_info "final step skipped (RUN_STEP_INCLUDE_FINAL_IN_ALL=0)"
      fi
      ;;
    from)
      autoclean_conflicting_runs
      start_step="${ARGS[1]:-}"
      if [[ -z "$start_step" ]]; then
        log_error "Usage: $0 from <step_number> [--no-plots]"
        exit 1
      fi
      for step in $(seq "$start_step" 10); do
        if ! run_step "$step"; then
          log_warn "step=$step failed; continuing"
        fi
      done
      cycle_end_epoch=$(date +%s)
      cycle_elapsed=$((cycle_end_epoch - cycle_start_epoch))
      log_info "steps ${start_step}-10 completed in ${cycle_elapsed}s"
      ;;
    *)
      autoclean_conflicting_runs
      if ! run_step "$STEP"; then
        step_failed="1"
      fi
      cycle_end_epoch=$(date +%s)
      cycle_elapsed=$((cycle_end_epoch - cycle_start_epoch))
      ;;
  esac

  if [[ "$step_failed" == "1" ]]; then
    exit 1
  fi

  if [[ -z "$LOOP" ]]; then
    break
  fi
  log_info "loop enabled; restarting"
done
