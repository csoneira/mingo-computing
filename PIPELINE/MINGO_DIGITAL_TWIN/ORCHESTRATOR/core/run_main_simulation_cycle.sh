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
# Script: PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_main_simulation_cycle.sh
# Purpose: Coordinate the cron-driven simulation enqueue, processing, STEP_FINAL, and maintenance phases.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_main_simulation_cycle.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Simulation orchestrator (cron-driven, two-phase).
#
# Phase 1 (enqueue, fast):
#   - Optional frequency gate
#   - Backpressure gate
#   - STEP_0 with --force (guarantees new mesh rows when under threshold)
#
# Phase 2 (processing, potentially long):
#   - run_step.sh all --no-plots
#   - STEP_FINAL (single attempt under sim_final.lock)
#   - housekeeping (non-fatal)
#
# Locks are internal and per-phase so long processing cannot starve enqueue.
# -----------------------------------------------------------------------------

ROOT_DIR="${DATAFLOW_ROOT}"
DT_DIR="${ROOT_DIR}/PIPELINE/MINGO_DIGITAL_TWIN"
ROOT_RUNTIME_DIR="${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME"
INTERSTEPS_DIR="${DT_DIR}/SIMULATION_OUTPUTS/INTERSTEPS"
RUN_STEP_STATE_DIR_DEFAULT="${ROOT_RUNTIME_DIR}/STATE/run_step"
SIM_INTERSTEPS_RESET_MARKER="${ROOT_RUNTIME_DIR}/STATE/sim_intersteps_reset_needed.flag"
SIM_INTERSTEPS_RESET_TRIGGER_PCT="${SIM_INTERSTEPS_RESET_TRIGGER_PCT:-95}"
SIM_INTERSTEPS_RESET_PENDING=0

SIM_STRUCTURED_LOGS_ENABLED="${SIM_STRUCTURED_LOGS_ENABLED:-1}"
if [[ "${SIM_STRUCTURED_LOGS_ENABLED}" != "0" && "${SIM_STRUCTURED_LOGS_ENABLED}" != "1" ]]; then
  SIM_STRUCTURED_LOGS_ENABLED="1"
fi
SIM_CYCLE_STRUCTURED_LOG_PATH="${ROOT_RUNTIME_DIR}/CRON_LOGS/SIMULATION/STRUCTURED/sim_cycle.jsonl"
SIM_CYCLE_DETAIL_LOG_PATH="${ROOT_RUNTIME_DIR}/CRON_LOGS/SIMULATION/RUN/sim_main_pipeline_cycle_detail.log"
SIM_LOG_HELPER="${DT_DIR}/ORCHESTRATOR/helpers/sim_structured_logging.sh"
if [[ -f "${SIM_LOG_HELPER}" ]]; then
  # shellcheck disable=SC1090
  source "${SIM_LOG_HELPER}"
fi

SIM_ENQUEUE_LOCK="${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_enqueue.lock"
SIM_PROCESSING_LOCK="${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_processing.lock"
SIM_FINAL_LOCK="${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_final.lock"

STEP0_SCRIPT="${DT_DIR}/MASTER_STEPS/STEP_0/step_0_setup_to_blank.py"
RUN_STEP_SCRIPT="${DT_DIR}/ORCHESTRATOR/core/run_step.sh"
STEP_FINAL_SCRIPT="${DT_DIR}/MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py"
STEP_FINAL_CONFIG="${DT_DIR}/MASTER_STEPS/STEP_FINAL/config_step_final_physics.yaml"
MAINTENANCE_CLI="${DT_DIR}/ORCHESTRATOR/maintenance/sim_maintenance.py"
FREQUENCY_CONFIG_FILE_DEFAULT="${DT_DIR}/CONFIG_FILES/ORCHESTRATOR/sim_main_pipeline_frequency.conf"

PARAM_MESH_PATH="${INTERSTEPS_DIR}/STEP_0_TO_1/param_mesh.csv"
SIMULATED_DATA_DIR="${DT_DIR}/SIMULATION_OUTPUTS/SIMULATED_DATA"
SIMULATED_DATA_FILES_DIR="${SIMULATED_DATA_DIR}/FILES"
STATIONS_STEP1_DIR="${ROOT_DIR}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00/STAGE_1/EVENT_DATA/STEP_1"

# Disabled by default: cron already fires every minute.
DEFAULT_MIN_INTERVAL_SECONDS=0
DEFAULT_LAST_RUN_STATE_FILE="${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_main_pipeline.last_run_epoch"

RESOLVED_MIN_INTERVAL_SECONDS="${DEFAULT_MIN_INTERVAL_SECONDS}"
RESOLVED_LAST_RUN_FILE="${DEFAULT_LAST_RUN_STATE_FILE}"

emit_structured_log() {
  local level="$1"
  shift
  local message="$*"
  if ! declare -F sim_structured_log_emit >/dev/null 2>&1; then
    return 0
  fi
  sim_structured_log_emit "${SIM_CYCLE_STRUCTURED_LOG_PATH}" "sim_cycle" "${level}" "${message}" || true
}

log_ts() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_info() {
  printf '%s [SIM_CYCLE] [INFO] %s\n' "$(log_ts)" "$*"
  emit_structured_log "INFO" "$*"
}

