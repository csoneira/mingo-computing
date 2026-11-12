#!/usr/bin/env bash
# Purpose: Restart simulation pipeline totally.

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

usage() {
  cat <<'EOF'
Restart simulation pipeline from a clean state while archiving previous outputs.

What gets archived/moved out:
  - PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00
  - PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA
  - PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS
  - PIPELINE/MINGO_DIGITAL_TWIN/PLOTTERS/EXECUTION runtime history/plot artifacts

What gets recreated empty:
  - PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00
  - PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES
  - PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1

Usage:
  restart_simulation_pipeline_totally.sh [--yes] [--archive-root DIR] [--root DIR]

Options:
  --yes               Skip confirmation prompt.
  --archive-root DIR  Archive base directory (default: $HOME/SIMULATION_DATA_JUNK).
  --root DIR          DATAFLOW root (default: ${DATAFLOW_ROOT}).
  -h, --help          Show this help.
EOF
}

ROOT_DIR="${DATAFLOW_ROOT}"
ARCHIVE_ROOT="${HOME}/SIMULATION_DATA_JUNK"
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --archive-root)
      ARCHIVE_ROOT="$2"
      shift 2
      ;;
    --root)
      ROOT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[error] Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

DT_DIR="${ROOT_DIR}/PIPELINE/MINGO_DIGITAL_TWIN"
MINGO00_DIR="${ROOT_DIR}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00"
SIMULATED_DATA_DIR="${DT_DIR}/SIMULATION_OUTPUTS/SIMULATED_DATA"
INTERSTEPS_DIR="${DT_DIR}/SIMULATION_OUTPUTS/INTERSTEPS"

PLOTTER_FILES_TO_RESET=(
  "PLOTTERS/EXECUTION/BACKPRESSURE/backpressure_monitor_history.csv"
  "PLOTTERS/EXECUTION/BACKPRESSURE/manually_removed.csv"
  "PLOTTERS/EXECUTION/BACKPRESSURE/backpressure_monitor.pdf"
  "PLOTTERS/EXECUTION/SIMULATION_TIME/simulation_execution_times.csv"
  "PLOTTERS/EXECUTION/SIMULATION_TIME/simulation_execution_time_hist.pdf"
  "PLOTTERS/EXECUTION/MESH/param_mesh_summary.pdf"
)

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
ARCHIVE_DIR="${ARCHIVE_ROOT}/restart_${STAMP}"
if [[ -e "${ARCHIVE_DIR}" ]]; then
  ARCHIVE_DIR="${ARCHIVE_DIR}_$$"
fi

for required in "${ROOT_DIR}" "${DT_DIR}"; do
  if [[ ! -d "${required}" ]]; then
    echo "[error] Required directory does not exist: ${required}" >&2
    exit 1
  fi
done

if [[ ${ASSUME_YES} -ne 1 ]]; then
  if [[ ! -t 0 ]]; then
    echo "[error] Non-interactive shell detected. Re-run with --yes." >&2
    exit 2
  fi
  echo "This will archive and reset simulation outputs:"
  echo "  - ${MINGO00_DIR}"
  echo "  - ${SIMULATED_DATA_DIR}"
  echo "  - ${INTERSTEPS_DIR}"
  echo "  - ${DT_DIR}/PLOTTERS/EXECUTION/* runtime history/plots"
  echo "Archive destination: ${ARCHIVE_DIR}"
  read -r -p "Continue? [y/N] " reply
  case "${reply}" in
    y|Y|yes|YES) ;;
    *)
      echo "[abort] No changes made."
      exit 0
      ;;
  esac
fi

mkdir -p \
  "${ARCHIVE_DIR}/STATIONS" \
  "${ARCHIVE_DIR}/MINGO_DIGITAL_TWIN"

moved_items=0
reset_plotter_items=0

move_if_exists() {
  local src="$1"
  local dst_dir="$2"
  if [[ -e "${src}" ]]; then
    mv "${src}" "${dst_dir}/"
    echo "[moved] ${src} -> ${dst_dir}/"
    moved_items=$((moved_items + 1))
  else
    echo "[skip] ${src} does not exist"
  fi
}

move_if_exists "${MINGO00_DIR}" "${ARCHIVE_DIR}/STATIONS"
move_if_exists "${SIMULATED_DATA_DIR}" "${ARCHIVE_DIR}/MINGO_DIGITAL_TWIN"
move_if_exists "${INTERSTEPS_DIR}" "${ARCHIVE_DIR}/MINGO_DIGITAL_TWIN"

archive_plotter_file_if_exists() {
  local rel_path="$1"
  local src="${DT_DIR}/${rel_path}"
  local dst="${ARCHIVE_DIR}/PIPELINE/MINGO_DIGITAL_TWIN/${rel_path}"
  if [[ -f "${src}" ]]; then
    mkdir -p "$(dirname "${dst}")"
    mv "${src}" "${dst}"
    echo "[moved] ${src} -> ${dst}"
    reset_plotter_items=$((reset_plotter_items + 1))
  else
    echo "[skip] ${src} does not exist"
  fi
}

for rel_path in "${PLOTTER_FILES_TO_RESET[@]}"; do
  archive_plotter_file_if_exists "${rel_path}"
done

mkdir -p "${MINGO00_DIR}"
mkdir -p "${SIMULATED_DATA_DIR}/FILES"
mkdir -p "${INTERSTEPS_DIR}/STEP_0_TO_1"

{
  echo "restart_timestamp_utc=${STAMP}"
  echo "dataflow_root=${ROOT_DIR}"
  echo "archive_dir=${ARCHIVE_DIR}"
  echo "status=completed"
  echo "moved_items_total=${moved_items}"
  echo "moved_station_dir=PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00"
  echo "moved_simulated_data_dir=PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA"
  echo "moved_intersteps_dir=PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS"
  echo "moved_plotter_runtime_files=${reset_plotter_items}"
  echo "recreated_station_dir=PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO00"
  echo "recreated_simulated_data_dir=PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES"
  echo "recreated_intersteps_dir=PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS/STEP_0_TO_1"
  for rel_path in "${PLOTTER_FILES_TO_RESET[@]}"; do
    echo "reset_plotter_file=${rel_path}"
  done
} > "${ARCHIVE_DIR}/restart_manifest.txt"

echo "[ok] Clean restart reset completed"
echo "[ok] Archive created at: ${ARCHIVE_DIR}"
echo "[next] Update z geometry config(s), then run STEP 0 and subsequent steps."
