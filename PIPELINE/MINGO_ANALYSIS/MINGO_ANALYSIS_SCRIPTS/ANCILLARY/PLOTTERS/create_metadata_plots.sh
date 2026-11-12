#!/usr/bin/env bash
# Purpose: Generate the configured metadata plots.

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
set -u

DATAFLOW_ROOT="${DATAFLOW_ROOT}"
PLOTTERS_ROOT="$DATAFLOW_ROOT/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/PLOTTERS"

failures=0
skipped=0

run_plotter() {
  local label="$1"
  shift

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] START ${label}"
  "$@"
  local rc=$?

  if [[ $rc -eq 3 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP  ${label} (no usable input data)"
    skipped=$((skipped + 1))
  elif [[ $rc -ne 0 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL  ${label} (exit ${rc})"
    failures=$((failures + 1))
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE  ${label}"
  fi
}

run_plotter \
  "definitive_execution_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/DEFINITIVE_EXECUTION/definitive_execution_plotter.py"

run_plotter \
  "filter_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/FILTER/filter_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/FILTER/filter_metadata_config.json"

run_plotter \
  "trigger_rates_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/TRIGGER_RATES/trigger_rate_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/TRIGGER_RATES/trigger_rate_metadata_config.json"

run_plotter \
  "noise_control_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/NOISE_CONTROL/noise_control_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/NOISE_CONTROL/noise_control_metadata_config.json"

run_plotter \
  "rates_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/RATES/rates_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/RATES/rates_metadata_config.json"

run_plotter \
  "task4_chi2_four_plane_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/TASK_4/task4_chi2_four_plane_plotter.py" \
  --config "$PLOTTERS_ROOT/TASK_4/task4_chi2_four_plane_config.json"

run_plotter \
  "execution_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/EXECUTION/execution_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/EXECUTION/execution_metadata_config.json"

run_plotter \
  "efficiency_metadata_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/EFFICIENCIES/efficiency_metadata_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/EFFICIENCIES/efficiency_metadata_config.json"

run_plotter \
  "efficiencies_three_to_four_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/METADATA/EFFICIENCIES_THREE_TO_FOUR/efficiencies_three_to_four_plotter.py" \
  --config "$PLOTTERS_ROOT/METADATA/EFFICIENCIES_THREE_TO_FOUR/efficiencies_three_to_four_config.json"

run_plotter \
  "simulated_data_evolution_plotter" \
  "${PYTHON_BIN:-$DATAFLOW_ROOT/.venv/bin/python3}" -u "$PLOTTERS_ROOT/SIMULATED_DATA_EVOLUTION/simulated_data_evolution_plotter.py" \
  --config "$PLOTTERS_ROOT/SIMULATED_DATA_EVOLUTION/simulated_data_evolution_config.json"

if [[ $failures -ne 0 ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] FINISH with ${failures} failure(s)"
  exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] FINISH failures=${failures} skipped=${skipped}"
