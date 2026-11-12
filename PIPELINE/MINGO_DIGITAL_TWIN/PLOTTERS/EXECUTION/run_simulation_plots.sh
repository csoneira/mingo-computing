#!/usr/bin/env bash
# Purpose: Run the configured digital-twin simulation plotters.

set -euo pipefail

EXTRA_ARGS=()

usage() {
  cat <<'USAGE'
Usage: run_simulation_plots.sh [--parallel] [--help] [ARGS...]
Runs:
  - MESH: MESH/plot_param_mesh.py
  - TIME: SIMULATION_TIME/plot_simulation_time.py
  - BACKPRESSURE: BACKPRESSURE/plot_backpressure_monitor.py

Options:
  -p, --parallel    run all scripts in parallel
  -h, --help        show this help

Any extra ARGS are forwarded to MESH and TIME scripts.
USAGE
}

PARALLEL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--parallel) PARALLEL=true; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MESH_SCRIPT="$SCRIPT_DIR/MESH/plot_param_mesh.py"
TIME_SCRIPT="$SCRIPT_DIR/SIMULATION_TIME/plot_simulation_time.py"
BACKPRESSURE_SCRIPT="$SCRIPT_DIR/BACKPRESSURE/plot_backpressure_monitor.py"
PYTHON="$(command -v python3 || command -v python || true)"

if [[ -z "$PYTHON" ]]; then
  echo "Error: python3 (or python) not found in PATH" >&2
  exit 1
fi

for f in "$MESH_SCRIPT" "$TIME_SCRIPT" "$BACKPRESSURE_SCRIPT"; do
  if [[ ! -f "$f" ]]; then
    echo "Error: required script not found: $f" >&2
    exit 2
  fi
done

echo "Start: $(date)"
echo "Using PYTHON: $PYTHON"
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  echo "Extra args: ${EXTRA_ARGS[*]}"
else
  echo "Extra args: <none>"
fi

run_one() {
  local name="$1"; shift
  local script="$1"; shift
  local status
  echo "=== [$name] $(date) ==="
  cd "$SCRIPT_DIR"
  if "$PYTHON" "$script" "$@"; then
    status=0
  else
    status=$?
  fi
  echo "=== [$name] exit: $status ==="
  return $status
}

if [[ "$PARALLEL" == true ]]; then
  run_one "mesh" "$MESH_SCRIPT" "${EXTRA_ARGS[@]}" &
  PID_MESH=$!
  run_one "time" "$TIME_SCRIPT" "${EXTRA_ARGS[@]}" &
  PID_TIME=$!
  run_one "backpressure" "$BACKPRESSURE_SCRIPT" &
  PID_BACKPRESSURE=$!
  set +e
  wait $PID_MESH; STATUS_MESH=$?
  wait $PID_TIME; STATUS_TIME=$?
  wait $PID_BACKPRESSURE; STATUS_BACKPRESSURE=$?
  set -e
  echo "mesh:$STATUS_MESH time:$STATUS_TIME backpressure:$STATUS_BACKPRESSURE"
  exit $(( STATUS_MESH || STATUS_TIME || STATUS_BACKPRESSURE ))
else
  set +e
  run_one "mesh" "$MESH_SCRIPT" "${EXTRA_ARGS[@]}"; STATUS_MESH=$?
  run_one "time" "$TIME_SCRIPT" "${EXTRA_ARGS[@]}"; STATUS_TIME=$?
  run_one "backpressure" "$BACKPRESSURE_SCRIPT"; STATUS_BACKPRESSURE=$?
  set -e
  echo "mesh:$STATUS_MESH time:$STATUS_TIME backpressure:$STATUS_BACKPRESSURE"
  if (( STATUS_MESH || STATUS_TIME || STATUS_BACKPRESSURE )); then
    echo "Finished with errors: $(date)"
    exit 1
  fi
fi

echo "Finished: $(date)"
exit 0