log_warn() {
  printf '%s [SIM_CYCLE] [WARN] %s\n' "$(log_ts)" "$*"
  emit_structured_log "WARN" "$*"
}

home_disk_usage_percent() {
  df -P /home 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}'
}

mark_intersteps_reset_needed() {
  local reason="${1:-disk_pressure}"
  local usage="${2:-unknown}"
  mkdir -p "$(dirname "${SIM_INTERSTEPS_RESET_MARKER}")"
  printf 'timestamp=%s\nreason=%s\nusage_pct=%s\n' "$(log_ts)" "${reason}" "${usage}" > "${SIM_INTERSTEPS_RESET_MARKER}"
  log_warn "intersteps_reset status=marked reason=${reason} usage_pct=${usage} marker=${SIM_INTERSTEPS_RESET_MARKER}"
}

maybe_handle_intersteps_reset_after_disk_pressure() {
  local usage
  local enqueue_fd processing_fd final_fd

  SIM_INTERSTEPS_RESET_PENDING=0
  usage="$(home_disk_usage_percent || true)"
  if [[ -z "${usage}" || ! "${usage}" =~ ^[0-9]+$ ]]; then
    log_warn "intersteps_reset status=skipped reason=unknown_disk_usage"
    return 0
  fi

  if (( usage >= SIM_INTERSTEPS_RESET_TRIGGER_PCT )); then
    if [[ ! -f "${SIM_INTERSTEPS_RESET_MARKER}" ]]; then
      mark_intersteps_reset_needed "disk_pressure" "${usage}"
    else
      log_warn "intersteps_reset status=pending usage_pct=${usage} marker=${SIM_INTERSTEPS_RESET_MARKER}"
    fi
  elif [[ ! -f "${SIM_INTERSTEPS_RESET_MARKER}" ]]; then
    return 0
  else
    log_warn "intersteps_reset status=pending usage_pct=${usage} marker=${SIM_INTERSTEPS_RESET_MARKER}"
  fi

  # A pending reset blocks new enqueue/processing work until all three owners
  # release their locks. The next cron cycle then performs the reset immediately;
  # it no longer waits for some other cleaner to reduce disk usage first.
  SIM_INTERSTEPS_RESET_PENDING=1
  mkdir -p "$(dirname "${SIM_ENQUEUE_LOCK}")" "$(dirname "${SIM_PROCESSING_LOCK}")" "$(dirname "${SIM_FINAL_LOCK}")"
  exec {enqueue_fd}> "${SIM_ENQUEUE_LOCK}"
  if ! flock -n "${enqueue_fd}"; then
    log_info "intersteps_reset status=skipped reason=enqueue_lock_busy usage_pct=${usage}"
    exec {enqueue_fd}>&-
    return 0
  fi
  exec {processing_fd}> "${SIM_PROCESSING_LOCK}"
  if ! flock -n "${processing_fd}"; then
    log_info "intersteps_reset status=skipped reason=processing_lock_busy usage_pct=${usage}"
    exec {processing_fd}>&-
    exec {enqueue_fd}>&-
    return 0
  fi
  exec {final_fd}> "${SIM_FINAL_LOCK}"
  if ! flock -n "${final_fd}"; then
    log_info "intersteps_reset status=skipped reason=final_lock_busy usage_pct=${usage}"
    exec {final_fd}>&-
    exec {processing_fd}>&-
    exec {enqueue_fd}>&-
    return 0
  fi

  log_warn "intersteps_reset status=start usage_pct=${usage} intersteps=${INTERSTEPS_DIR} run_step_state=${RUN_STEP_STATE_DIR_DEFAULT}"
  if [[ -L "${INTERSTEPS_DIR}" ]]; then
    local intersteps_target
    intersteps_target="$(readlink -e -- "${INTERSTEPS_DIR}")" || {
      log_warn "intersteps_reset status=failed reason=external_target_unavailable path=${INTERSTEPS_DIR}"
      exec {final_fd}>&-
      exec {processing_fd}>&-
      exec {enqueue_fd}>&-
      return 1
    }
    find "${intersteps_target}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  else
    rm -rf "${INTERSTEPS_DIR}"
    mkdir -p "${INTERSTEPS_DIR}"
  fi
  rm -rf "${RUN_STEP_STATE_DIR_DEFAULT}"
  rm -f "${SIM_INTERSTEPS_RESET_MARKER}"
  SIM_INTERSTEPS_RESET_PENDING=0
  log_warn "intersteps_reset status=done usage_pct=${usage}"

  exec {final_fd}>&-
  exec {processing_fd}>&-
  exec {enqueue_fd}>&-
}

is_nonneg_int() {
  local value="${1:-}"
  [[ "${value}" =~ ^[0-9]+$ ]]
}

