#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/clean_dataflow.sh
# Purpose: Clean dataflow.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-05-08
# Runtime: bash
# Usage: bash OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/clean_dataflow.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

LC_ALL=C
shopt -s dotglob nullglob

COMPACT=false

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DATAFLOW_ROOT_DEFAULT="$(cd -- "$SCRIPT_DIR/../../../.." && pwd -P)"
DATAFLOW_ROOT="${DATAFLOW_CLEAN_ROOT:-$DATAFLOW_ROOT_DEFAULT}"
DATAFLOW_PARENT="$(dirname -- "$DATAFLOW_ROOT")"
LOCK_FILE="${DATAFLOW_CLEAN_LOCK_FILE:-/tmp/dataflow_clean_dataflow.lock}"

log_ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log_warn() {
  printf '[%s] [CLEAN_DATAFLOW] [WARN] %s\n' "$(log_ts)" "$*" >&2
}

log_info() {
  printf '%s\n' "$*"
}

log_detail() {
  if [[ "$COMPACT" != true ]]; then
    printf '%s\n' "$*"
  fi
}

usage() {
  cat <<'EOF'
clean_dataflow.sh
Unified cleaner and archive-consistency checker for DATAFLOW_v3 artefacts (COMPLETED_DIRECTORY exports, QA-verified intermediates, plot bundles, and Stage-0 buffers).

Usage:
  clean_dataflow.sh [--force|-f] [--threshold|-t <percent>] [--select|-s <list>] [--compact|-c] [--keep-final] [--kill-lock-holder]

Options:
  -h, --help             Show this help message and exit.
  -f, --force            Skip the disk usage threshold check.
                         When --select is omitted, defaults to: temps,plots,completed.
  -t, --threshold <pct>  Override the disk usage threshold (0-100, default 50).
  -s, --select <list>    Comma-separated list of cleanups to run (temps,plots,completed,cronlogs).
                         May be repeated. Defaults to all when omitted.
  -c, --compact          Compact output for chat/notification consumers.
  --keep-final           Preserve STEP_1/TASK_*/INPUT_FILES/COMPLETED_DIRECTORY contents
                         during completed cleanup. If /home usage rises above 90%,
                         prune the oldest files from those final completed directories
                         until usage drops to 60% or no files remain.
  --kill-lock-holder     If another clean_dataflow process holds the lock, terminate it,
                         remove the stale lock file, and continue. Use only after checking
                         that the previous cleaner should be stopped.

Emergency fallback:
  PARQUET_LAKE is persistent under normal operation. Only when /home is above 95%
  does the emergency policy prune globally oldest parquets, exhausting files outside
  configured date ranges of interest before considering in-range files, until 95%.

Consistency check:
  Every invocation compares successful Task-5 metadata records with each station PARQUET_LAKE,
  checks parquet magic bytes, and atomically updates a detailed CSV report.

Examples:
  clean_dataflow.sh
  clean_dataflow.sh --threshold 65 --select plots,completed
  clean_dataflow.sh --force -s temps
  clean_dataflow.sh --force --select completed --keep-final
  clean_dataflow.sh --force --select plots,completed --kill-lock-holder
  clean_dataflow.sh --force --compact
EOF
}

DEFAULT_SELECTION=(temps plots completed cronlogs)
FORCE_DEFAULT_SELECTION=(temps plots completed)
declare -A VALID_TYPES=([temps]=1 [plots]=1 [completed]=1 [cronlogs]=1)

STATIONS_BASE="${DATAFLOW_CLEAN_STATIONS_BASE:-$DATAFLOW_ROOT/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS}"
TEMP_ROOTS=(
  "$DATAFLOW_ROOT"
  "${DATAFLOW_CLEAN_SAFE_ROOT:-$DATAFLOW_PARENT/SAFE_DATAFLOW_v3}"
)
CRON_LOG_DIR="${DATAFLOW_CLEAN_CRON_LOG_DIR:-$DATAFLOW_ROOT/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS}"
SIM_JUNK_BASE="${DATAFLOW_CLEAN_SIM_JUNK_BASE:-$DATAFLOW_PARENT/SIMULATION_DATA_JUNK}"
PLOTS_KEEP_FRESHEST="${DATAFLOW_CLEAN_PLOTS_KEEP_FRESHEST:-5}"
KEEP_FINAL_TRIGGER_PCT="${DATAFLOW_CLEAN_KEEP_FINAL_TRIGGER_PCT:-90}"
KEEP_FINAL_TARGET_PCT="${DATAFLOW_CLEAN_KEEP_FINAL_TARGET_PCT:-60}"
ARCHIVE_PRESSURE_TRIGGER_PCT="${DATAFLOW_CLEAN_ARCHIVE_PRESSURE_TRIGGER_PCT:-95}"
MASTER_CONFIG_ROOT="${DATAFLOW_CLEAN_MASTER_CONFIG_ROOT:-$DATAFLOW_ROOT/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES}"
ARCHIVE_EMERGENCY_DIR="${DATAFLOW_CLEAN_ARCHIVE_EMERGENCY_DIR:-}"
PARQUET_LAKE_CONSISTENCY_REPORT="${DATAFLOW_CLEAN_PARQUET_LAKE_REPORT:-$DATAFLOW_ROOT/OPERATIONS/OPERATIONS_RUNTIME/CONSISTENCY/PARQUET_LAKE/parquet_lake_consistency_latest.csv}"
QA_REPROCESSING_SUMMARY="${DATAFLOW_CLEAN_QA_SUMMARY:-$DATAFLOW_ROOT/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/QUALITY_ASSURANCE_NEW/TOTAL_SUMMARY/OUTPUTS/FILES/qa_all_stations_reprocessing_quality.csv}"

