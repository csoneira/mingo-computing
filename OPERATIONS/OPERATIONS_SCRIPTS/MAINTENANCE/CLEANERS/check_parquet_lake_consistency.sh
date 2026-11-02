#!/usr/bin/env bash
# Read-only archive check extracted from the previous cleaner. Writes only its CSV report.
set -euo pipefail
shopt -s nullglob
DATAFLOW_ROOT="${DATAFLOW_CLEAN_ROOT:?repository root required}"
STATIONS_BASE="$DATAFLOW_ROOT/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"
PARQUET_LAKE_CONSISTENCY_REPORT="$DATAFLOW_ROOT/OPERATIONS/OPERATIONS_RUNTIME/CONSISTENCY/PARQUET_LAKE/parquet_lake_consistency_latest.csv"
log_info() { printf '%s\n' "$*"; }
log_warn() { printf '%s\n' "$*" >&2; }
check_parquet_lake_consistency() {
  local report_dir report_tmp checked_at
  report_dir=$(dirname -- "$PARQUET_LAKE_CONSISTENCY_REPORT")
  mkdir -p "$report_dir"
  report_tmp=$(mktemp "$report_dir/.parquet_lake_consistency.XXXXXX")
  checked_at=$(date -u "+%Y-%m-%dT%H:%M:%SZ")
  printf 'checked_at_utc,station,filename_base,issue,path\n' >"$report_tmp"

  PARQUET_LAKE_EXPECTED_COUNT=0
  PARQUET_LAKE_ACTUAL_COUNT=0
  PARQUET_LAKE_MISSING_COUNT=0
  PARQUET_LAKE_ORPHAN_COUNT=0
  PARQUET_LAKE_INVALID_COUNT=0
  PARQUET_LAKE_STRUCTURE_COUNT=0

  local station_dir station_name lake_dir success_csv file file_name basename magic
  local csv_basename csv_rest
  local station_expected station_actual station_missing station_orphan station_invalid
  for station_dir in "$STATIONS_BASE"/MINGO0[0-9]; do
    [[ -d "$station_dir" ]] || continue
    station_name=$(basename -- "$station_dir")
    lake_dir="$station_dir/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE"
    success_csv="$station_dir/STAGE_1/EVENT_DATA/STEP_1/TASK_5/METADATA/task_5_metadata_specific.csv"

    unset expected_basenames actual_basenames
    declare -A expected_basenames=()
    declare -A actual_basenames=()
    station_expected=0
    station_actual=0
    station_missing=0
    station_orphan=0
    station_invalid=0

    if [[ -s "$success_csv" ]]; then
      while IFS=, read -r csv_basename csv_rest; do
        [[ "$csv_basename" =~ ^mi0[0-9][0-9]{11}$ ]] || continue
        if [[ -z ${expected_basenames["$csv_basename"]:-} ]]; then
          expected_basenames["$csv_basename"]=1
          station_expected=$((station_expected + 1))
        fi
      done <"$success_csv"
    else
      PARQUET_LAKE_STRUCTURE_COUNT=$((PARQUET_LAKE_STRUCTURE_COUNT + 1))
      log_warn "Task-5 successful-output metadata missing or empty for $station_name: $success_csv"
      printf '%s,%s,,task5_success_metadata_missing,%s\n' \
        "$checked_at" "$station_name" "$success_csv" >>"$report_tmp"
    fi

    if [[ ! -d "$lake_dir" ]]; then
      PARQUET_LAKE_STRUCTURE_COUNT=$((PARQUET_LAKE_STRUCTURE_COUNT + 1))
      log_warn "PARQUET_LAKE missing for $station_name: $lake_dir"
      printf '%s,%s,,parquet_lake_missing,%s\n' \
        "$checked_at" "$station_name" "$lake_dir" >>"$report_tmp"
    else
      for file in "$lake_dir"/postprocessed_*.parquet; do
        [[ -f "$file" ]] || continue
        file_name=$(basename -- "$file")
        if [[ "$file_name" =~ ^postprocessed_(mi0[0-9][0-9]{11})[.]parquet$ ]]; then
          basename="${BASH_REMATCH[1]}"
          if [[ -z ${actual_basenames["$basename"]:-} ]]; then
            actual_basenames["$basename"]=1
            station_actual=$((station_actual + 1))
          fi
          magic="$(head -c 4 -- "$file" 2>/dev/null || true)$(tail -c 4 -- "$file" 2>/dev/null || true)"
          if [[ "$magic" != "PAR1PAR1" ]]; then
            station_invalid=$((station_invalid + 1))
            printf '%s,%s,%s,invalid_parquet_magic,%s\n' \
              "$checked_at" "$station_name" "$basename" "$file" >>"$report_tmp"
          fi
        else
          station_orphan=$((station_orphan + 1))
          printf '%s,%s,,unexpected_parquet_filename,%s\n' \
            "$checked_at" "$station_name" "$file" >>"$report_tmp"
        fi
      done
    fi

    for basename in "${!expected_basenames[@]}"; do
      if [[ -z ${actual_basenames["$basename"]:-} ]]; then
        station_missing=$((station_missing + 1))
        printf '%s,%s,%s,successful_task5_missing_from_lake,%s\n' \
          "$checked_at" "$station_name" "$basename" \
          "$lake_dir/postprocessed_${basename}.parquet" >>"$report_tmp"
      fi
    done
    for basename in "${!actual_basenames[@]}"; do
      if [[ -z ${expected_basenames["$basename"]:-} ]]; then
        station_orphan=$((station_orphan + 1))
        printf '%s,%s,%s,archive_without_successful_task5_metadata,%s\n' \
          "$checked_at" "$station_name" "$basename" \
          "$lake_dir/postprocessed_${basename}.parquet" >>"$report_tmp"
      fi
    done

    PARQUET_LAKE_EXPECTED_COUNT=$((PARQUET_LAKE_EXPECTED_COUNT + station_expected))
    PARQUET_LAKE_ACTUAL_COUNT=$((PARQUET_LAKE_ACTUAL_COUNT + station_actual))
    PARQUET_LAKE_MISSING_COUNT=$((PARQUET_LAKE_MISSING_COUNT + station_missing))
    PARQUET_LAKE_ORPHAN_COUNT=$((PARQUET_LAKE_ORPHAN_COUNT + station_orphan))
    PARQUET_LAKE_INVALID_COUNT=$((PARQUET_LAKE_INVALID_COUNT + station_invalid))
    log_info "PARQUET_LAKE $station_name: expected=$station_expected actual=$station_actual missing=$station_missing untracked=$station_orphan invalid=$station_invalid"
  done

  mv -f -- "$report_tmp" "$PARQUET_LAKE_CONSISTENCY_REPORT"
  log_info "PARQUET_LAKE consistency report: $PARQUET_LAKE_CONSISTENCY_REPORT"
  if (( PARQUET_LAKE_MISSING_COUNT > 0 || PARQUET_LAKE_ORPHAN_COUNT > 0 || PARQUET_LAKE_INVALID_COUNT > 0 || PARQUET_LAKE_STRUCTURE_COUNT > 0 )); then
    log_warn "PARQUET_LAKE consistency problems detected: expected=$PARQUET_LAKE_EXPECTED_COUNT actual=$PARQUET_LAKE_ACTUAL_COUNT missing=$PARQUET_LAKE_MISSING_COUNT untracked=$PARQUET_LAKE_ORPHAN_COUNT invalid=$PARQUET_LAKE_INVALID_COUNT structural=$PARQUET_LAKE_STRUCTURE_COUNT"
  else
    log_info "PARQUET_LAKE consistency check passed."
  fi
}

check_parquet_lake_consistency