load_frequency_gate_settings() {
  local config_file="${SIM_MAIN_CYCLE_FREQUENCY_CONFIG_FILE:-${FREQUENCY_CONFIG_FILE_DEFAULT}}"
  local raw_interval
  local env_interval_set=0
  local env_interval_value=""
  local env_last_run_set=0
  local env_last_run_value=""
  local env_ignore_set=0
  local env_ignore_value=""
  local env_backpressure_set=0
  local env_backpressure_value=""

  if [[ "${SIM_MAIN_CYCLE_MIN_INTERVAL_SECONDS+x}" == "x" ]]; then
    env_interval_set=1
    env_interval_value="${SIM_MAIN_CYCLE_MIN_INTERVAL_SECONDS}"
  fi
  if [[ "${SIM_MAIN_CYCLE_LAST_RUN_FILE+x}" == "x" ]]; then
    env_last_run_set=1
    env_last_run_value="${SIM_MAIN_CYCLE_LAST_RUN_FILE}"
  fi
  if [[ "${SIM_MAIN_CYCLE_IGNORE_FREQUENCY_GATE+x}" == "x" ]]; then
    env_ignore_set=1
    env_ignore_value="${SIM_MAIN_CYCLE_IGNORE_FREQUENCY_GATE}"
  fi
  if [[ "${SIM_MAX_UNPROCESSED_FILES+x}" == "x" ]]; then
    env_backpressure_set=1
    env_backpressure_value="${SIM_MAX_UNPROCESSED_FILES}"
  fi

  if [[ -f "${config_file}" ]]; then
    # shellcheck disable=SC1090
    source "${config_file}"
  fi

  if (( env_interval_set )); then
    SIM_MAIN_CYCLE_MIN_INTERVAL_SECONDS="${env_interval_value}"
  fi
  if (( env_last_run_set )); then
    SIM_MAIN_CYCLE_LAST_RUN_FILE="${env_last_run_value}"
  fi
  if (( env_ignore_set )); then
    SIM_MAIN_CYCLE_IGNORE_FREQUENCY_GATE="${env_ignore_value}"
  fi
  if (( env_backpressure_set )); then
    SIM_MAX_UNPROCESSED_FILES="${env_backpressure_value}"
  fi

  raw_interval="${SIM_MAIN_CYCLE_MIN_INTERVAL_SECONDS:-${DEFAULT_MIN_INTERVAL_SECONDS}}"
  if ! is_nonneg_int "${raw_interval}"; then
    log_warn "frequency_gate status=invalid_interval value='${raw_interval}' fallback=${DEFAULT_MIN_INTERVAL_SECONDS}"
    raw_interval="${DEFAULT_MIN_INTERVAL_SECONDS}"
  fi

  RESOLVED_MIN_INTERVAL_SECONDS="${raw_interval}"
  RESOLVED_LAST_RUN_FILE="${SIM_MAIN_CYCLE_LAST_RUN_FILE:-${DEFAULT_LAST_RUN_STATE_FILE}}"
  log_info "frequency_gate status=config min_interval_s=${RESOLVED_MIN_INTERVAL_SECONDS} state_file=${RESOLVED_LAST_RUN_FILE}"
}

frequency_gate_allows_run() {
  local now_epoch
  local last_epoch
  local elapsed
  local remaining

  if [[ "${SIM_MAIN_CYCLE_IGNORE_FREQUENCY_GATE:-0}" == "1" ]]; then
    log_info "frequency_gate status=bypassed"
    return 0
  fi

  if (( RESOLVED_MIN_INTERVAL_SECONDS <= 0 )); then
    log_info "frequency_gate status=disabled min_interval_s=${RESOLVED_MIN_INTERVAL_SECONDS}"
    return 0
  fi

  now_epoch="$(date +%s)"
  if [[ -f "${RESOLVED_LAST_RUN_FILE}" ]]; then
    last_epoch="$(tr -d '[:space:]' < "${RESOLVED_LAST_RUN_FILE}" || true)"
    if is_nonneg_int "${last_epoch}"; then
      elapsed=$(( now_epoch - last_epoch ))
      if (( elapsed < 0 )); then
        log_warn "frequency_gate status=clock_skew now_epoch=${now_epoch} last_epoch=${last_epoch}"
      elif (( elapsed < RESOLVED_MIN_INTERVAL_SECONDS )); then
        remaining=$(( RESOLVED_MIN_INTERVAL_SECONDS - elapsed ))
        log_info "enqueue status=skipped reason=frequency_gate min_interval_s=${RESOLVED_MIN_INTERVAL_SECONDS} elapsed_s=${elapsed} remaining_s=${remaining}"
        return 1
      fi
    else
      log_warn "frequency_gate status=invalid_state value='${last_epoch}' file=${RESOLVED_LAST_RUN_FILE}"
    fi
  fi

  return 0
}

frequency_gate_mark_run() {
  local run_epoch="${1:-$(date +%s)}"
  if (( RESOLVED_MIN_INTERVAL_SECONDS <= 0 )); then
    return 0
  fi
  mkdir -p "$(dirname "${RESOLVED_LAST_RUN_FILE}")"
  if ! printf '%s\n' "${run_epoch}" > "${RESOLVED_LAST_RUN_FILE}"; then
    log_warn "frequency_gate status=state_write_failed file=${RESOLVED_LAST_RUN_FILE}"
    return 1
  fi
  log_info "frequency_gate status=state_updated epoch=${run_epoch}"
  return 0
}