declare -A TYPE_BEFORE=()
declare -A TYPE_AFTER=()
declare -A TYPE_FREED=()
declare -A TYPE_COUNTS=()
QUEUE_SIDECAR_BEFORE=0
QUEUE_SIDECAR_AFTER=0
QUEUE_SIDECAR_FREED=0
QUEUE_SIDECAR_COUNT=0
PARQUET_LAKE_EXPECTED_COUNT=0
PARQUET_LAKE_ACTUAL_COUNT=0
PARQUET_LAKE_MISSING_COUNT=0
PARQUET_LAKE_ORPHAN_COUNT=0
PARQUET_LAKE_INVALID_COUNT=0
PARQUET_LAKE_STRUCTURE_COUNT=0

join_by() {
  local sep="$1"
  shift || { printf ""; return 0; }
  local first="$1"
  shift
  printf "%s" "$first"
  for item in "$@"; do
    printf "%s%s" "$sep" "$item"
  done
}

format_bytes() {
  local bytes="${1:-0}"
  if [[ -z "$bytes" ]]; then
    bytes=0
  fi
  local abs=$(( bytes < 0 ? -bytes : bytes ))
  local decimal
  decimal=$(awk -v b="$abs" 'BEGIN{printf "%.3f", b/1000000000}')
  local binary
  binary=$(awk -v b="$abs" 'BEGIN{printf "%.3f", b/1024/1024/1024}')
  if (( bytes < 0 )); then
    printf "-%s GB (-%s GiB)" "$decimal" "$binary"
  else
    printf "%s GB (%s GiB)" "$decimal" "$binary"
  fi
}

validate_threshold() {
  local value="$1"
  if [[ -z "$value" ]]; then
    echo "Threshold requires a numeric value." >&2
    exit 1
  fi
  if [[ ! "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Threshold must be numeric between 0 and 100: $value" >&2
    exit 1
  fi
  local formatted
  if ! formatted=$(LC_ALL=C awk -v v="$value" 'BEGIN{if (v < 0 || v > 100) exit 1; printf "%.2f", v}'); then
    echo "Threshold must be between 0 and 100: $value" >&2
    exit 1
  fi
  printf "%s" "$formatted"
}

disk_usage_percent() {
  df -P /home | awk 'NR==2 {gsub("%","",$5); print $5}'
}

disk_usage_summary() {
  df -h /home | awk 'NR==2 {printf "%s used (%s / %s)", $5, $3, $2}'
}

label_for_type() {
  case "$1" in
    temps) echo "temps";;
    plots) echo "plots";;
    completed) echo "completed directories";;
    cronlogs) echo "cron logs";;
    *) echo "$1";;
  esac
}

is_metadata_path() {
  local path="${1:-}"
  local upper="${path^^}"
  [[ "$upper" == *"/METADATA/"* || "$upper" == *"/METADATA" ]]
}

is_final_completed_dir() {
  local path="${1:-}"
  local upper="${path^^}"
  [[ "$upper" == *"/STAGE_1/EVENT_DATA/STEP_1/TASK_"*"/INPUT_FILES/COMPLETED_DIRECTORY" ]]
}

