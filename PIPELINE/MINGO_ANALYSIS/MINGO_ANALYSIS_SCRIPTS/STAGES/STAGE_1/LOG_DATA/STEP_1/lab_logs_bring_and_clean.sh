#!/bin/bash

# Resolve the checkout from this script's location when the caller did not provide it.
if [[ -z "${DATAFLOW_ROOT:-}" ]]; then
  _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
    _repo_probe="$(dirname -- "$_repo_probe")"
  done
  if [[ -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh"
  else
    echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  fi
fi
unset _repo_probe
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/LOG_DATA/STEP_1/lab_logs_bring_and_clean.sh
# Purpose: Only this changes between mingos and computers.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/LOG_DATA/STEP_1/lab_logs_bring_and_clean.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# ----------------------------------------------
# Only this changes between mingos and computers
if [[ ${1:-} =~ ^(-h|--help)$ ]]; then
  cat <<'EOF'
lab_logs_bring_and_clean.sh
Pulls lab log files from a station, cleans new ones, and stages them for STEP_2.

Usage:
  lab_logs_bring_and_clean.sh [-a|--all] <station>

Options:
  -a, --all    Re-clean files already marked as completed.
  -h, --help    Show this help message and exit.

Pass the station number (1-4). The script fetches raw logs via rsync, runs the
cleaner, and keeps a record of processed files so they are not re-cleaned unless
the --all flag is provided.
EOF
  exit 0
fi

include_completed=false
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--all)
      include_completed=true
      shift
      ;;
    -h|--help)
      cat <<'EOF'
lab_logs_bring_and_clean.sh
Pulls lab log files from a station, cleans new ones, and stages them for STEP_2.

Usage:
  lab_logs_bring_and_clean.sh [-a|--all] <station>

Options:
  -a, --all    Re-clean files already marked as completed.
  -h, --help   Show this help message and exit.
EOF
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