count_pending_files() {
  local n_sim_root=0 n_sim_files=0 n_unprocessed=0 n_processing=0 total=0

  if [[ -d "${SIMULATED_DATA_DIR}" ]]; then
    n_sim_root=$(find "${SIMULATED_DATA_DIR}" -maxdepth 1 -name "mi*.dat" -type f 2>/dev/null | wc -l || true)
  fi
  if [[ -d "${SIMULATED_DATA_FILES_DIR}" ]]; then
    n_sim_files=$(find "${SIMULATED_DATA_FILES_DIR}" -maxdepth 1 -name "mi*.dat" -type f 2>/dev/null | wc -l || true)
  fi
  if [[ -d "${STATIONS_STEP1_DIR}" ]]; then
    n_unprocessed=$(find "${STATIONS_STEP1_DIR}" -path "*/INPUT_FILES/UNPROCESSED_DIRECTORY/*" -type f ! -name "removed_channel_values_*" ! -name "removed_rows_*" 2>/dev/null | wc -l || true)
    n_processing=$(find "${STATIONS_STEP1_DIR}" -path "*/INPUT_FILES/PROCESSING_DIRECTORY/*" -type f ! -name "removed_channel_values_*" ! -name "removed_rows_*" 2>/dev/null | wc -l || true)
  fi

  total=$(( n_sim_root + n_sim_files + n_unprocessed + n_processing ))
  printf '%s %s %s %s %s\n' "${n_sim_root}" "${n_sim_files}" "${n_unprocessed}" "${n_processing}" "${total}"
}

count_pending_unique_mi() {
  local result
  result="$(
    SIMULATED_DATA_DIR="${SIMULATED_DATA_DIR}" \
    SIMULATED_DATA_FILES_DIR="${SIMULATED_DATA_FILES_DIR}" \
    STATIONS_STEP1_DIR="${STATIONS_STEP1_DIR}" \
      /usr/bin/env python3 - <<'PY'
import os
import re
from itertools import combinations
from pathlib import Path

rx = re.compile(r"(mi\d{13})")
IGNORED_QUEUE_PREFIXES = ("removed_channel_values_", "removed_rows_")


def extract_ids(paths):
    ids = set()
    for path in paths:
        match = rx.search(path.name)
        if match:
            ids.add(match.group(1))
    return ids


def list_files(path: str, pattern: str, recursive: bool = False):
    root = Path(path)
    if not root.is_dir():
        return []
    if recursive:
        return [p for p in root.rglob(pattern) if p.is_file()]
    return [p for p in root.glob(pattern) if p.is_file()]


def is_countable_queue_file(path: Path) -> bool:
    return not path.name.startswith(IGNORED_QUEUE_PREFIXES)


sim_root_files = list_files(os.environ.get("SIMULATED_DATA_DIR", ""), "mi*.dat", recursive=False)
sim_files_files = list_files(os.environ.get("SIMULATED_DATA_FILES_DIR", ""), "mi*.dat", recursive=False)
step1_dir = Path(os.environ.get("STATIONS_STEP1_DIR", ""))
if step1_dir.is_dir():
    unprocessed_files = [
        p
        for p in step1_dir.rglob("*")
        if p.is_file()
        and "INPUT_FILES/UNPROCESSED_DIRECTORY/" in str(p)
        and is_countable_queue_file(p)
    ]
    processing_files = [
        p
        for p in step1_dir.rglob("*")
        if p.is_file()
        and "INPUT_FILES/PROCESSING_DIRECTORY/" in str(p)
        and is_countable_queue_file(p)
    ]
else:
    unprocessed_files = []
    processing_files = []

sets = {
    "sim_root": extract_ids(sim_root_files),
    "sim_files": extract_ids(sim_files_files),
    "unprocessed": extract_ids(unprocessed_files),
    "processing": extract_ids(processing_files),
}
unique_total = len(set().union(*sets.values()))
raw_total = sum(len(v) for v in sets.values())
duplicate_entries = max(raw_total - unique_total, 0)

pairs = {
    ("sim_root", "sim_files"): 0,
    ("sim_root", "unprocessed"): 0,
    ("sim_root", "processing"): 0,
    ("sim_files", "unprocessed"): 0,
    ("sim_files", "processing"): 0,
    ("unprocessed", "processing"): 0,
}
for a, b in combinations(sets.keys(), 2):
    pairs[(a, b)] = len(sets[a] & sets[b])

print(
    unique_total,
    duplicate_entries,
    len(sets["sim_root"]),
    len(sets["sim_files"]),
    len(sets["unprocessed"]),
    len(sets["processing"]),
    pairs[("sim_root", "sim_files")],
    pairs[("sim_root", "unprocessed")],
    pairs[("sim_root", "processing")],
    pairs[("sim_files", "unprocessed")],
    pairs[("sim_files", "processing")],
    pairs[("unprocessed", "processing")],
)
PY
  )" || {
    printf '0 0 0 0 0 0 0 0 0 0 0 0\n'
    return 0
  }
  printf '%s\n' "${result}"
}

