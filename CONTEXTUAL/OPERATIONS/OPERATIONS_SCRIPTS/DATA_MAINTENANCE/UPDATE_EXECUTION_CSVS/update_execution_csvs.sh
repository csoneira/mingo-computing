#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/UPDATE_EXECUTION_CSVS/update_execution_csvs.sh
# Purpose: Compatibility wrapper for lake-authoritative processed-basename lists.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Runtime: bash
# Usage: update_execution_csvs.sh [--not-erase] [STATION ...]
# =============================================================================

set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
declare -a STATIONS=()

while (( $# > 0 )); do
  case "$1" in
    --not-erase)
      # Retained for callers of the former interface. The wrapper never erases
      # acquisition metadata, regardless of this flag.
      shift
      ;;
    -h|--help)
      cat <<'HELP'
Usage: update_execution_csvs.sh [--not-erase] [STATION ...]

Deprecated compatibility wrapper. It refreshes MINGOxx_processed_basenames.csv
from valid Parquet Lake archives through FILE_FLOW_TRACKER. It never derives
completion from Stage 2 and never rewrites Stage 0 acquisition metadata.
HELP
      exit 0
      ;;
    --)
      shift
      while (( $# > 0 )); do STATIONS+=("$1"); shift; done
      ;;
    -* )
      log "Unknown option: $1"
      exit 1
      ;;
    *)
      STATIONS+=("$1")
      shift
      ;;
  esac
done

if (( ${#STATIONS[@]} == 0 )); then
  STATIONS=(1 2 3 4)
fi

for station in "${STATIONS[@]}"; do
  if [[ ! "$station" =~ ^[0-9]+$ ]] || (( 10#$station < 0 || 10#$station > 4 )); then
    log "Station identifier must be between 0 and 4 (got $station)"
    exit 1
  fi
done

log "DEPRECATED: delegating to the Parquet-Lake-authoritative FILE_FLOW_TRACKER"
exec /usr/bin/env python3 \
  "$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FILE_FLOW_TRACKER/file_flow_tracker.py" \
  --processed-lists-only --stations "${STATIONS[@]}"