if [[ ${#args[@]} -lt 1 ]]; then
  echo "Error: No station provided."
  echo "Usage: $0 [-a|--all] <station>"
  exit 1
fi

station=${args[0]}
echo "Station: $station"

log_info() {
  echo "[INFO] $*"
}

log_warn() {
  echo "[WARN] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

if [[ ! "$station" =~ ^[1-4]$ ]]; then
  log_error "Invalid station number. Please provide a number between 1 and 4."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "${MASTER_DIR}" != "/" && "$(basename "${MASTER_DIR}")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
  MASTER_DIR="$(dirname "${MASTER_DIR}")"
done
# STATUS_HELPER="${MASTER_DIR}/SUPPORT/SHARED_CODE/status_csv.py"
# STATUS_TIMESTAMP=""
# STATUS_CSV=""

LAB_LOGS_CONFIG_SHARED="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/LOG_DATA/config_lab_logs.yaml"
LAB_LOGS_CONFIG_STEP1="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/LOG_DATA/STEP_1/config_step_1.yaml"
LAB_LOGS_COLUMN_COUNTS_CSV="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/LOG_DATA/STEP_1/config_step_1.csv"

is_lab_logs_station_enabled() {
  local station_id="$1"
  local decision
  decision=$(python3 - "$station_id" "$LAB_LOGS_CONFIG_SHARED" "$LAB_LOGS_CONFIG_STEP1" <<'PY' || true
import sys
from pathlib import Path
import os

station_raw, shared_cfg, step_cfg = sys.argv[1:4]

try:
    station_id = int(str(station_raw).strip())
except Exception:
    print("1")
    raise SystemExit(0)

repo_root = Path(os.environ["DATAFLOW_ROOT"])
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

try:
    from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import load_selection_for_paths, station_is_selected
    selection = load_selection_for_paths(
        [shared_cfg, step_cfg],
        master_config_root=repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES",
    )
    print("1" if station_is_selected(station_id, selection.stations) else "0")
except Exception:
    print("1")
PY
  )
  [[ "$decision" != "0" ]]
}

if ! is_lab_logs_station_enabled "$station"; then
  echo "Skipping station ${station}: disabled by selection.stations."
  exit 0
fi

date_range_filter_enabled=false
declare -a date_ranges_start_epochs=()
declare -a date_ranges_end_epochs=()
declare -a date_ranges_display_pairs=()

load_lab_logs_date_ranges() {
  local result
  if ! result=$(python3 - "$LAB_LOGS_CONFIG_SHARED" "$LAB_LOGS_CONFIG_STEP1" "$station" <<'PY'
import sys
import shlex
from pathlib import Path
import os

shared_path = sys.argv[1]
step_path = sys.argv[2]
station_raw = sys.argv[3]

repo_root = Path(os.environ["DATAFLOW_ROOT"])
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

epochs = ""
labels = ""
try:
    from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import (
        load_selection_for_paths,
        serialize_date_ranges_for_shell,
    )

    selection = load_selection_for_paths(
        [shared_path, step_path],
        master_config_root=repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES",
    )
    from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import effective_date_ranges_for_station

    ranges = effective_date_ranges_for_station(station_raw, selection)
    epochs, labels = serialize_date_ranges_for_shell(ranges)
except Exception:
    pass

print(f"LAB_LOGS_DATE_RANGES_EPOCHS={shlex.quote(epochs)}")
print(f"LAB_LOGS_DATE_RANGES_LABELS={shlex.quote(labels)}")
PY
  ); then
    return 0
  fi

  eval "$result"
  local serialized="${LAB_LOGS_DATE_RANGES_EPOCHS:-}"
  local labels="${LAB_LOGS_DATE_RANGES_LABELS:-}"
  date_ranges_start_epochs=()
  date_ranges_end_epochs=()
  date_ranges_display_pairs=()
  date_range_filter_enabled=false

  if [[ -n "$serialized" ]]; then
    local -a epoch_chunks=()
    local -a label_chunks=()
    IFS=';' read -r -a epoch_chunks <<< "$serialized"
    IFS=';' read -r -a label_chunks <<< "$labels"
    local idx
    for idx in "${!epoch_chunks[@]}"; do
      local chunk="${epoch_chunks[idx]}"
      [[ -z "$chunk" || "$chunk" != *,* ]] && continue
      local start_epoch="${chunk%%,*}"
      local end_epoch="${chunk#*,}"
      [[ -n "$start_epoch" && ! "$start_epoch" =~ ^[0-9]+$ ]] && continue
      [[ -n "$end_epoch" && ! "$end_epoch" =~ ^[0-9]+$ ]] && continue
      [[ -z "$start_epoch" && -z "$end_epoch" ]] && continue
      date_ranges_start_epochs+=("$start_epoch")
      date_ranges_end_epochs+=("$end_epoch")

      local label_chunk="${label_chunks[idx]:-}"
      local start_label=""
      local end_label=""
      if [[ "$label_chunk" == *"|"* ]]; then
        start_label="${label_chunk%%|*}"
        end_label="${label_chunk#*|}"
      fi
      [[ -z "$start_label" ]] && start_label="-inf"
      [[ -z "$end_label" ]] && end_label="+inf"
      date_ranges_display_pairs+=("${start_label} to ${end_label}")
    done
  fi

  if (( ${#date_ranges_start_epochs[@]} > 0 )); then
    date_range_filter_enabled=true
    local range_display
    range_display="$(printf '%s; ' "${date_ranges_display_pairs[@]}")"
    range_display="${range_display%; }"
    log_info "Date range filtering enabled (${#date_ranges_start_epochs[@]} interval(s)): ${range_display}."
  fi
}

filename_matches_date_ranges() {
  local file_path="$1"
  if ! $date_range_filter_enabled; then
    return 0
  fi

  local base_name="${file_path##*/}"
  if [[ ! "$base_name" =~ ([0-9]{4}-[0-9]{2}-[0-9]{2}) ]]; then
    return 1
  fi

  local ymd="${BASH_REMATCH[1]}"
  local file_day_start_epoch file_day_end_epoch
  file_day_start_epoch=$(date -u -d "${ymd} 00:00:00" +%s 2>/dev/null) || return 1
  file_day_end_epoch=$(date -u -d "${ymd} 23:59:59" +%s 2>/dev/null) || return 1

  local idx
  for idx in "${!date_ranges_start_epochs[@]}"; do
    local start_epoch="${date_ranges_start_epochs[idx]}"
    local end_epoch="${date_ranges_end_epochs[idx]}"
    if [[ -n "$start_epoch" && "$file_day_end_epoch" -lt "$start_epoch" ]]; then
      continue
    fi
    if [[ -n "$end_epoch" && "$file_day_start_epoch" -gt "$end_epoch" ]]; then
      continue
    fi
    return 0
  done
  return 1
}

declare -A COLUMN_COUNTS=(
  ["Flow0_"]=5
  ["hv0_"]=22
  ["Odroid_"]=4
  ["rates_"]=12
  ["sensors_bus0_"]=8
  ["sensors_bus1_"]=8
)

load_column_counts_config() {
  local cfg="$LAB_LOGS_COLUMN_COUNTS_CSV"
  [[ -f "$cfg" ]] || return 0
  local header_seen=false
  while IFS=',' read -r prefix expected _rest; do
    prefix="${prefix//$'\r'/}"
    expected="${expected//$'\r'/}"
    if ! $header_seen; then
      header_seen=true
      if [[ "${prefix,,}" == "prefix" ]]; then
        continue
      fi
    fi
    [[ -z "$prefix" || -z "$expected" ]] && continue
    [[ ! "$expected" =~ ^[0-9]+$ ]] && continue
    COLUMN_COUNTS["$prefix"]="$expected"
  done < "$cfg"
}

load_lab_logs_date_ranges
load_column_counts_config

# ----------------------------------------------

# Additional paths
mingo_direction="mingo0$station"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
RSYNC_RSH_CMD="ssh -o BatchMode=yes -o ConnectTimeout=15"

LAB_LOGS_ROOT="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0${station}/STAGE_1/LOG_DATA"
STEP1_ROOT="${LAB_LOGS_ROOT}/STEP_1"
STEP1_INPUT="${STEP1_ROOT}/INPUT_FILES"
STEP1_INPUT_UNPROCESSED="${STEP1_INPUT}/UNPROCESSED"
STEP1_INPUT_COMPLETED="${STEP1_INPUT}/COMPLETED"
STEP1_OUTPUT="${STEP1_ROOT}/OUTPUT_FILES"

mkdir -p "${STEP1_ROOT}" "${STEP1_INPUT_UNPROCESSED}" "${STEP1_INPUT_COMPLETED}" "${STEP1_OUTPUT}"

# STATUS_CSV="${STEP1_ROOT}/log_bring_and_clean_status.csv"
# if ! STATUS_TIMESTAMP="$(python3 "$STATUS_HELPER" append "$STATUS_CSV")"; then
#   echo "Warning: unable to record status in $STATUS_CSV" >&2
#   STATUS_TIMESTAMP=""
# fi

# finish() {
#   local exit_code="$1"
#   if [[ ${exit_code} -eq 0 && -n "${STATUS_TIMESTAMP:-}" && -n "${STATUS_CSV:-}" ]]; then
#     python3 "$STATUS_HELPER" complete "$STATUS_CSV" "$STATUS_TIMESTAMP" >/dev/null 2>&1 || true
#   fi
# }

# trap 'finish $?' EXIT

local_destination="${STEP1_INPUT_UNPROCESSED}"
OUTPUT_DIR="${STEP1_OUTPUT}"
rsync_file_list=""
filtered_rsync_file_list=""
fetch_status="not-run"

cleanup_tmp_files() {
    [[ -n "$rsync_file_list" ]] && rm -f "$rsync_file_list"
    [[ -n "$filtered_rsync_file_list" ]] && rm -f "$filtered_rsync_file_list"
}
trap cleanup_tmp_files EXIT


echo '--------------------------- bash script starts ---------------------------'

# Sync data from the remote server
declare -A SEEN_RELATIVE_PATHS

if [[ -d "${STEP1_INPUT_UNPROCESSED}" ]]; then
    while IFS= read -r -d '' file; do
        rel="${file#${STEP1_INPUT_UNPROCESSED}/}"
        [[ -n "$rel" ]] || continue
        SEEN_RELATIVE_PATHS["$rel"]=1
    done < <(find "${STEP1_INPUT_UNPROCESSED}" -type f -print0 2>/dev/null || true)
fi

if [[ -d "${STEP1_INPUT_COMPLETED}" ]]; then
    while IFS= read -r -d '' file; do
        rel="${file#${STEP1_INPUT_COMPLETED}/}"
        [[ -n "$rel" ]] || continue
        SEEN_RELATIVE_PATHS["$rel"]=1
    done < <(find "${STEP1_INPUT_COMPLETED}" -type f -print0 2>/dev/null || true)
fi

rsync_file_list=$(mktemp)
filtered_rsync_file_list=$(mktemp)

remote_find_cmd=$(printf 'cd %q && find . -type f -name %s -printf %s' \
  "/home/rpcuser/logs" "'*.log'" "'%P\0'")

if ssh "${SSH_OPTS[@]}" "$mingo_direction" "$remote_find_cmd" > "$rsync_file_list"; then
    if [[ -s "$rsync_file_list" ]]; then
        : > "$filtered_rsync_file_list"
        while IFS= read -r -d '' candidate; do
            candidate=${candidate//$'\r'/}
            candidate=${candidate#./}
            [[ -z "$candidate" ]] && continue

            local_name="${candidate##*/}"
            if [[ "$local_name" == clean_* || "$local_name" == merged_* ]]; then
                continue
            fi
            if [[ "$candidate" == done/clean_* || "$candidate" == done/merged_* ]]; then
                continue
            fi
            if [[ -n ${SEEN_RELATIVE_PATHS["$candidate"]+_} ]]; then
                continue
            fi
            if ! filename_matches_date_ranges "$candidate"; then
                continue
            fi
            printf '%s\0' "$candidate" >> "$filtered_rsync_file_list"
        done < "$rsync_file_list"

        if [[ -s "$filtered_rsync_file_list" ]]; then
            if ! RSYNC_RSH="$RSYNC_RSH_CMD" rsync -avz --ignore-existing \
                --files-from="$filtered_rsync_file_list" \
                --from0 \
                "$mingo_direction:/home/rpcuser/logs/" "${local_destination}/"; then
                fetch_status="rsync-error"
                log_warn "rsync encountered an error while fetching lab logs."
            else
                fetch_status="transferred"
            fi
        else
            fetch_status="no-eligible-files"
            log_info "No .log files eligible for transfer after filters."
        fi
    else
        fetch_status="no-remote-files"
        log_info "No .log files found to transfer."
    fi
else
    fetch_status="remote-list-error"
    log_warn "unable to list remote lab logs from ${mingo_direction}."
fi

case "$fetch_status" in
    transferred)
        log_info "Received lab log data from ${mingo_direction}."
        ;;
    no-eligible-files)
        log_info "Remote lab log directory is reachable, but no files matched the local filters."
        ;;
    no-remote-files)
        log_info "Remote lab log directory is reachable, but it currently contains no .log files."
        ;;
    rsync-error|remote-list-error)
        log_error "LAB_LOGS fetch failed for ${mingo_direction}."
        exit 1
        ;;
esac

move_to_completed() {
    local file_path=$1
    if [[ "${file_path}" != "${STEP1_INPUT_UNPROCESSED}/"* ]]; then
        return
    fi
    local relative_path="${file_path#${STEP1_INPUT_UNPROCESSED}/}"
    local destination="${STEP1_INPUT_COMPLETED}/${relative_path}"
    mkdir -p "$(dirname "$destination")"
    if [[ -e "$destination" ]]; then
        rm -f "$destination"
    fi
    mv "$file_path" "$destination"
}

process_file() {
    local file=$1
    local move_after=$2
    local filename=$(basename "$file")

    if ! filename_matches_date_ranges "$filename"; then
        return
    fi

    local output_file="$OUTPUT_DIR/$filename"

    # Check if the file needs to be processed
    if [[ -f "$output_file" ]]; then
        # Compare modification timestamps
        local source_mtime=$(stat -c %Y "$file")
        local processed_mtime=$(stat -c %Y "$output_file")
        
        #source_mtime_save=$(stat -c %Y "$file")
        #processed_mtime_save=$(stat -c %Y "$output_file")
        
        if [[ $source_mtime -le $processed_mtime ]]; then
            #echo "File $filename is already processed and up-to-date. Skipping."
            if [[ "${move_after}" == "1" ]]; then
                move_to_completed "$file"
            fi
            return
        fi
    fi

    # Process the file
    for prefix in "${!COLUMN_COUNTS[@]}"; do
        if [[ $filename == $prefix* ]]; then
            local column_count=${COLUMN_COUNTS[$prefix]}
            awk -v col_count=$column_count -v output_file="$output_file" -v file="$file" '
		    BEGIN { OFS=" "; invalid_count=0; valid_count=0 }
		    {
			  gsub(/T/, " ", $1);      # Replace T with space
			  gsub(/[,;]/, " ");       # Replace commas and semicolons with space
			  gsub(/  +/, " ");        # Replace multiple spaces with a single space
			  if (NF >= col_count) {   # Keep rows with at least the expected number of fields
				valid_count++;
				print $0 > output_file
			  } else {
				invalid_count++;
			  }
		    }
		    END {
			  if (invalid_count > 0) {   # Only print the message if invalid rows were found
				print "Processed: " valid_count " valid rows, " invalid_count " discarded rows." > "/dev/stderr"
				print "Processed " file " into " output_file > "/dev/stderr"
			  }
		    }
	' "$file"
            
            #echo "Processed $file into $output_file."
	#echo $source_mtime_save
	#echo $processed_mtime_save
	#echo '-------------------'
            if [[ "${move_after}" == "1" && "${file}" == "${STEP1_INPUT_UNPROCESSED}/"* ]]; then
                move_to_completed "$file"
            fi
            return
        fi
    done

    #echo "Unknown file prefix: $filename. Skipping $file."
}

process_directory() {
    local dir=$1
    local move_after=$2
    [[ -d "$dir" ]] || return

    while IFS= read -r -d '' file; do
        process_file "$file" "$move_after"
    done < <(find "$dir" -type f -print0)
}

process_directory "${STEP1_INPUT_UNPROCESSED}" "1"

if [[ "${include_completed}" == true ]]; then
    process_directory "${STEP1_INPUT_COMPLETED}" "0"
fi

# Clean up any empty directories left in UNPROCESSED after moving files
cleanup_empty_dirs() {
    local base_dir=$1
    [[ -d "$base_dir" ]] || return
    find "$base_dir" -type d -empty -delete 2>/dev/null || true
}

cleanup_empty_dirs "${STEP1_INPUT_UNPROCESSED}"
echo "Files cleaned into $OUTPUT_DIR"

echo '------------------------------------------------------'
echo "log_bring_and_clean.sh completed on: $(date '+%Y-%m-%d %H:%M:%S')"
echo '------------------------------------------------------'