backpressure_gate_allows_step0() {
  local threshold="${SIM_MAX_UNPROCESSED_FILES:-0}"
  local n_sim_root=0 n_sim_files=0 n_unprocessed=0 n_processing=0 total=0
  local unique_total=0 duplicate_entries=0 unique_sim_root=0 unique_sim_files=0 unique_unprocessed=0 unique_processing=0
  local overlap_sr_sf=0 overlap_sr_u=0 overlap_sr_p=0 overlap_sf_u=0 overlap_sf_p=0 overlap_u_p=0
  local mesh_undone_rows=0 expected_files_per_sim_run=1 expected_from_mesh=0

  if ! is_nonneg_int "${threshold}"; then
    log_warn "backpressure_gate status=invalid_threshold value='${threshold}' fallback=0"
    threshold=0
  fi

  # shellcheck disable=SC2086
  read -r n_sim_root n_sim_files n_unprocessed n_processing total <<< "$(count_pending_files)"
  # shellcheck disable=SC2086
  read -r unique_total duplicate_entries unique_sim_root unique_sim_files unique_unprocessed unique_processing overlap_sr_sf overlap_sr_u overlap_sr_p overlap_sf_u overlap_sf_p overlap_u_p <<< "$(count_pending_unique_mi)"
  mesh_undone_rows="$(count_mesh_undone_rows "${PARAM_MESH_PATH}")"
  if ! is_nonneg_int "${mesh_undone_rows}"; then
    mesh_undone_rows=0
  fi
  expected_files_per_sim_run="$(resolve_step_final_expected_files_per_sim_run)"
  if ! is_nonneg_int "${expected_files_per_sim_run}" || (( expected_files_per_sim_run <= 0 )); then
    expected_files_per_sim_run=1
  fi
  expected_from_mesh=$(( mesh_undone_rows * expected_files_per_sim_run ))

  if (( threshold <= 0 )); then
    log_info "backpressure_gate status=disabled pending_total=${total} simulated_root=${n_sim_root} simulated_files=${n_sim_files} unprocessed=${n_unprocessed} processing=${n_processing} unique_mi_total=${unique_total} duplicate_entries=${duplicate_entries} unique_simulated_root=${unique_sim_root} unique_simulated_files=${unique_sim_files} unique_unprocessed=${unique_unprocessed} unique_processing=${unique_processing} overlap_sr_sf=${overlap_sr_sf} overlap_sr_u=${overlap_sr_u} overlap_sr_p=${overlap_sr_p} overlap_sf_u=${overlap_sf_u} overlap_sf_p=${overlap_sf_p} overlap_u_p=${overlap_u_p} mesh_undone=${mesh_undone_rows} expected_files_per_sim_run=${expected_files_per_sim_run} expected_from_mesh=${expected_from_mesh}"
    return 0
  fi

  if (( total >= threshold )); then
    log_info "backpressure_gate status=blocked pending_total=${total} threshold=${threshold} simulated_root=${n_sim_root} simulated_files=${n_sim_files} unprocessed=${n_unprocessed} processing=${n_processing} unique_mi_total=${unique_total} duplicate_entries=${duplicate_entries} unique_simulated_root=${unique_sim_root} unique_simulated_files=${unique_sim_files} unique_unprocessed=${unique_unprocessed} unique_processing=${unique_processing} overlap_sr_sf=${overlap_sr_sf} overlap_sr_u=${overlap_sr_u} overlap_sr_p=${overlap_sr_p} overlap_sf_u=${overlap_sf_u} overlap_sf_p=${overlap_sf_p} overlap_u_p=${overlap_u_p} mesh_undone=${mesh_undone_rows} expected_files_per_sim_run=${expected_files_per_sim_run} expected_from_mesh=${expected_from_mesh}"
    return 1
  fi

  if (( expected_from_mesh >= threshold )); then
    log_info "backpressure_gate status=blocked_mesh pending_total=${total} threshold=${threshold} simulated_root=${n_sim_root} simulated_files=${n_sim_files} unprocessed=${n_unprocessed} processing=${n_processing} unique_mi_total=${unique_total} duplicate_entries=${duplicate_entries} unique_simulated_root=${unique_sim_root} unique_simulated_files=${unique_sim_files} unique_unprocessed=${unique_unprocessed} unique_processing=${unique_processing} overlap_sr_sf=${overlap_sr_sf} overlap_sr_u=${overlap_sr_u} overlap_sr_p=${overlap_sr_p} overlap_sf_u=${overlap_sf_u} overlap_sf_p=${overlap_sf_p} overlap_u_p=${overlap_u_p} mesh_undone=${mesh_undone_rows} expected_files_per_sim_run=${expected_files_per_sim_run} expected_from_mesh=${expected_from_mesh}"
    return 1
  fi

  log_info "backpressure_gate status=ok pending_total=${total} threshold=${threshold} simulated_root=${n_sim_root} simulated_files=${n_sim_files} unprocessed=${n_unprocessed} processing=${n_processing} unique_mi_total=${unique_total} duplicate_entries=${duplicate_entries} unique_simulated_root=${unique_sim_root} unique_simulated_files=${unique_sim_files} unique_unprocessed=${unique_unprocessed} unique_processing=${unique_processing} overlap_sr_sf=${overlap_sr_sf} overlap_sr_u=${overlap_sr_u} overlap_sr_p=${overlap_sr_p} overlap_sf_u=${overlap_sf_u} overlap_sf_p=${overlap_sf_p} overlap_u_p=${overlap_u_p} mesh_undone=${mesh_undone_rows} expected_files_per_sim_run=${expected_files_per_sim_run} expected_from_mesh=${expected_from_mesh}"
  return 0
}

count_mesh_rows() {
  local mesh_path="${1:-${PARAM_MESH_PATH}}"
  if [[ ! -f "${mesh_path}" ]]; then
    echo "0"
    return 0
  fi
  awk 'NR>1 {count++} END {print count+0}' "${mesh_path}" 2>/dev/null || echo "0"
}

