#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_DIGITAL_TWIN/run_step.sh
# Purpose: Run step.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_DIGITAL_TWIN/run_step.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

# Backward-compatible entrypoint. Canonical location:
#   PIPELINE/MINGO_DIGITAL_TWIN/ORCHESTRATOR/core/run_step.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/ORCHESTRATOR/core/run_step.sh" "$@"
