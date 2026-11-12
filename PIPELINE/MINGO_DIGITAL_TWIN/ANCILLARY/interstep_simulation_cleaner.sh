#!/usr/bin/env bash
# Purpose: Remove simulation interstep files selected by the configured retention policy.

# Remove the complete simulation INTERSTEPS tree after its products are no
# longer needed. This is a Digital Twin maintenance operation.

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

BASE="${DATAFLOW_ROOT}/PIPELINE/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS"
JOBS="${JOBS:-$(nproc)}"

echo "Target base directory:"
echo "${BASE}"
echo

if [[ ! -d "${BASE}" ]]; then
  echo "Base directory does not exist. Nothing to delete."
  exit 0
fi

echo "Deleting matching pickle chunks:"
echo "${BASE}/STEP_*_TO_*/SIM_RUN_*/step_*_chunks/part_*.pkl"
echo "Parallel jobs: ${JOBS}"
echo

find "${BASE}" \
  -type f \
  -path "${BASE}/STEP_*_TO_*/SIM_RUN_*/step_*_chunks/part_*.pkl" \
  -print0 \
| xargs -0 -r -n 1000 -P "${JOBS}" rm -f --

echo
echo "Removing entire INTERSTEPS directory:"
echo "${BASE}"

rm -rf --one-file-system -- "${BASE}"

echo "Done."
