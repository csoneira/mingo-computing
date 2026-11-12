#!/usr/bin/env bash
# Purpose: Run all configured quality-assurance steps.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/orchestrate_quality_assurance.py" "$@"
