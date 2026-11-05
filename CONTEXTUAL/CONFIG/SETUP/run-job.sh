#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../CONTENTS/environment/dataflow.sh"
# Fail closed during setup and after a failed prerequisite check.
[[ -f "$DATAFLOW_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/production-enabled" ]] || exit 0
[[ "${1:-}" == -- ]] && shift
cd "$DATAFLOW_ROOT"
export MPLBACKEND=Agg
exec /usr/bin/env "$@"
