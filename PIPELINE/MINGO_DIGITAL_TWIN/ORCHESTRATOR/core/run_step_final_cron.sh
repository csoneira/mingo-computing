#!/usr/bin/env bash
# Purpose: Run standalone STEP_FINAL without starving a pending interstep reset.

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
set -euo pipefail

ROOT_DIR="${DATAFLOW_ROOT}"
RESET_MARKER="${SIM_INTERSTEPS_RESET_MARKER:-${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/sim_intersteps_reset_needed.flag}"
FINAL_LOCK="${SIM_FINAL_LOCK:-${ROOT_DIR}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/sim_final.lock}"
STEP_FINAL_SCRIPT="${SIM_STEP_FINAL_SCRIPT:-${ROOT_DIR}/PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_FINAL/step_final_daq_to_station_dat.py}"
STEP_FINAL_CONFIG="${SIM_STEP_FINAL_CONFIG:-${ROOT_DIR}/PIPELINE/MINGO_DIGITAL_TWIN/MASTER_STEPS/STEP_FINAL/config_step_final_physics.yaml}"
PYTHON_BIN="${SIM_PYTHON_BIN:-${PYTHON_BIN:-${DATAFLOW_ROOT}/.venv/bin/python3}}"

# The main controller needs final_lock together with its enqueue and processing
# locks to clear stale intersteps. If a reset is pending, do not compete for the
# final lock; the main controller will clear the marker after the reset.
if [[ -f "${RESET_MARKER}" ]]; then
  exit 0
fi

mkdir -p "$(dirname "${FINAL_LOCK}")"
exec /usr/bin/flock -n "${FINAL_LOCK}" \
  /usr/bin/env "${PYTHON_BIN}" "${STEP_FINAL_SCRIPT}" --config "${STEP_FINAL_CONFIG}"
