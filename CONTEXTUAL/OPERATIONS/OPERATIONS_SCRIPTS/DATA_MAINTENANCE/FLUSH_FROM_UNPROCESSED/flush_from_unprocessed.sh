#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FLUSH_FROM_UNPROCESSED/flush_from_unprocessed.sh
# Purpose: Flush from unprocessed.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/FLUSH_FROM_UNPROCESSED/flush_from_unprocessed.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

station_from_path() {
  local path="$1" rel
  if [[ "$path" == "$STATIONS_ROOT/"* ]]; then
    rel=${path#"$STATIONS_ROOT"/}
    echo "${rel%%/*}"
  else
    echo "UNKNOWN"
  fi
}

usage() {
  cat <<'EOF'
Usage: flush_from_unprocessed.sh [--dry-run] [--no-filter]

Removes files under PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/*/UNPROCESSED* whose basename (after the first
underscore, extension trimmed) appears in any *_processed_basenames.csv under
CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/UPDATE_EXECUTION_CSVS/OUTPUT_FILES.

Options:
  --dry-run     Show which files would be removed without deleting them.
  --no-filter   Remove every file under UNPROCESSED directories (ignore processed lists).
  -h,--help     Show this help message.
EOF
}

DRY_RUN=false
NO_FILTER=false
while (( $# > 0 )); do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-filter)
      NO_FILTER=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PROCESSED_DIR="$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/UPDATE_EXECUTION_CSVS/OUTPUT_FILES"
STATIONS_ROOT="$REPO_ROOT/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"
ACTIVE_REPROCESS_CSV="$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/REPROCESS_BASENAMES/active_reprocessing.csv"

if ! $NO_FILTER && [[ ! -d "$PROCESSED_DIR" ]]; then
  log "Processed basenames directory not found: $PROCESSED_DIR"
  exit 1
fi

if [[ ! -d "$STATIONS_ROOT" ]]; then
  log "Stations root not found: $STATIONS_ROOT"
  exit 1
fi

declare -A PROCESSED=()
declare -A ACTIVE_REPROCESS=()
if [[ -s "$ACTIVE_REPROCESS_CSV" ]]; then
  {
    read -r _header || true
    while IFS="," read -r _station active_base _rest; do
      active_base=$(printf "%s" "$active_base" | tr -d "\r")
      [[ -z "$active_base" || "$active_base" == "basename" ]] && continue
      ACTIVE_REPROCESS["$active_base"]=1
    done
  } < "$ACTIVE_REPROCESS_CSV"
  log "Loaded ${#ACTIVE_REPROCESS[@]} active reprocessing basename(s)"
fi
if ! $NO_FILTER; then
  while IFS= read -r -d '' csv_file; do
    while IFS=, read -r base _rest; do
      base=${base//$'\r'/}
      [[ -z "$base" || "$base" == "basename" ]] && continue
      PROCESSED["$base"]=1
    done < "$csv_file"
  done < <(find "$PROCESSED_DIR" -type f -name '*_processed_basenames.csv' -print0)

  if (( ${#PROCESSED[@]} == 0 )); then
    log "No processed basenames loaded from $PROCESSED_DIR"
    exit 1
  fi
  log "Loaded ${#PROCESSED[@]} processed basenames"
else
  log "No-filter mode enabled: every file in UNPROCESSED directories will be removed."
fi

dir_count=0
file_count=0
removed_count=0
declare -A MATCH_COUNTS=()

while IFS= read -r -d '' unprocessed_dir; do
((++dir_count))
  while IFS= read -r -d '' file_path; do
    ((++file_count))
    filename="$(basename "$file_path")"
    stem="${filename%.*}"
    candidate="$stem"
    if [[ "$stem" == *_* ]]; then
      candidate="${stem#*_}"
    fi
    candidate=$(printf "%s" "$candidate" | tr -d "[:cntrl:]")
    if [[ -n ${ACTIVE_REPROCESS[$candidate]:-} ]]; then
      log "Preserved active reprocessing input $file_path"
      continue
    fi
    if $NO_FILTER || [[ -n ${PROCESSED[$candidate]:-} ]]; then
      station="$(station_from_path "$file_path")"
      ((++MATCH_COUNTS["$station"]))
      if $DRY_RUN; then
        log "[DRY-RUN] Would remove $file_path"
      else
        rm -f "$file_path"
        log "Removed $file_path"
      fi
      ((++removed_count))
    fi
  done < <(find "$unprocessed_dir" -type f -print0)
done < <(find "$STATIONS_ROOT" -type d \( -name 'UNPROCESSED' -o -name 'UNPROCESSED_DIRECTORY' \) -print0)

if (( ${#MATCH_COUNTS[@]} > 0 )); then
  log "Per-station files to flush (dry-run: $DRY_RUN):"
  while IFS=$'\t' read -r count station; do
    log "  $station: $count"
  done < <(
    for station in "${!MATCH_COUNTS[@]}"; do
      printf '%d\t%s\n' "${MATCH_COUNTS[$station]}" "$station"
    done | sort -rn -k1,1
  )
else
  log "No matching files found in any station."
fi

log "Checked $file_count files across $dir_count UNPROCESSED directories; removed $removed_count files (dry-run: $DRY_RUN)"