count_mesh_undone_rows() {
  local mesh_path="${1:-${PARAM_MESH_PATH}}"
  if [[ ! -f "${mesh_path}" ]]; then
    echo "0"
    return 0
  fi

  awk -F, '
    NR==1 {
      for (i=1; i<=NF; i++) {
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)
        if ($i == "done") {
          done_col = i
        }
      }
      next
    }
    {
      if (done_col == 0) {
        count++
        next
      }
      value = $done_col
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value != "1") {
        count++
      }
    }
    END { print count+0 }
  ' "${mesh_path}" 2>/dev/null || echo "0"
}

resolve_step_final_expected_files_per_sim_run() {
  local physics_path="${STEP_FINAL_CONFIG}"
  local runtime_path=""
  if [[ "${physics_path}" == *_physics.yaml ]]; then
    runtime_path="${physics_path%_physics.yaml}_runtime.yaml"
  fi

  local resolved
  resolved="$(
    /usr/bin/env python3 - "${physics_path}" "${runtime_path}" <<'PY'
import sys
from pathlib import Path
import yaml


def load_yaml_mapping(path):
    if path is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_positive_subsample_rows(value):
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "null", "[]"}:
            return []
        raw_rows = [part.strip() for part in text.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        raw_rows = list(value)
    else:
        return []

    rows = []
    for row in raw_rows:
        try:
            row_i = int(row)
        except Exception:
            return []
        if row_i <= 0:
            return []
        rows.append(row_i)
    return rows


physics_path = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] else None
runtime_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None

runtime_cfg = load_yaml_mapping(runtime_path)
physics_cfg = load_yaml_mapping(physics_path)
cfg = dict(runtime_cfg)
cfg.update(physics_cfg)

try:
    files_per_station_conf = int(cfg.get("files_per_station_conf", 1))
except Exception:
    files_per_station_conf = 1
if files_per_station_conf <= 0:
    files_per_station_conf = 1

subsample_rows = parse_positive_subsample_rows(cfg.get("subsample_rows", []))
expected = files_per_station_conf + len(subsample_rows)
print(max(expected, 1))
PY
  )" || {
    echo "1"
    return 0
  }

  if ! is_nonneg_int "${resolved}" || (( resolved <= 0 )); then
    echo "1"
    return 0
  fi
  echo "${resolved}"
}

run_stage() {
  local stage="$1"
  shift
  local rc=0

  log_info "stage=${stage} status=start"
  if "$@"; then
    log_info "stage=${stage} status=ok"
    return 0
  fi

  rc=$?
  log_warn "stage=${stage} status=failed rc=${rc}"
  return "${rc}"
}

run_stage_to_detail_log() {
  local stage="$1"
  shift
  local rc=0

  mkdir -p "$(dirname "${SIM_CYCLE_DETAIL_LOG_PATH}")"
  log_info "stage=${stage} status=start detail_log=${SIM_CYCLE_DETAIL_LOG_PATH}"
  if "$@" >> "${SIM_CYCLE_DETAIL_LOG_PATH}" 2>&1; then
    log_info "stage=${stage} status=ok detail_log=${SIM_CYCLE_DETAIL_LOG_PATH}"
    return 0
  fi

  rc=$?
  log_warn "stage=${stage} status=failed rc=${rc} detail_log=${SIM_CYCLE_DETAIL_LOG_PATH}"
  tail -n 40 "${SIM_CYCLE_DETAIL_LOG_PATH}" 2>/dev/null || true
  return "${rc}"
}

# Cascade cleanup: once step N+1 has produced valid output, step N's
# intermediate SIM_RUN (which was step N+1's input) is no longer needed.
cleanup_consumed_intermediates() {
  local output
  local rc

  if [[ ! -f "${MAINTENANCE_CLI}" ]]; then
    log_warn "cascade_cleanup status=skipped reason=missing_maintenance_cli cli=${MAINTENANCE_CLI}"
    return 1
  fi

  if output="$(/usr/bin/env python3 "${MAINTENANCE_CLI}" cascade-cleanup --intersteps "${INTERSTEPS_DIR}" --mesh "${PARAM_MESH_PATH}" 2>&1)"; then
    log_info "cascade_cleanup status=done ${output}"
    return 0
  fi

  rc=$?
  log_warn "cascade_cleanup status=failed rc=${rc} output=${output}"
  return 1
}

