#!/usr/bin/env bash
# Purpose: Schedule or execute a selected digital-twin simulation step.

set -euo pipefail

# Backward-compatible entrypoint. Canonical location:
#   PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_step.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/ORCHESTRATOR/core/run_step.sh" "$@"