prune_final_completed_if_needed() {
  local -a final_dirs=("$@")
  if [[ "$KEEP_FINAL" != true ]] || (( ${#final_dirs[@]} == 0 )); then
    return 0
  fi

  local current_usage
  current_usage=$(disk_usage_percent)
  if [[ -z "$current_usage" ]]; then
    log_warn "Unable to determine disk usage for final completed pruning check. Preserving final completed files."
    return 0
  fi

  if (( current_usage < KEEP_FINAL_TRIGGER_PCT )); then
    log_info "Keeping final completed directories: disk usage ${current_usage}% is below emergency trigger ${KEEP_FINAL_TRIGGER_PCT}%."
    return 0
  fi

  log_warn "Disk usage ${current_usage}% exceeds keep-final emergency trigger ${KEEP_FINAL_TRIGGER_PCT}%. Pruning oldest final completed files until ${KEEP_FINAL_TARGET_PCT}% or no files remain."

  local deleted_count=0
  local deleted_bytes=0
  local candidate_count=0
  local record rest file_size file_path
  while IFS= read -r -d '' record; do
    [[ -n "$record" ]] || continue
    candidate_count=$((candidate_count + 1))
    rest="${record#*$'\t'}"
    file_size="${rest%%$'\t'*}"
    file_path="${rest#*$'\t'}"
    [[ -f "$file_path" ]] || continue

    chmod u+w -- "$file_path" 2>/dev/null || true
    if rm -f -- "$file_path" 2>/dev/null; then
      deleted_count=$((deleted_count + 1))
      deleted_bytes=$((deleted_bytes + file_size))
      current_usage=$(disk_usage_percent)
      if [[ -n "$current_usage" ]] && (( current_usage <= KEEP_FINAL_TARGET_PCT )); then
        break
      fi
    else
      log_warn "Failed to remove final completed file during emergency prune: $file_path"
    fi
  done < <(find "${final_dirs[@]}" -type f -printf '%T@\t%s\t%p\0' 2>/dev/null | sort -z -n)

  find "${final_dirs[@]}" -depth -type d -empty -delete 2>/dev/null || true

  current_usage=$(disk_usage_percent)
  if (( candidate_count == 0 )); then
    log_warn "Emergency final completed pruning was triggered, but no files were found."
    return 0
  fi

  log_info "Emergency final completed pruning removed ${deleted_count} file(s)"
  log_info "   Freed:       $(format_bytes "$deleted_bytes")"
  log_info "   Disk usage:  ${current_usage}%"
  if [[ -n "$current_usage" ]] && (( current_usage > KEEP_FINAL_TARGET_PCT )); then
    log_warn "Disk usage remains above target ${KEEP_FINAL_TARGET_PCT}% after pruning. No more eligible final completed files remain or more cleanup is needed elsewhere."
  fi
}

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

run_archive_emergency_cleanup() {
  local current_usage
  current_usage=$(disk_usage_percent)
  if [[ -z "$current_usage" ]]; then
    log_warn "Unable to determine /home usage; skipping emergency PARQUET_LAKE pruning."
    return 0
  fi

  # Strictly greater than the threshold: 95% itself is not enough to delete.
  if (( current_usage <= ARCHIVE_PRESSURE_TRIGGER_PCT )); then
    log_info "PARQUET_LAKE emergency check: disk usage ${current_usage}% is not above ${ARCHIVE_PRESSURE_TRIGGER_PCT}%."
    return 0
  fi

  local -a lake_dirs=()
  local station_dir lake_dir
  if [[ -n "$ARCHIVE_EMERGENCY_DIR" ]]; then
    [[ -d "$ARCHIVE_EMERGENCY_DIR" ]] && lake_dirs+=("$ARCHIVE_EMERGENCY_DIR")
  else
    for station_dir in "$STATIONS_BASE"/MINGO0[0-9]; do
      [[ -d "$station_dir" ]] || continue
      lake_dir="$station_dir/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE"
      [[ -d "$lake_dir" ]] && lake_dirs+=("$lake_dir")
    done
  fi
  if (( ${#lake_dirs[@]} == 0 )); then
    log_warn "Disk usage is ${current_usage}%, but no PARQUET_LAKE directories were found."
    return 0
  fi

  local ranker="$SCRIPT_DIR/rank_parquet_lake_candidates.py"
  local candidate_manifest
  candidate_manifest=$(mktemp /tmp/dataflow_archive_candidates.XXXXXX)
  if ! python3 "$ranker" "$DATAFLOW_ROOT" "$MASTER_CONFIG_ROOT" "${lake_dirs[@]}" >"$candidate_manifest"; then
    log_warn "Could not rank PARQUET_LAKE candidates against $MASTER_CONFIG_ROOT/config_selection.yaml; refusing emergency deletion."
    rm -f -- "$candidate_manifest"
    return 0
  fi

  log_warn "Disk usage ${current_usage}% is above ${ARCHIVE_PRESSURE_TRIGGER_PCT}%. Pruning oldest PARQUET_LAKE files to ${ARCHIVE_PRESSURE_TRIGGER_PCT}%."
  log_info "Priority: files outside configured date ranges first, then in-range files; oldest first within each tier."

  local deleted_count=0
  local deleted_bytes=0
  local deleted_out_of_range=0
  local deleted_in_range=0
  local record priority rest mtime_ns file_size file_path
  while IFS= read -r -d '' record; do
    priority="${record%%$'\t'*}"
    rest="${record#*$'\t'}"
    mtime_ns="${rest%%$'\t'*}"
    rest="${rest#*$'\t'}"
    file_size="${rest%%$'\t'*}"
    file_path="${rest#*$'\t'}"
    [[ -f "$file_path" ]] || continue

    chmod u+w -- "$file_path" 2>/dev/null || true
    if rm -f -- "$file_path" 2>/dev/null; then
      deleted_count=$((deleted_count + 1))
      deleted_bytes=$((deleted_bytes + file_size))
      if [[ "$priority" == 0 ]]; then
        deleted_out_of_range=$((deleted_out_of_range + 1))
      else
        deleted_in_range=$((deleted_in_range + 1))
      fi
      log_detail "  Deleted $file_path ($(format_bytes "$file_size"))"
      current_usage=$(disk_usage_percent)
      if [[ -n "$current_usage" ]] && (( current_usage <= ARCHIVE_PRESSURE_TRIGGER_PCT )); then
        break
      fi
    else
      log_warn "Failed to remove emergency archive candidate: $file_path"
    fi
  done <"$candidate_manifest"
  rm -f -- "$candidate_manifest"

  current_usage=$(disk_usage_percent)
  log_info "Emergency PARQUET_LAKE pruning removed ${deleted_count} file(s): outside-range=${deleted_out_of_range}, in-range=${deleted_in_range}."
  log_info "   Freed:      $(format_bytes "$deleted_bytes")"
  log_info "   Disk usage: ${current_usage:-unknown}%"
  if (( deleted_count > 0 )); then
    log_info "Refreshing PARQUET_LAKE consistency report after emergency pruning."
    check_parquet_lake_consistency
  fi
  if [[ -n "$current_usage" ]] && (( current_usage > ARCHIVE_PRESSURE_TRIGGER_PCT )); then
    log_warn "Disk usage remains above ${ARCHIVE_PRESSURE_TRIGGER_PCT}% after all PARQUET_LAKE candidates were considered."
  fi
}


clean_verified_lake_qa_intermediates() {
  if [[ ! -s "$QA_REPROCESSING_SUMMARY" ]]; then
    log_warn "Verified Stage-1 cleanup skipped: QA summary is missing or empty: $QA_REPROCESSING_SUMMARY"
    return 0
  fi

  local qa_cutoff
  qa_cutoff=$(stat -c %Y "$QA_REPROCESSING_SUMMARY" 2>/dev/null || true)
  if [[ -z "$qa_cutoff" ]]; then
    log_warn "Verified Stage-1 cleanup skipped: cannot read QA summary timestamp."
    return 0
  fi

  local total_eligible=0
  local total_deleted=0
  local total_bytes=0
  local station_dir station_name lake_dir step1_dir task_root target_root file file_name file_mtime file_size
  local -a target_roots=()
  local qa_station qa_basename qa_timestamp qa_status qa_rest

  for station_dir in "$STATIONS_BASE"/MINGO0[0-9]; do
    [[ -d "$station_dir" ]] || continue
    station_name=$(basename "$station_dir")
    lake_dir="$station_dir/STAGE_1_PRODUCTS/EVENT_DATA/PARQUET_LAKE"
    step1_dir="$station_dir/STAGE_1/EVENT_DATA/STEP_1"
    [[ -d "$lake_dir" && -d "$step1_dir" ]] || continue

    unset eligible_basenames
    declare -A eligible_basenames=()
    while IFS=, read -r qa_station qa_basename qa_timestamp qa_status qa_rest; do
      [[ "$qa_station" == "$station_name" ]] || continue
      [[ "$qa_status" == "pass" ]] || continue
      [[ "$qa_basename" =~ ^mi0[0-9][0-9]{11}$ ]] || continue
      [[ -f "$lake_dir/postprocessed_${qa_basename}.parquet" ]] || continue
      eligible_basenames["$qa_basename"]=1
    done < <(tail -n +2 "$QA_REPROCESSING_SUMMARY")

    total_eligible=$((total_eligible + ${#eligible_basenames[@]}))
    (( ${#eligible_basenames[@]} > 0 )) || continue

    target_roots=()
    for task_root in "$step1_dir"/TASK_*; do
      [[ -d "$task_root" ]] || continue
      for target_root in "$task_root/INPUT_FILES" "$task_root/OUTPUT_FILES" "$task_root/ANCILLARY"; do
        [[ -d "$target_root" ]] && target_roots+=("$target_root")
      done
    done
    (( ${#target_roots[@]} > 0 )) || continue

    while IFS= read -r -d "" file; do
      file_name=$(basename "$file")
      [[ "$file_name" =~ (mi0[0-9][0-9]{11}) ]] || continue
      qa_basename="${BASH_REMATCH[1]}"
      [[ -n ${eligible_basenames["$qa_basename"]:-} ]] || continue
      file_mtime=$(stat -c %Y "$file" 2>/dev/null || true)
      [[ -n "$file_mtime" && "$file_mtime" -le "$qa_cutoff" ]] || continue
      file_size=$(stat -c %s "$file" 2>/dev/null || printf 0)
      chmod u+w -- "$file" 2>/dev/null || true
      if rm -f -- "$file"; then
        total_deleted=$((total_deleted + 1))
        total_bytes=$((total_bytes + file_size))
      else
        log_warn "Failed to remove verified Stage-1 intermediate: $file"
      fi
    done < <(find "${target_roots[@]}" -type f -print0 2>/dev/null)
  done

  log_info "Lake+QA verified Stage-1 cleanup: eligible basenames=$total_eligible removed files=$total_deleted freed=$(format_bytes "$total_bytes")"
}

clean_completed() {
  local type="completed"
  local -a dirs=()
  local -a final_dirs=()
  local station_dir dir
  if [[ ! -d "$STATIONS_BASE" ]]; then
    log_info "Skipping completed cleanup: $STATIONS_BASE not found."
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    return 0
  fi

  declare -A seen_dirs=()
  add_completed_dir() {
    local candidate="$1"
    [[ -d "$candidate" ]] || return 0
    [[ -n ${seen_dirs["$candidate"]:-} ]] && return 0
    if is_metadata_path "$candidate"; then
      log_warn "Skipping metadata path during completed cleanup: $candidate"
      return 0
    fi
    if [[ "$KEEP_FINAL" == true ]] && is_final_completed_dir "$candidate"; then
      log_info "Keeping final completed directory due to --keep-final: $candidate"
      final_dirs+=("$candidate")
      return 0
    fi
    seen_dirs["$candidate"]=1
    dirs+=("$candidate")
  }

  for station_dir in "$STATIONS_BASE"/*; do
    [[ -d "$station_dir" ]] || continue
    for dir in \
      "$station_dir"/STAGE_1/EVENT_DATA/STEP_1/TASK_*/INPUT_FILES/COMPLETED_DIRECTORY \
      "$station_dir"/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/INPUT_FILES/COMPLETED \
      "$station_dir"/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_1/INPUT_FILES \
      "$station_dir"/STAGE_1/LOG_DATA/STEP_*/INPUT_FILES/COMPLETED \
      "$station_dir"/STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/COMPLETED; do
      add_completed_dir "$dir"
    done
  done

  if (( ${#dirs[@]} == 0 )); then
    log_info "No completed directories found."
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    prune_final_completed_if_needed "${final_dirs[@]}"
    return 0
  fi

  local total_before=0

  for dir in "${dirs[@]}"; do
    log_detail "--> Cleaning $dir"
    chmod -R u+w "$dir" 2>/dev/null || true
    find "$dir" -mindepth 1 -delete 2>/dev/null || true
  done

  # Directories are empty after deletion; after ≈ 0
  local total_after=0
  local freed=$((total_before - total_after))
  TYPE_BEFORE["$type"]=$total_before
  TYPE_AFTER["$type"]=$total_after
  TYPE_FREED["$type"]=$freed
  TYPE_COUNTS["$type"]=${#dirs[@]}

  log_info "Completed directories cleaned: ${#dirs[@]}"
  log_info "   Size accounting skipped for speed."

  prune_final_completed_if_needed "${final_dirs[@]}"
}

clean_step1_queue_sidecars() {
  local -a files=()
  local station_dir task_input_dir queue_dir file
  if [[ ! -d "$STATIONS_BASE" ]]; then
    log_info "Skipping Step-1 queue sidecar cleanup: $STATIONS_BASE not found."
    QUEUE_SIDECAR_BEFORE=0
    QUEUE_SIDECAR_AFTER=0
    QUEUE_SIDECAR_FREED=0
    QUEUE_SIDECAR_COUNT=0
    return 0
  fi

  for station_dir in "$STATIONS_BASE"/*; do
    [[ -d "$station_dir" ]] || continue
    for task_input_dir in "$station_dir"/STAGE_1/EVENT_DATA/STEP_1/TASK_*/INPUT_FILES; do
      [[ -d "$task_input_dir" ]] || continue
      for queue_dir in "$task_input_dir"/UNPROCESSED_DIRECTORY "$task_input_dir"/PROCESSING_DIRECTORY; do
        [[ -d "$queue_dir" ]] || continue
        for file in "$queue_dir"/removed_channel_values_* "$queue_dir"/removed_rows_*; do
          [[ -f "$file" ]] || continue
          files+=("$file")
        done
      done
    done
  done

  if (( ${#files[@]} == 0 )); then
    log_info "No misplaced Step-1 queue sidecars found."
    QUEUE_SIDECAR_BEFORE=0
    QUEUE_SIDECAR_AFTER=0
    QUEUE_SIDECAR_FREED=0
    QUEUE_SIDECAR_COUNT=0
    return 0
  fi

  local total_before
  total_before=$(du -cb "${files[@]}" 2>/dev/null | awk 'END{print $1+0}')

  for file in "${files[@]}"; do
    log_detail "--> Removing misplaced queue sidecar $file"
    chmod u+w "$file" 2>/dev/null || true
    rm -f "$file" 2>/dev/null || true
  done

  QUEUE_SIDECAR_BEFORE=$total_before
  QUEUE_SIDECAR_AFTER=0
  QUEUE_SIDECAR_FREED=$total_before
  QUEUE_SIDECAR_COUNT=${#files[@]}

  log_info "Misplaced Step-1 queue sidecars cleaned: ${#files[@]}"
  log_info "   Size before: $(format_bytes "$QUEUE_SIDECAR_BEFORE")"
  log_info "   Size after:  $(format_bytes "$QUEUE_SIDECAR_AFTER")"
  log_info "   Freed:       $(format_bytes "$QUEUE_SIDECAR_FREED")"
}

clean_cronlogs() {
  local type="cronlogs"
  local dir="$CRON_LOG_DIR"

  if [[ ! -d "$dir" ]]; then
    log_info "Cron logs directory not found: $dir"
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    return 0
  fi

  local before after freed count failed
  before=$(du -sb "$dir" | awk '{print $1}')
  count=0
  failed=0

  log_detail "--> Removing cron log files under $dir; active jobs recreate them only when output exists"
  chmod -R u+w "$dir" >/dev/null 2>&1 || true
  while IFS= read -r -d '' file; do
    if rm -f -- "$file" 2>/dev/null; then
      count=$((count + 1))
    else
      failed=$((failed + 1))
    fi
  done < <(find "$dir" -type f -print0)

  after=$(du -sb "$dir" | awk '{print $1}')
  freed=$((before - after))

  TYPE_BEFORE["$type"]=$before
  TYPE_AFTER["$type"]=$after
  TYPE_FREED["$type"]=$freed
  TYPE_COUNTS["$type"]=${count:-0}

  log_info "Cron logs removed: ${count:-0} file(s)"
  if (( failed > 0 )); then
    log_info "   Failed to remove: ${failed} file(s)"
  fi
  log_info "   Size before: $(format_bytes "$before")"
  log_info "   Size after:  $(format_bytes "$after")"
  log_info "   Freed:       $(format_bytes "$freed")"
}

clean_plots() {
  local type="plots"
  local -a dirs=()
  local station_dir dir
  declare -A seen_dirs=()
  if [[ ! -d "$STATIONS_BASE" ]]; then
    log_info "Skipping plots cleanup: $STATIONS_BASE not found."
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    return 0
  fi

  add_plot_dir() {
    local candidate="$1"
    [[ -d "$candidate" ]] || return 0
    [[ -n ${seen_dirs["$candidate"]:-} ]] && return 0
    if is_metadata_path "$candidate"; then
      log_warn "Skipping metadata path during plots cleanup: $candidate"
      return 0
    fi
    seen_dirs["$candidate"]=1
    dirs+=("$candidate")
  }

  # Avoid a broad find over STATIONS. This cleaner is ancillary and should move
  # quickly even when /home is almost full or station trees contain huge queues.
  for station_dir in "$STATIONS_BASE"/*; do
    [[ -d "$station_dir" ]] || continue
    for dir in \
      "$station_dir"/STAGE_0/REPROCESSING/STEP_*/PLOTS \
      "$station_dir"/STAGE_1/EVENT_DATA/STEP_1/TASK_*/PLOTS \
      "$station_dir"/STAGE_1/EVENT_DATA/STEP_1/TASK_*/PLOTS/DEBUG_PLOTS \
      "$station_dir"/STAGE_2/EVENT_DATA/STEP_1_ACCUMULATION/PLOTS \
      "$station_dir"/STAGE_2/EVENT_DATA/STEP_2_DAILY_EVENT_DATA/TASK_*/PLOTS \
      "$station_dir"/STAGE_1/LOG_DATA/STEP_*/PLOTS; do
      add_plot_dir "$dir"
    done
  done

  # Fallback for future shallow station plot locations without walking large
  # INPUT_FILES/COMPLETED trees.
  for dir in "$STATIONS_BASE"/*/*/*/PLOTS "$STATIONS_BASE"/*/*/*/*/PLOTS "$STATIONS_BASE"/*/*/*/*/*/PLOTS; do
    [[ -n ${seen_dirs["$dir"]:-} ]] && continue
    add_plot_dir "$dir"
  done

  # Post-filter: drop any DEBUG_PLOTS whose parent PLOTS is also in the list
  local -a filtered_dirs=()
  local parent_plot_dir
  for dir in "${dirs[@]}"; do
    if [[ "$dir" == */DEBUG_PLOTS ]]; then
      parent_plot_dir="${dir%/DEBUG_PLOTS}"
      if [[ -n ${seen_dirs["$parent_plot_dir"]:-} ]]; then
        continue
      fi
    fi
    filtered_dirs+=("$dir")
  done
  dirs=("${filtered_dirs[@]}")

  if [[ ! "$PLOTS_KEEP_FRESHEST" =~ ^[0-9]+$ ]]; then
    log_warn "Invalid DATAFLOW_CLEAN_PLOTS_KEEP_FRESHEST=$PLOTS_KEEP_FRESHEST. Falling back to 5."
    PLOTS_KEEP_FRESHEST=5
  fi

  if (( ${#dirs[@]} == 0 )); then
    log_info "No PLOTS directories found."
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    return 0
  fi

  log_info "PLOTS directories discovered: ${#dirs[@]}"
  local total_before=0
  local total_after=0
  local total_freed=0
  local total_deleted=0
  local kept_per_dir=$PLOTS_KEEP_FRESHEST

  for dir in "${dirs[@]}"; do
    if [[ ! -d "$dir" ]]; then
      log_warn "Skipping vanished plots path: $dir"
      continue
    fi
    log_detail "--> Cleaning $dir (keep newest $kept_per_dir file(s))"
    chmod -R u+w "$dir" 2>/dev/null || true

    local -a ranked_entries=()
    local entry path rest file_size dir_before dir_after
    local idx=0
    dir_before=0
    dir_after=0
    while IFS= read -r -d '' entry; do
      ranked_entries+=("$entry")
      rest="${entry#*|}"
      file_size="${rest%%|*}"
      dir_before=$((dir_before + file_size))
    done < <(find "$dir" -type f -printf '%T@|%s|%p\0' 2>/dev/null | sort -z -t '|' -k1,1nr)
    total_before=$((total_before + dir_before))

    if (( ${#ranked_entries[@]} <= kept_per_dir )); then
      total_after=$((total_after + dir_before))
      continue
    fi

    for entry in "${ranked_entries[@]}"; do
      rest="${entry#*|}"
      file_size="${rest%%|*}"
      path="${rest#*|}"
      if (( idx < kept_per_dir )); then
        dir_after=$((dir_after + file_size))
        idx=$((idx + 1))
        continue
      fi
      if rm -f -- "$path" 2>/dev/null; then
        total_deleted=$((total_deleted + 1))
        total_freed=$((total_freed + file_size))
      else
        log_warn "Failed to remove old plot file: $path"
        dir_after=$((dir_after + file_size))
      fi
      idx=$((idx + 1))
    done
    total_after=$((total_after + dir_after))

    # Remove empty subdirectories left after trimming old files.
    find "$dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true
  done

  TYPE_BEFORE["$type"]=$total_before
  TYPE_AFTER["$type"]=$total_after
  TYPE_FREED["$type"]=$total_freed
  TYPE_COUNTS["$type"]=${#dirs[@]}

  log_info "PLOTS directories cleaned: ${#dirs[@]} (kept newest $kept_per_dir file(s) per directory)"
  log_info "   Old files deleted: $total_deleted"
  log_info "   Total before: $(format_bytes "$total_before")"
  log_info "   Total after:  $(format_bytes "$total_after")"
  log_info "   Total freed:  $(format_bytes "$total_freed")"
}

clean_temps() {
  local type="temps"
  local -a roots=("${TEMP_ROOTS[@]}")
  local -a rel_targets=(
    "varData/tmp_mi0*"
    "rawData/dat/removed/*"
    "asci/removed/*"
    "varData/*"
    "rawData/dat/done/*"
  )
  local -a patterns=()
  declare -A seen_bases=()

  for root in "${roots[@]}"; do
    [[ -d "$root" ]] || continue

    local base
    for base in \
      "$root"/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES/system/devices/TRB3/mingo*/data/daqData \
      "$root"/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO*/STAGE_0/*/system/devices/TRB3/mingo*/data/daqData \
      "$root"/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO*/STAGE_0/*/*/system/devices/TRB3/mingo*/data/daqData; do
      [[ -d "$base" ]] || continue
      if [[ -n ${seen_bases["$base"]:-} ]]; then
        continue
      fi
      seen_bases["$base"]=1
      for rel in "${rel_targets[@]}"; do
        patterns+=("$base/$rel")
      done
    done
  done

  if (( ${#patterns[@]} == 0 )); then
    log_info "No Stage_0 data buffers found under DATAFLOW_v3 or SAFE_DATAFLOW_v3."
    TYPE_BEFORE["$type"]=0
    TYPE_AFTER["$type"]=0
    TYPE_FREED["$type"]=0
    TYPE_COUNTS["$type"]=0
    return 0
  fi

  declare -A seen_paths=()
  local total_before=0
  local total_after=0
  local removed=0

  for pattern in "${patterns[@]}"; do
    while IFS= read -r match; do
      [[ -n "$match" ]] || continue
      if [[ -n ${seen_paths["$match"]:-} ]]; then
        continue
      fi
      seen_paths["$match"]=1

      if [[ ! -e "$match" ]]; then
        continue
      fi
      if is_metadata_path "$match"; then
        log_warn "Skipping metadata path during temp cleanup: $match"
        continue
      fi

      local before after delta
      before=$(du -sb "$match" | awk '{print $1}')
      total_before=$((total_before + before))
      log_detail "--> Removing $match"
      chmod -R u+w "$match" >/dev/null 2>&1 || true
      if ! rm -rf -- "$match"; then
        log_warn "unable to remove $match (check permissions)"
      fi
      if [[ ! -e "$match" ]]; then
        ((++removed))
      fi

      if [[ -e "$match" ]]; then
        after=$(du -sb "$match" | awk '{print $1}')
      else
        after=0
      fi
      total_after=$((total_after + after))
      delta=$((before - after))
      log_detail "   Freed $(format_bytes "$delta")"
      if [[ -e "$match" ]]; then
        log_warn "Item still present after cleanup: $match"
      fi
    done < <(compgen -G "$pattern" || true)
  done

  local freed=$((total_before - total_after))
  TYPE_BEFORE["$type"]=$total_before
  TYPE_AFTER["$type"]=$total_after
  TYPE_FREED["$type"]=$freed
  TYPE_COUNTS["$type"]=$removed

  if (( removed == 0 )); then
    log_info "No temporary files found to delete."
  else
    log_info "Temporary artefacts removed: $removed item(s)"
    log_info "   Total before: $(format_bytes "$total_before")"
    log_info "   Total after:  $(format_bytes "$total_after")"
    log_info "   Total freed:  $(format_bytes "$freed")"
  fi
}

lock_file_key() {
  local path="$1"
  local key
  key=$(stat -Lc '%t:%T:%i' "$path" 2>/dev/null || true)
  [[ -n "$key" ]] || return 1
  printf '%s' "$key"
}

lock_holder_pid() {
  local path="$1"
  local key inode pid
  key=$(lock_file_key "$path") || return 1
  pid=$(awk -v key="$key" '$6 == key {print $5; exit}' /proc/locks 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    printf '%s' "$pid"
    return 0
  fi
  inode="${key##*:}"
  awk -v inode="$inode" '$2 == "FLOCK" && $6 ~ ":" inode "$" {print $5; exit}' /proc/locks 2>/dev/null || true
}

process_command_line() {
  local pid="$1"
  if [[ -r "/proc/$pid/cmdline" ]]; then
    tr '\0' ' ' <"/proc/$pid/cmdline" | sed 's/[[:space:]]*$//'
  else
    ps -p "$pid" -o args= 2>/dev/null || true
  fi
}

wait_for_process_exit() {
  local pid="$1"
  local attempts="${2:-10}"
  local i
  for ((i = 0; i < attempts; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

process_descendants() {
  local pid="$1"
  local child
  while IFS= read -r child; do
    [[ -n "$child" ]] || continue
    process_descendants "$child"
    printf '%s\n' "$child"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
}

terminate_process_tree() {
  local pid="$1"
  local -a targets=()
  local target
  while IFS= read -r target; do
    [[ -n "$target" ]] || continue
    targets+=("$target")
  done < <(process_descendants "$pid")
  targets+=("$pid")

  kill -TERM "${targets[@]}" 2>/dev/null || true
  if wait_for_process_exit "$pid" 2; then
    return 0
  fi

  log_warn "PID $pid did not exit after TERM. Sending KILL to lock holder process tree."
  kill -KILL "${targets[@]}" 2>/dev/null || true
  wait_for_process_exit "$pid" 2
}

FORCE=false
KEEP_FINAL=false
KILL_LOCK_HOLDER=false
THRESHOLD=$(validate_threshold "50")
declare -a SELECTION_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -f|--force)
      FORCE=true
      shift
      ;;
    -c|--compact)
      COMPACT=true
      shift
      ;;
    --keep-final)
      KEEP_FINAL=true
      shift
      ;;
    --kill-lock-holder)
      KILL_LOCK_HOLDER=true
      shift
      ;;
    -t|--threshold)
      if [[ $# -lt 2 ]]; then
        echo "Option --threshold requires a value." >&2
        exit 1
      fi
      THRESHOLD=$(validate_threshold "$2")
      shift 2
      ;;
    -s|--select)
      if [[ $# -lt 2 ]]; then
        echo "Option --select requires a value." >&2
        exit 1
      fi
      SELECTION_ARGS+=("$2")
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

declare -a SELECTED_TYPES=()
declare -A SEEN_TYPES=()

if ((${#SELECTION_ARGS[@]} == 0)); then
  if [[ "$FORCE" == true ]]; then
    for type in "${FORCE_DEFAULT_SELECTION[@]}"; do
      SELECTED_TYPES+=("$type")
      SEEN_TYPES["$type"]=1
    done
  else
    for type in "${DEFAULT_SELECTION[@]}"; do
      SELECTED_TYPES+=("$type")
      SEEN_TYPES["$type"]=1
    done
  fi
else
  for entry in "${SELECTION_ARGS[@]}"; do
    IFS=',' read -ra tokens <<<"$entry"
    for token in "${tokens[@]}"; do
      token=${token,,}
      token=${token// /}
      [[ -z "$token" ]] && continue
      if [[ "$token" == "all" ]]; then
        for t in "${DEFAULT_SELECTION[@]}"; do
          if [[ -z ${SEEN_TYPES["$t"]:-} ]]; then
            SELECTED_TYPES+=("$t")
            SEEN_TYPES["$t"]=1
          fi
        done
        continue
      fi
      if [[ -z ${VALID_TYPES["$token"]:-} ]]; then
        echo "Unknown value for --select: $token" >&2
        exit 1
      fi
      if [[ -z ${SEEN_TYPES["$token"]:-} ]]; then
        SELECTED_TYPES+=("$token")
        SEEN_TYPES["$token"]=1
      fi
    done
  done
  if ((${#SELECTED_TYPES[@]} == 0)); then
    for type in "${DEFAULT_SELECTION[@]}"; do
      SELECTED_TYPES+=("$type")
      SEEN_TYPES["$type"]=1
    done
  fi
fi

# Acquire exclusive lock to prevent concurrent runs (LOCK_FILE was declared above)
if ! { exec {LOCK_FD}>"$LOCK_FILE"; } 2>/dev/null; then
  log_warn "Cannot open lock file: $LOCK_FILE"
  exit 1
fi
if ! flock -n "$LOCK_FD"; then
  holder_pid="$(lock_holder_pid "$LOCK_FILE")"
  if [[ -n "$holder_pid" ]]; then
    holder_cmd="$(process_command_line "$holder_pid")"
    log_warn "Another clean_dataflow instance is already running."
    log_warn "   Lock file: $LOCK_FILE"
    log_warn "   Holder PID: $holder_pid"
    if [[ -n "$holder_cmd" ]]; then
      log_warn "   Holder command: $holder_cmd"
    fi
  else
    log_warn "Another process holds the clean_dataflow lock, but the holder PID could not be identified."
    log_warn "   Lock file: $LOCK_FILE"
  fi

  if [[ "$KILL_LOCK_HOLDER" != true ]]; then
    log_warn "Exiting without cleaning. Re-run with --kill-lock-holder to terminate the holder and continue."
    exit 0
  fi

  if [[ -z "$holder_pid" ]]; then
    log_warn "--kill-lock-holder was requested, but no holder PID was found. Refusing to remove a possibly active lock."
    exit 1
  fi

  log_warn "--kill-lock-holder requested. Terminating lock holder PID $holder_pid and its children."
  if ! terminate_process_tree "$holder_pid"; then
    log_warn "PID $holder_pid is still present after KILL. Refusing to continue."
    exit 1
  fi

  exec {LOCK_FD}>&-
  rm -f "$LOCK_FILE" 2>/dev/null || true
  if ! { exec {LOCK_FD}>"$LOCK_FILE"; } 2>/dev/null; then
    log_warn "Cannot recreate lock file: $LOCK_FILE"
    exit 1
  fi
  if ! flock -n "$LOCK_FD"; then
    log_warn "Lock is still held after killing PID $holder_pid. Refusing to continue."
    exit 1
  fi
  log_warn "Previous lock holder stopped; continuing with cleanup."
fi
trap 'flock -u "$LOCK_FD" 2>/dev/null || true; rm -f "$LOCK_FILE" 2>/dev/null || true' EXIT

log_info "Selected cleanups: $(join_by ', ' "${SELECTED_TYPES[@]}")"
if [[ "$KEEP_FINAL" == true ]]; then
  log_info "Keep-final flag enabled: STEP_1/TASK_*/INPUT_FILES/COMPLETED_DIRECTORY contents will be preserved."
  log_info "Emergency keep-final policy: if /home usage rises above ${KEEP_FINAL_TRIGGER_PCT}%, prune oldest final completed files until ${KEEP_FINAL_TARGET_PCT}%."
fi
log_info "Disk usage before cleaning: $(disk_usage_summary)"
log_info ""
log_info "=== Checking persistent PARQUET_LAKE archives ==="
check_parquet_lake_consistency

if [[ "$FORCE" == true ]]; then
  if ((${#SELECTION_ARGS[@]} == 0)); then
    log_info "Force default selection active: $(join_by ', ' "${FORCE_DEFAULT_SELECTION[@]}")"
  fi
  log_info "Force flag enabled; skipping disk usage threshold check."
else
  usage_percent=$(disk_usage_percent)
  if [[ -z "$usage_percent" ]]; then
    echo "Unable to determine disk usage for /home." >&2
    exit 1
  fi
  log_info "Threshold: ${THRESHOLD}%"
  should_clean=$(awk -v usage="$usage_percent" -v threshold="$THRESHOLD" 'BEGIN{usage+=0; threshold+=0; if (usage >= threshold) print 1; else print 0}')
  if [[ "$should_clean" -eq 0 ]]; then
    log_info "Disk usage ${usage_percent}% is below the threshold (${THRESHOLD}%). Use --force to override."
    exit 0
  fi
  log_info "Disk usage ${usage_percent}% exceeds threshold ${THRESHOLD}%. Proceeding with cleanup."
fi

log_info ""
log_info "=== Cleaning misplaced Step-1 queue sidecars ==="
clean_step1_queue_sidecars

for type in "${SELECTED_TYPES[@]}"; do
  log_info ""
  case "$type" in
    temps)
      log_info "=== Cleaning Stage-0 temporary buffers ==="
      clean_temps
      ;;
    plots)
      log_info "=== Cleaning plot exports ==="
      clean_plots
      ;;
    completed)
      log_info "=== Cleaning lake-backed QA-passed Stage-1 intermediates ==="
      clean_verified_lake_qa_intermediates
      log_info "=== Cleaning COMPLETED_DIRECTORY exports ==="
      clean_completed
      ;;
    cronlogs)
      log_info "=== Cleaning cron execution logs ==="
      clean_cronlogs
      ;;
  esac
done

overall_before=0
overall_after=0

for type in "${SELECTED_TYPES[@]}"; do
  before=${TYPE_BEFORE["$type"]:-0}
  after=${TYPE_AFTER["$type"]:-0}
  overall_before=$((overall_before + before))
  overall_after=$((overall_after + after))
done
overall_before=$((overall_before + QUEUE_SIDECAR_BEFORE))
overall_after=$((overall_after + QUEUE_SIDECAR_AFTER))

overall_freed=$((overall_before - overall_after))

log_info ""
log_info "Summary:"
log_info "  - Step-1 queue sidecars: $(format_bytes "$QUEUE_SIDECAR_FREED") freed across ${QUEUE_SIDECAR_COUNT} item(s)"
for type in "${SELECTED_TYPES[@]}"; do
  label=$(label_for_type "$type")
  freed=${TYPE_FREED["$type"]:-0}
  count=${TYPE_COUNTS["$type"]:-0}
  log_info "  - ${label}: $(format_bytes "$freed") freed across ${count} item(s)"
done
log_info "  Total reclaimed: $(format_bytes "$overall_freed")"


# Clean SIMULATION_DATA_JUNK MINGO_DIGITAL_TWIN runtime directories.
if [[ -d "$SIM_JUNK_BASE" ]]; then
  log_info "Cleaning SIMULATION_DATA_JUNK/*/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS directories..."
  count=0
  freed=0
  while IFS= read -r -d '' dir; do
    if [[ -d "$dir" ]]; then
      size_before=$(du -sb "$dir" 2>/dev/null | awk '{print $1}')
      rm -rf "$dir" 2>/dev/null || true
      count=$((count + 1))
      freed=$((freed + size_before))
      log_detail "  Removed $dir ($(format_bytes "$size_before"))"
    fi
  done < <(find "$SIM_JUNK_BASE" -mindepth 4 -maxdepth 4 -type d -path '*/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/INTERSTEPS' -print0 2>/dev/null)
  log_info "  - SIMULATION_DATA_JUNK INTERSTEPS: $(format_bytes "$freed") freed across $count item(s)"

  log_info "Cleaning SIMULATION_DATA_JUNK/*/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES directories..."
  count=0
  freed=0
  while IFS= read -r -d '' dir; do
    if [[ -d "$dir" ]]; then
      size_before=$(du -sb "$dir" 2>/dev/null | awk '{print $1}')
      rm -rf "$dir" 2>/dev/null || true
      count=$((count + 1))
      freed=$((freed + size_before))
      log_detail "  Removed $dir ($(format_bytes "$size_before"))"
    fi
  done < <(find "$SIM_JUNK_BASE" -mindepth 5 -maxdepth 5 -type d -path '*/MINGO_DIGITAL_TWIN/SIMULATION_OUTPUTS/SIMULATED_DATA/FILES' -print0 2>/dev/null)
  log_info "  - SIMULATION_DATA_JUNK SIMULATION_OUTPUTS/SIMULATED_DATA/FILES: $(format_bytes "$freed") freed across $count item(s)"
else
  log_info "SIMULATION_DATA_JUNK base directory not found: $SIM_JUNK_BASE"
fi

# Emergency archive pruning is allowed only above 95%, with range-aware prioritization.
run_archive_emergency_cleanup

log_info ""
log_info "Disk usage after cleaning: $(disk_usage_summary)"