run_enqueue_phase() {
  local mesh_before=0 mesh_after=0 rows_added=0
  local enqueue_failed=0
  local backpressure_purge_enabled="${SIM_BACKPRESSURE_PURGE_ENABLED:-1}"
  local backpressure_purge_fraction="${SIM_BACKPRESSURE_PURGE_FRACTION:-0.5}"

  mkdir -p "$(dirname "${SIM_ENQUEUE_LOCK}")"
  exec {enqueue_fd}> "${SIM_ENQUEUE_LOCK}"
  if ! flock -n "${enqueue_fd}"; then
    log_info "enqueue status=skipped reason=lock_busy lock=${SIM_ENQUEUE_LOCK}"
    exec {enqueue_fd}>&-
    return 0
  fi

  if ! frequency_gate_allows_run; then
    exec {enqueue_fd}>&-
    return 0
  fi

  if [[ "${backpressure_purge_enabled}" != "0" && "${backpressure_purge_enabled}" != "1" ]]; then
    backpressure_purge_enabled="1"
  fi
  if [[ "${backpressure_purge_enabled}" == "1" ]]; then
    if [[ -f "${MAINTENANCE_CLI}" ]]; then
      if ! run_stage "purge_backpressure_queue" /usr/bin/env python3 "${MAINTENANCE_CLI}" purge-backpressure-queue --fraction-of-limit "${backpressure_purge_fraction}"; then
        log_warn "stage=purge_backpressure_queue status=non_fatal_failure"
      fi
    else
      log_info "stage=purge_backpressure_queue status=skipped reason=missing_script"
    fi
  else
    log_info "stage=purge_backpressure_queue status=skipped reason=disabled"
  fi

  if backpressure_gate_allows_step0; then
    mesh_before="$(count_mesh_rows "${PARAM_MESH_PATH}")"
    log_info "stage=step_0 status=start mode=force"
    if /usr/bin/env python3 "${STEP0_SCRIPT}" --force; then
      mesh_after="$(count_mesh_rows "${PARAM_MESH_PATH}")"
      rows_added=$(( mesh_after - mesh_before ))
      if (( rows_added <= 0 )); then
        log_warn "stage=step_0 status=failed reason=no_rows_added rows_before=${mesh_before} rows_after=${mesh_after}"
        enqueue_failed=1
      else
        log_info "stage=step_0 status=ok rows_before=${mesh_before} rows_after=${mesh_after} rows_added=${rows_added}"
      fi
    else
      log_warn "stage=step_0 status=failed"
      enqueue_failed=1
    fi
  else
    log_info "stage=step_0 status=skipped reason=backpressure"
  fi

  frequency_gate_mark_run "$(date +%s)" || true
  exec {enqueue_fd}>&-

  if (( enqueue_failed == 0 )); then
    return 0
  fi
  return 1
}

