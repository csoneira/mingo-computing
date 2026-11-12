#!/usr/bin/env bash
# Purpose: Run audit pipeline states.

set -euo pipefail

# Usage:
#   run_audit_pipeline_states.sh [--scan-logs] [--stale-hours N] [--html-max-rows N] [--stations all|0,1,2,3,4]
#
# Default: all stations, 24h stale, 3000 rows, no log scan.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/audit_pipeline_states.py"
OUTPUT_ROOT="$SCRIPT_DIR/OUTPUT_FILES"

SCAN_LOGS=false
STALE_HOURS=24
HTML_MAX_ROWS=3000
STATIONS=all

while (( $# > 0 )); do
  case "$1" in
    --scan-logs)
      SCAN_LOGS=true
      shift
      ;;
    --stale-hours)
      STALE_HOURS="$2"
      shift 2
      ;;
    --html-max-rows)
      HTML_MAX_ROWS="$2"
      shift 2
      ;;
    --stations)
      STATIONS="$2"
      shift 2
      ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^#//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

ARGS=("--stations" "$STATIONS" "--stale-hours" "$STALE_HOURS" "--html-max-rows" "$HTML_MAX_ROWS")
if $SCAN_LOGS; then
  ARGS+=("--scan-logs")
fi

python3 "$PY_SCRIPT" "${ARGS[@]}"

# Update a stable 'LATEST' pointer for easy access
LATEST_DIR=$(ls -1dt "$OUTPUT_ROOT"/*/ 2>/dev/null | head -n1 || true)
if [[ -n "$LATEST_DIR" ]]; then
  ln -sfn "$LATEST_DIR" "$OUTPUT_ROOT/LATEST"
fi
