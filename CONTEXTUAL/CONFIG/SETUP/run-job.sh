#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../CONTENTS/environment/dataflow.sh"
# Fail closed during setup and after a failed prerequisite check.
if [[ ! -f "$DATAFLOW_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/production-enabled" ]]; then
    # Keep the read-only file-flow status snapshot current while production
    # processing is paused. This script only reads pipeline state and writes
    # its own telemetry CSVs; no other scheduled job bypasses the gate.
    paused_readonly=0
    for arg in "$@"; do
        if [[ "$arg" == "$DATAFLOW_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FILE_FLOW_TRACKER/file_flow_realtime.py" ]]; then
            paused_readonly=1
            break
        fi
    done
    (( paused_readonly )) || exit 0
fi
[[ "${1:-}" == -- ]] && shift
cd "$DATAFLOW_ROOT"
export MPLBACKEND=Agg
exec /usr/bin/env "$@"