run_processing_phase() {
  local failed=0
  local requested_include_final="${RUN_STEP_INCLUDE_FINAL_IN_ALL:-0}"
  local run_step_autoclean_conflicts="${SIM_RUN_STEP_AUTOCLEAN_CONFLICTS:-1}"
  local run_step_autoclean_min_age_s="${SIM_RUN_STEP_AUTOCLEAN_MIN_AGE_S:-300}"
  local post_sanitize_enabled="${SIM_POST_SANITIZE_ENABLED:-1}"
  local post_sanitize_min_age_s="${SIM_POST_SANITIZE_MIN_AGE_S:-900}"
  local processing_runs_step_final="${SIM_PROCESSING_RUN_STEP_FINAL:-1}"
  local run_step_stuck_alerts_enabled="${RUN_STEP_STUCK_ALERTS_ENABLED:-1}"
  local run_step_stuck_alert_min_cycles="${RUN_STEP_STUCK_ALERT_MIN_CYCLES:-3}"
  local run_step_stuck_alert_repeat_cycles="${RUN_STEP_STUCK_ALERT_REPEAT_CYCLES:-60}"
  local run_step_stuck_alert_min_observation_interval_s="${RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S:-45}"

  if [[ "${run_step_autoclean_conflicts}" != "0" && "${run_step_autoclean_conflicts}" != "1" ]]; then
    run_step_autoclean_conflicts="1"
  fi
  if ! is_nonneg_int "${run_step_autoclean_min_age_s}"; then
    run_step_autoclean_min_age_s="300"
  fi
  if [[ "${post_sanitize_enabled}" != "0" && "${post_sanitize_enabled}" != "1" ]]; then
    post_sanitize_enabled="1"
  fi
  if ! is_nonneg_int "${post_sanitize_min_age_s}"; then
    post_sanitize_min_age_s="900"
  fi
  if [[ "${processing_runs_step_final}" != "0" && "${processing_runs_step_final}" != "1" ]]; then
    processing_runs_step_final="1"
  fi
  if [[ "${run_step_stuck_alerts_enabled}" != "0" && "${run_step_stuck_alerts_enabled}" != "1" ]]; then
    run_step_stuck_alerts_enabled="1"
  fi
  if ! is_nonneg_int "${run_step_stuck_alert_min_cycles}"; then
    run_step_stuck_alert_min_cycles="3"
  fi
  if ! is_nonneg_int "${run_step_stuck_alert_repeat_cycles}"; then
    run_step_stuck_alert_repeat_cycles="60"
  fi
  if ! is_nonneg_int "${run_step_stuck_alert_min_observation_interval_s}"; then
    run_step_stuck_alert_min_observation_interval_s="45"
  fi

  mkdir -p "$(dirname "${SIM_PROCESSING_LOCK}")"
  exec {processing_fd}> "${SIM_PROCESSING_LOCK}"
  if ! flock -n "${processing_fd}"; then
    log_info "processing status=skipped reason=lock_busy lock=${SIM_PROCESSING_LOCK}"
    exec {processing_fd}>&-
    return 0
  fi

  if [[ "${SIM_ENABLE_REPAIR_MESH_IDS:-0}" == "1" ]]; then
    if ! run_stage "repair_mesh_step_ids" /usr/bin/env python3 "${MAINTENANCE_CLI}" repair-mesh-step-ids --apply; then
      log_warn "stage=repair_mesh_step_ids status=non_fatal_failure"
    fi
  else
    log_info "stage=repair_mesh_step_ids status=skipped reason=disabled"
  fi

  if [[ "${requested_include_final}" != "0" ]]; then
    log_warn "stage=run_step_all invariant=force_disable_step_final requested_value=${requested_include_final}"
  fi
  log_info "sanitize_policy pre_enabled=${run_step_autoclean_conflicts} pre_min_age_s=${run_step_autoclean_min_age_s} post_enabled=${post_sanitize_enabled} post_min_age_s=${post_sanitize_min_age_s}"
  log_info "alert_policy stuck_alerts_enabled=${run_step_stuck_alerts_enabled} min_cycles=${run_step_stuck_alert_min_cycles} repeat_cycles=${run_step_stuck_alert_repeat_cycles} min_observation_interval_s=${run_step_stuck_alert_min_observation_interval_s}"

  # Invariant: the processing phase runs STEP_FINAL exactly once below under
  # sim_final.lock, so run_step.sh all must never invoke STEP_FINAL itself.
  if ! run_stage_to_detail_log "run_step_all" /usr/bin/env \
    RUN_STEP_STRICT_LINE_CLOSURE="${RUN_STEP_STRICT_LINE_CLOSURE:-0}" \
    RUN_STEP_OBLITERATE_UNINTERESTING_STEP1_LINES="${RUN_STEP_OBLITERATE_UNINTERESTING_STEP1_LINES:-0}" \
    RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY="${RUN_STEP_CHECK_PARAM_MESH_CONSISTENCY:-0}" \
    RUN_STEP_AUTOCLEAN_CONFLICTS="${run_step_autoclean_conflicts}" \
    RUN_STEP_AUTOCLEAN_MIN_AGE_S="${run_step_autoclean_min_age_s}" \
    RUN_STEP_STUCK_ALERTS_ENABLED="${run_step_stuck_alerts_enabled}" \
    RUN_STEP_STUCK_ALERT_MIN_CYCLES="${run_step_stuck_alert_min_cycles}" \
    RUN_STEP_STUCK_ALERT_REPEAT_CYCLES="${run_step_stuck_alert_repeat_cycles}" \
    RUN_STEP_STUCK_ALERT_MIN_OBSERVATION_INTERVAL_S="${run_step_stuck_alert_min_observation_interval_s}" \
    RUN_STEP_INCLUDE_FINAL_IN_ALL=0 \
    /bin/bash "${RUN_STEP_SCRIPT}" all --no-plots; then
    failed=1
  fi

  if [[ "${processing_runs_step_final}" == "1" ]]; then
    log_info "stage=step_final status=start lock=${SIM_FINAL_LOCK}"
    if flock -n -E 200 "${SIM_FINAL_LOCK}" /usr/bin/env python3 "${STEP_FINAL_SCRIPT}" --config "${STEP_FINAL_CONFIG}"; then
      log_info "stage=step_final status=ok"
    else
      rc=$?
      if (( rc == 200 )); then
        log_info "stage=step_final status=skipped reason=lock_busy lock=${SIM_FINAL_LOCK}"
      else
        log_warn "stage=step_final status=failed rc=${rc}"
        failed=1
      fi
    fi
  else
    log_info "stage=step_final status=skipped reason=disabled_by_config"
  fi

  if ! run_stage "prune_mesh_done_rows" /usr/bin/env python3 "${MAINTENANCE_CLI}" prune-mesh; then
    log_warn "stage=prune_mesh_done_rows status=non_fatal_failure"
  fi

  if [[ -f "${MAINTENANCE_CLI}" ]]; then
    if ! run_stage "prune_final_params" /usr/bin/env python3 "${MAINTENANCE_CLI}" prune-final-params; then
      log_warn "stage=prune_final_params status=non_fatal_failure"
    fi
  fi

  cleanup_consumed_intermediates || log_warn "stage=cascade_cleanup status=non_fatal_failure"

  if [[ "${post_sanitize_enabled}" == "1" ]]; then
    if [[ -f "${MAINTENANCE_CLI}" ]]; then
      if ! run_stage "sanitize" /usr/bin/env python3 "${MAINTENANCE_CLI}" sanitize-runs --apply --min-age-seconds "${post_sanitize_min_age_s}"; then
        log_warn "stage=sanitize status=non_fatal_failure"
      fi
    else
      log_info "stage=sanitize status=skipped reason=missing_script"
    fi
  else
    log_info "stage=sanitize status=skipped reason=disabled"
  fi

  exec {processing_fd}>&-
  if (( failed == 0 )); then
    return 0
  fi
  return 1
}

main() {
  local failed=0

  load_frequency_gate_settings
  log_info "cycle status=start"
  maybe_handle_intersteps_reset_after_disk_pressure
  if (( SIM_INTERSTEPS_RESET_PENDING == 1 )); then
    log_warn "cycle status=deferred reason=intersteps_reset_pending"
    return 0
  fi

  if ! run_enqueue_phase; then
    failed=1
  fi

  if ! run_processing_phase; then
    failed=1
  fi

  if (( failed == 0 )); then
    log_info "cycle status=ok"
    return 0
  fi

  log_warn "cycle status=failed"
  return 1
}

main "$@"
