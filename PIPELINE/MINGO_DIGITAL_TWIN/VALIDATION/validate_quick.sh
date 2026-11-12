#!/usr/bin/env bash
# Purpose: Run the non-destructive quick validation checks for the digital twin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${SCRIPT_DIR}/run_validation.py" --steps "cross,0,1,2,3" "$@"
