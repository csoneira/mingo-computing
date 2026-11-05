#!/usr/bin/env bash

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
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_1/bring_reprocessing_files.sh
# Purpose: bring_reprocessing_files.sh.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_1/bring_reprocessing_files.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# ---------------------------------------------------------------------------
# bring_reprocessing_files.sh
#   Fetch HLD data from backuplip, writing
#     * *.hld.tar.gz or *.hld-tar-gz  --> STAGE_0/REPROCESSING/INPUT_FILES/COMPRESSED_HLDS
#     * *.hld                         --> STAGE_0/REPROCESSING/INPUT_FILES/UNCOMPRESSED_HLDS
# ---------------------------------------------------------------------------

set -e  # Exit on command failure
set -u  # Error on undefined variables
set -o pipefail  # Fail on any part of a pipeline

log_info() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log_warn() {
  printf '[%s] [WARN] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "${MASTER_DIR}" != "/" && "$(basename "${MASTER_DIR}")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
  MASTER_DIR="$(dirname "${MASTER_DIR}")"
done
REPO_ROOT="$(dirname "$(dirname "${MASTER_DIR}")")"
# STATUS_HELPER="${MASTER_DIR}/common/status_csv.py"
# STATUS_TIMESTAMP=""

# finish() {
#   local exit_code="$1"
#   if [[ ${exit_code} -eq 0 && -n "${STATUS_TIMESTAMP:-}" && -n "${STATUS_CSV:-}" ]]; then
#     python3 "$STATUS_HELPER" complete "$STATUS_CSV" "$STATUS_TIMESTAMP" >/dev/null 2>&1 || true
#   fi
# }
# trap 'finish $?' EXIT

##############################################################################
# Parse arguments
##############################################################################
usage() {
  cat <<'EOF'
Usage:
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot]
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] --random|-r
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] --newest|-n
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] <start YYMMDD> <end YYMMDD>

Options:
  -h, --help            Show this help message and exit.
  -r, --random          Select a single random basename from metadata and download it.
  -n, --newest          Select the newest (lexicographically last) unprocessed basename.
  -m, --refresh-metadata
                        Refresh the metadata CSV with the latest list of basenames
                        from the remote host. Can be combined with --random or a
                        date range, or used alone.
      --plot            Generate a histogram (PDF) of time differences between
                        consecutive metadata entries in STEP_1/PLOTS. Can be run
                        by itself using the existing metadata CSV or combined
                        with other flags.
EOF
  exit 1
}

if [[ ${1:-} =~ ^(-h|--help)$ ]]; then
  cat <<'EOF'
bring_reprocessing_files.sh
Fetches HLD data from backuplip into the STAGE_0 buffers for a station.

Usage:
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot]
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] --random/-r
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] --newest/-n
  bring_reprocessing_files.sh <station> [--refresh-metadata|-m] [--plot] YYMMDD YYMMDD

Options:
  -h, --help            Show this help message and exit.
  -r, --random          Select a single random basename from metadata and download it.
  -n, --newest          Select the newest (lexicographically last) unprocessed basename.
  -m, --refresh-metadata
                        Refresh the metadata CSV with the latest list of basenames
                        from the remote host. Can be combined with --random or a
                        date range, or used alone.
      --plot            Generate a histogram (PDF) of time differences between
                        consecutive metadata entries in STEP_1/PLOTS. Can be run
                        by itself using the existing metadata CSV or combined
                        with other flags.

The random mode selects a pending day automatically; otherwise provide a
start and end date in YYMMDD format for the desired range.
EOF
  exit 0
fi

if (( $# < 1 )); then
  usage
fi

station="$1"
shift

random_mode=false
newest_mode=false
refresh_metadata=false
plot_hist=false
start_arg=""
end_arg=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --refresh-metadata|-m)
      refresh_metadata=true
      shift
      ;;
    --plot)
      plot_hist=true
      shift
      ;;
    --random|-r)
      if [[ -n "$start_arg" || -n "$end_arg" || $newest_mode == true ]]; then
        usage
      fi
      random_mode=true
      shift
      ;;
    --newest|-n)
      if [[ -n "$start_arg" || -n "$end_arg" || $random_mode == true ]]; then
        usage
      fi
      newest_mode=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      if [[ "$1" =~ ^[0-9]{6}$ ]]; then
        if $random_mode || $newest_mode; then
          usage
        fi
        if [[ -z "$start_arg" ]]; then
          start_arg="$1"
        elif [[ -z "$end_arg" ]]; then
          end_arg="$1"
        else
          usage
        fi
        shift
      else
        usage
      fi
      ;;
  esac
done

perform_download=true
if $random_mode || $newest_mode; then
  if [[ -n "$start_arg" || -n "$end_arg" ]]; then
    usage
  fi
else
  if [[ -z "$start_arg" || -z "$end_arg" ]]; then
    perform_download=false
  fi
fi

if ! $refresh_metadata && ! $perform_download && ! $plot_hist; then
  usage
fi

##############################################################################
# Target directories
##############################################################################
station_directory="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0${station}"
reprocessing_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_1"
input_directory="${reprocessing_directory}/INPUT_FILES"
output_directory="${reprocessing_directory}/OUTPUT_FILES"
compressed_directory="${output_directory}/COMPRESSED_HLDS"
uncompressed_directory="${output_directory}/UNCOMPRESSED_HLDS"
metadata_directory="${reprocessing_directory}/METADATA"
mkdir -p "$input_directory" "$compressed_directory" "$uncompressed_directory" "$metadata_directory"

step0_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_0"
step0_metadata_directory="${step0_directory}/METADATA"
step0_output_directory="${step0_directory}/OUTPUT_FILES"
qa_retry_manifest_csv="${step0_output_directory}/qa_retry_manifest_${station}.csv"
active_reprocessing_csv="${REPO_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/REPROCESS_BASENAMES/active_reprocessing.csv"
dat_unpacked_csv="${station_directory}/STAGE_0/REPROCESSING/STEP_2/METADATA/dat_files_unpacked.csv"
stage0_to_1_directory="${station_directory}/STAGE_0_TO_1"
task0_directory="${station_directory}/STAGE_1/EVENT_DATA/STEP_1/TASK_0"
task0_input_directory="${task0_directory}/INPUT_FILES"
task0_output_directory="${task0_directory}/OUTPUT_FILES"
task0_execution_csv="${task0_directory}/METADATA/task_0_metadata_execution.csv"
stage1_product_metadata_directory="${station_directory}/STAGE_1_PRODUCTS/EVENT_DATA/METADATA"

brought_csv="${metadata_directory}/hld_files_brought.csv"
brought_csv_header="hld_name,bring_timesamp"
processed_csv="${REPO_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/UPDATE_EXECUTION_CSVS/OUTPUT_FILES/MINGO0${station}_processed_basenames.csv"
config_file_shared="${MASTER_DIR}/CONFIG_FILES/STAGE_0/REPROCESSING/config_reprocessing.yaml"
config_file_step="${MASTER_DIR}/CONFIG_FILES/STAGE_0/REPROCESSING/STEP_1/config_step_1.yaml"
reprocessing_policy_script="${MASTER_DIR}/common/reprocessing_policy.py"

is_reprocessing_step_enabled() {
  local station_id="$1"
  local step_id="$2"
  local cfg_path="$config_file_shared"
  [[ -f "$cfg_path" ]] || return 0

  local decision
  decision=$(python3 - "$cfg_path" "$station_id" "$step_id" <<'PY' || true
import sys
from pathlib import Path
import os

cfg_path, station_raw, step_raw = sys.argv[1:4]

try:
    import yaml
except ImportError:
    print("1")
    raise SystemExit(0)

def parse_int(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None

def normalize_steps(value):
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return []
        if text == "all":
            return "all"
        out = []
        for token in text.replace(";", ",").split(","):
            token = token.strip().lower()
            if not token:
                continue
            if token.startswith("step_"):
                token = token.split("step_", 1)[1]
            elif token.startswith("step"):
                token = token[4:]
            try:
                out.append(int(token))
            except Exception:
                continue
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if isinstance(item, str):
                parsed = normalize_steps(item)
                if parsed == "all":
                    return "all"
                if isinstance(parsed, list):
                    out.extend(parsed)
                    continue
            try:
                out.append(int(item))
            except Exception:
                continue
        return out
    if isinstance(value, (int, float)):
        try:
            return [int(value)]
        except Exception:
            return []
    return []

station_id = parse_int(station_raw)
step_id = parse_int(step_raw)
if station_id is None or step_id is None:
    print("1")
    raise SystemExit(0)

repo_root = Path(os.environ["DATAFLOW_ROOT"])
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

try:
    from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import load_selection_for_paths, station_is_selected
    selection = load_selection_for_paths(
        [cfg_path],
        master_config_root=repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "CONFIG_FILES",
    )
    if not station_is_selected(station_id, selection.stations):
        print("0")
        raise SystemExit(0)
except Exception:
    pass

try:
    with open(cfg_path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
except Exception:
    data = {}

node = data.get("reprocessing_run_matrix")
if not isinstance(node, dict):
    print("1")
    raise SystemExit(0)

if not bool(node.get("enabled", False)):
    print("1")
    raise SystemExit(0)

mode = str(node.get("mode", "whitelist")).strip().lower()
stations_node = node.get("stations")
if not isinstance(stations_node, dict):
    stations_node = {}

default_steps = normalize_steps(node.get("default_steps", []))
station_steps = normalize_steps(stations_node.get(str(station_id)))
if station_steps is None:
    station_steps = normalize_steps(stations_node.get("0"))

if mode == "blacklist":
    disabled = False
    if station_steps is None:
        if default_steps == "all":
            disabled = True
        elif isinstance(default_steps, list) and step_id in default_steps:
            disabled = True
    elif station_steps == "all":
        disabled = True
    elif isinstance(station_steps, list) and step_id in station_steps:
        disabled = True
    print("0" if disabled else "1")
    raise SystemExit(0)

allowed = False
if station_steps is None:
    if default_steps == "all":
        allowed = True
    elif isinstance(default_steps, list) and step_id in default_steps:
        allowed = True
elif station_steps == "all":
    allowed = True
elif isinstance(station_steps, list) and step_id in station_steps:
    allowed = True

print("1" if allowed else "0")
PY
  )

  [[ "$decision" != "0" ]]
}

if ! is_reprocessing_step_enabled "$station" 1; then
  log_info "Skipping station ${station}: STEP_1 disabled by reprocessing_run_matrix."
  exit 0
fi

resolve_reprocessing_policy_field() {
  local field="$1"
  python3 "$reprocessing_policy_script" \
    --shared "$config_file_shared" \
    --local "$config_file_step" \
    --step 1 \
    --station "$station" \
    --field "$field"
}

if [[ "$(resolve_reprocessing_policy_field stations)" != "true" ]]; then
  log_info "Skipping station ${station}: not included in the resolved STEP_1 stations policy."
  exit 0
fi

reprocess_completed=$(resolve_reprocessing_policy_field reprocess_completed_stations)
log_info "Resolved STEP_1 policy: station=${station}, reprocess_completed=${reprocess_completed}."

# STATUS_CSV="${metadata_directory}/bring_reprocessing_files_status.csv"
# if ! STATUS_TIMESTAMP="$(python3 "$STATUS_HELPER" append "$STATUS_CSV")"; then
#   echo "Warning: unable to record status in $STATUS_CSV" >&2
#   STATUS_TIMESTAMP=""
# fi

remote_dir="/local/experiments/MINGOS/MINGO0${station}/"
remote_user="rpcuser"
printf -v remote_dir_escaped '%q' "$remote_dir"
clean_metadata_csv="${step0_output_directory}/clean_remote_database_${station}.csv"
working_metadata_csv="${input_directory}/clean_remote_database_${station}.csv"
csv_timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
csv_header="basename"

metadata_prep_script="${MASTER_DIR}/STAGES/STAGE_0/REPROCESSING/STEP_0/prepare_reprocessing_metadata.sh"
if $refresh_metadata || $plot_hist; then
  if [[ ! -x "$metadata_prep_script" ]]; then
    log_info "Metadata preparation script not found at $metadata_prep_script" >&2
    exit 1
  fi
  step0_args=("$station")
  $refresh_metadata && step0_args+=("--refresh-metadata")
  $plot_hist && step0_args+=("--plot")
  "$metadata_prep_script" "${step0_args[@]}"
fi

# Remove incomplete zero-byte targets before the initial snapshot. Otherwise
# rsync --ignore-existing would preserve them forever and the basename would
# never become a fresh, validated download.
for download_dir in "$compressed_directory" "$uncompressed_directory"; do
  while IFS= read -r -d '' empty_download; do
    log_warn "Removing zero-byte download placeholder so it can be fetched again: $empty_download"
    rm -f "$empty_download"
  done < <(find "$download_dir" -maxdepth 1 -type f -size 0 -print0)
done

# Snapshot existing archives to detect fresh downloads after rsync completes
tmp_before_compressed=$(mktemp)
tmp_before_uncompressed=$(mktemp)
tmp_after_compressed=""
tmp_after_uncompressed=""
tmp_new_compressed=""
tmp_new_uncompressed=""
compressed_list_file=""
uncompressed_list_file=""
new_downloads_file=""

cleanup() {
  rm -f "$tmp_before_compressed" "$tmp_before_uncompressed"
  [[ -n "$tmp_after_compressed" ]] && rm -f "$tmp_after_compressed"
  [[ -n "$tmp_after_uncompressed" ]] && rm -f "$tmp_after_uncompressed"
  [[ -n "$tmp_new_compressed" ]] && rm -f "$tmp_new_compressed"
  [[ -n "$tmp_new_uncompressed" ]] && rm -f "$tmp_new_uncompressed"
  [[ -n "$compressed_list_file" ]] && rm -f "$compressed_list_file"
  [[ -n "$uncompressed_list_file" ]] && rm -f "$uncompressed_list_file"
  [[ -n "$new_downloads_file" ]] && rm -f "$new_downloads_file"
  return 0
}
trap cleanup EXIT

read_config_value() {
  local key="$1"
  python3 - "$key" "$config_file_step" "$config_file_shared" <<'PY' || true
import re
import sys

key = sys.argv[1]
paths = [sys.argv[2], sys.argv[3]]
value = None
for path in paths:
    if not path:
        continue
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                match = re.match(rf"\s*{re.escape(key)}\s*:\s*(\S+)", line)
                if match:
                    value = match.group(1)
                    break
    except FileNotFoundError:
        continue
    if value:
        break

if value:
    print(value.strip())
PY
}

ensure_brought_csv() {
  if [[ ! -f "$brought_csv" || ! -s "$brought_csv" ]]; then
    printf '%s\n' "$brought_csv_header" > "$brought_csv"
  fi
}

declare -A qa_retry_basenames=()
load_qa_retry_manifest_basenames() {
  qa_retry_basenames=()
  if [[ ! -s "$qa_retry_manifest_csv" ]]; then
    return
  fi
  {
    read -r _header || true
    while IFS=',' read -r retry_base _rest; do
      retry_base=${retry_base//$'\r'/}
      [[ -z "$retry_base" || "$retry_base" == "basename" ]] && continue
      qa_retry_basenames["$retry_base"]=1
    done
  } < "$qa_retry_manifest_csv"
}

declare -A active_reprocessing_basenames=()
load_active_reprocessing_basenames() {
  active_reprocessing_basenames=()
  [[ -s "$active_reprocessing_csv" ]] || return 0
  while IFS="," read -r request_station request_base _task _requested_at stage0_fallback _rest; do
    [[ "$request_station" == "MINGO${station_code}" ]] || continue
    [[ "$stage0_fallback" == "1" ]] || continue
    [[ -n "$request_base" ]] && active_reprocessing_basenames["$request_base"]=1
  done < "$active_reprocessing_csv"
}

declare -A brought_hld_records=()
load_brought_hld_records() {
  if [[ ! -s "$brought_csv" ]]; then
    return
  fi
  while IFS=',' read -r hld_name _; do
    hld_name=${hld_name//$'\r'/}
    [[ -z "$hld_name" || "$hld_name" == "hld_name" ]] && continue
    brought_hld_records["$hld_name"]=1
  done < "$brought_csv"
}

strip_suffix() {
  local name="$1"
  name=${name%.hld.tar.gz}
  name=${name%.hld-tar-gz}
  name=${name%.tar.gz}
  name=${name%.hld}
  name=${name%.dat}
  printf '%s' "$name"
}

declare -A unpacked_basenames=()
declare -A stage1_started_basenames=()

load_unpacked_basenames() {
  unpacked_basenames=()
  [[ -s "$dat_unpacked_csv" ]] || return 0
  while IFS="," read -r dat_name _execution_timestamp _execution_duration actually_unpacked _rest; do
    dat_name=${dat_name//$'\r'/}
    actually_unpacked=${actually_unpacked//$'\r'/}
    [[ -z "$dat_name" || "$dat_name" == "dat_name" ]] && continue
    # Legacy rows have no explicit flag and represent successful unpacking.
    [[ "$actually_unpacked" == "0" ]] && continue
    local base
    base=$(strip_suffix "$dat_name")
    [[ -n "$base" ]] && unpacked_basenames["$base"]=1
  done < "$dat_unpacked_csv"
}

load_stage1_started_basenames() {
  stage1_started_basenames=()

  shopt -s nullglob
  local metadata_csv
  local -a execution_metadata_files=(
    "$task0_execution_csv"
    "$stage1_product_metadata_directory"/TASK_*/task_*_metadata_execution.csv
  )
  shopt -u nullglob
  for metadata_csv in "${execution_metadata_files[@]}"; do
    [[ -s "$metadata_csv" ]] || continue
    while IFS="," read -r base _rest; do
      base=${base//$'\r'/}
      [[ -z "$base" || "$base" == "filename_base" ]] && continue
      stage1_started_basenames["$base"]=1
    done < "$metadata_csv"
  done

  shopt -s nullglob
  local artifact name base
  for artifact in \
    "$stage0_to_1_directory"/*.dat \
    "$task0_input_directory"/*/*.dat \
    "$task0_output_directory"/raw_*.parquet; do
    [[ -f "$artifact" ]] || continue
    name=$(basename "$artifact")
    if [[ "$name" == raw_*.parquet ]]; then
      base=${name#raw_}
      base=${base%.parquet}
    else
      base=$(strip_suffix "$name")
    fi
    [[ -n "$base" ]] && stage1_started_basenames["$base"]=1
  done
  shopt -u nullglob
}

has_safe_local_handoff() {
  local base="$1"
  [[ -n ${unpacked_basenames["$base"]+_} && -n ${stage1_started_basenames["$base"]+_} ]]
}

basename_has_local_file() {
  local base="$1"
  local alt="$base"
  if [[ $alt == minI* ]]; then
    alt="mi0${station}${alt:4}"
  fi
  local candidate
  for candidate in \
    "${compressed_directory}/${base}.hld.tar.gz" \
    "${compressed_directory}/${base}.hld-tar-gz" \
    "${compressed_directory}/${base}.tar.gz" \
    "${compressed_directory}/${base}.dat" \
    "${uncompressed_directory}/${base}.hld" \
    "${uncompressed_directory}/${base}.dat" \
    "${compressed_directory}/${alt}.hld.tar.gz" \
    "${compressed_directory}/${alt}.hld-tar-gz" \
    "${compressed_directory}/${alt}.tar.gz" \
    "${uncompressed_directory}/${alt}.hld"; do
    [[ -n "$candidate" && -s "$candidate" ]] && return 0
  done
  return 1
}

basename_time_key() {
  local name="$1"
  local base
  base=$(strip_suffix "$name")
  if [[ $base =~ ([0-9]{11})$ ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  else
    printf ''
  fi
}

time_key_to_epoch() {
  local key="$1"
  if [[ ! $key =~ ^[0-9]{11}$ ]]; then
    return 1
  fi
  local yy=${key:0:2}
  local doy=${key:2:3}
  local hh=${key:5:2}
  local mm=${key:7:2}
  local ss=${key:9:2}
  local day_index=$((10#$doy - 1))
  if (( day_index < 0 )); then
    return 1
  fi
  date -d "20${yy}-01-01 +${day_index} days ${hh}:${mm}:${ss}" +%s 2>/dev/null
}

basename_to_epoch() {
  local name="$1"
  local key
  key=$(basename_time_key "$name")
  if [[ -z "$key" ]]; then
    return 1
  fi
  time_key_to_epoch "$key"
}

newest_mode_order_key() {
  local base="$1"
  local normalized="$base"
  if [[ $normalized == minI* ]]; then
    normalized="mi01${normalized:4}"
  fi
  local prefix="mi0${station}"
  if [[ $normalized == "${prefix}"* ]]; then
    printf '%s' "${normalized:${#prefix}}"
    return 0
  fi
  local key
  key=$(basename_time_key "$normalized")
  if [[ -n "$key" ]]; then
    printf '%s' "$key"
    return 0
  fi
  printf '%s' "$normalized"
}

ymd_to_epoch() {
  local ymd="$1"
  if [[ ! $ymd =~ ^[0-9]{6}$ ]]; then
    return 1
  fi
  local yy=${ymd:0:2}
  local mm=${ymd:2:2}
  local dd=${ymd:4:2}
  date -d "20${yy}-${mm}-${dd}" +%s
}

ymd_to_bound_key() {
  local ymd="$1"
  local suffix="$2"
  local doy
  doy=$(date -d "20${ymd:0:2}-${ymd:2:2}-${ymd:4:2}" +%y%j 2>/dev/null) || return 1
  printf '%s%s' "$doy" "$suffix"
}

if [[ ! -s "$clean_metadata_csv" ]]; then
  log_info "Clean metadata CSV not found at ${clean_metadata_csv}." >&2
  log_info "Attempting automatic refresh via $(basename "$metadata_prep_script") --refresh-metadata (station ${station})." >&2

  # Throttle + serialize refreshes across stations to avoid overloading the system/remote host.
  # - Throttle: small station-based delay so stations refresh in numeric order when cron fires simultaneously.
  # - Serialize: flock ensures only one refresh runs at a time.
  refresh_delay_sec=$((10#$station * 3))
  if (( refresh_delay_sec > 0 )); then
    log_info "Throttling metadata refresh by sleeping ${refresh_delay_sec}s (station ${station})." >&2
    sleep "$refresh_delay_sec"
  fi

  lock_dir="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS"
  lock_file="${lock_dir}/prepare_reprocessing_metadata_refresh.lock"
  mkdir -p "$lock_dir"

  exec 9>"$lock_file"
  if flock -n 9; then
    if [[ -x "$metadata_prep_script" ]]; then
      if ! "$metadata_prep_script" "$station" --refresh-metadata; then
        log_warn "metadata refresh failed for station ${station}"
      fi
    else
      log_warn "metadata preparation script not found at $metadata_prep_script"
    fi
    flock -u 9 || true
  else
    log_warn "another metadata refresh is already running; skipping refresh for station ${station} this run"
  fi

  if [[ ! -s "$clean_metadata_csv" ]]; then
    log_warn "clean metadata CSV still not found at ${clean_metadata_csv}; skipping downloads for station ${station}"
    exit 0
  fi
fi

if ! cp "$clean_metadata_csv" "$working_metadata_csv"; then
  log_info "Unable to copy metadata CSV into ${working_metadata_csv}." >&2
  exit 1
fi
csv_path="$working_metadata_csv"
log_info "Using metadata from ${csv_path}"

declare -a metadata_basenames=()
if [[ -s "$csv_path" ]]; then
  {
    read -r _header || true
    while IFS=',' read -r base_name _rest; do
      base_name=${base_name//$'\r'/}
      [[ -z "$base_name" || "$base_name" == "$csv_header" ]] && continue
      metadata_basenames+=("$base_name")
    done
  } < "$csv_path"
fi

if (( ${#metadata_basenames[@]} == 0 )); then
  log_info "Metadata CSV ${csv_path} does not list any basenames; nothing to do."
  exit 0
fi
log_info "Loaded ${#metadata_basenames[@]} basenames from metadata CSV."

load_qa_retry_manifest_basenames
log_info "Active QA retry basenames from STEP_0 manifest: ${#qa_retry_basenames[@]}"
load_active_reprocessing_basenames
log_info "Active operator reprocessing basenames requiring Stage 0: ${#active_reprocessing_basenames[@]}"
load_unpacked_basenames
load_stage1_started_basenames
log_info "Previously unpacked basenames: ${#unpacked_basenames[@]}"
log_info "Basenames with a local Stage 1 handoff or Task 0 execution: ${#stage1_started_basenames[@]}"

if ! $perform_download; then
  if $plot_hist; then
    log_info "No download requested; plot-only run complete."
  else
    log_info "No download requested; exiting after metadata handling."
  fi
  exit 0
fi

declare -A brought_basenames=()
if [[ -s "$brought_csv" ]]; then
  {
    read -r _header || true
    while IFS=',' read -r recorded_name bring_ts; do
      recorded_name=${recorded_name//$'\r'/}
      [[ -z "$recorded_name" || "$recorded_name" == "hld_name" ]] && continue
      brought_basenames["$recorded_name"]=1
    done
  } < "$brought_csv"
fi
initial_brought_count=${#brought_basenames[@]}
  if (( initial_brought_count > 0 )); then
    missing_local_count=0
    for recorded_name in "${!brought_basenames[@]}"; do
      if ! basename_has_local_file "$recorded_name"; then
        unset "brought_basenames[$recorded_name]"
        ((missing_local_count+=1))
      fi
    done
    if (( missing_local_count > 0 )); then
      log_info "Detected ${missing_local_count} basenames recorded as brought but missing in OUTPUT_FILES; they will be re-downloaded."
  fi
fi
log_info "Basenames already recorded as brought: ${#brought_basenames[@]}"

random_batch_size=1
random_batch_key="random_basenames_per_run_${station}"
random_batch_raw=$(read_config_value "$random_batch_key" | tr -d '[:space:]')
if [[ "$random_batch_raw" =~ ^[0-9]+$ ]] && (( random_batch_raw >= 1 )); then
  random_batch_size=$random_batch_raw
fi

declare -A processed_basenames=()
if $reprocess_completed; then
  log_info "Station ${station} is in reprocess_completed_stations; processed basenames remain eligible."
else
  if [[ -s "$processed_csv" ]]; then
    {
      read -r _header || true
      while IFS=',' read -r processed_name _rest; do
        processed_name=${processed_name//$'\r'/}
        [[ -z "$processed_name" || "$processed_name" == "basename" ]] && continue
        processed_basenames["$processed_name"]=1
      done
    } < "$processed_csv"
  fi
  log_info "Basenames already processed (execution CSVs): ${#processed_basenames[@]}"
fi

log_info "Selecting basenames to download..."

declare -a selected_bases=()

mapfile -t active_candidates < <(
  for base in "${metadata_basenames[@]}"; do
    [[ -n ${active_reprocessing_basenames["$base"]+_} ]] && printf "%s\n" "$base"
  done | sort
)

if (( ${#active_candidates[@]} > 0 )); then
  selected_bases=("${active_candidates[@]:0:random_batch_size}")
  log_info "Prioritizing ${#selected_bases[@]} active operator reprocessing request(s): ${selected_bases[*]}"
elif $random_mode; then
  mapfile -t random_candidates < <(
    for base in "${metadata_basenames[@]}"; do
      [[ -n ${brought_basenames["$base"]+_} ]] && continue
      if [[ -z ${qa_retry_basenames["$base"]+_} ]] && has_safe_local_handoff "$base"; then
        continue
      fi
      if ! $reprocess_completed && [[ -z ${qa_retry_basenames["$base"]+_} ]] && [[ -n ${processed_basenames["$base"]+_} ]]; then
        continue
      fi
      printf '%s\n' "$base"
    done
  )
  if (( ${#random_candidates[@]} == 0 )); then
    log_info "No basenames require downloading; all metadata entries are already local, downstream, or completed."
    exit 0
  fi
  mapfile -t selected_bases < <(
    printf '%s\n' "${random_candidates[@]}" | shuf -n "$random_batch_size"
  )
  if (( ${#selected_bases[@]} == 1 )); then
    log_info "Randomly selected basename: ${selected_bases[0]}"
  else
    log_info "Randomly selected ${#selected_bases[@]} basenames (configured ${random_batch_size}): ${selected_bases[*]}"
  fi
elif $newest_mode; then
  mapfile -t newest_candidates < <(
    for base in "${metadata_basenames[@]}"; do
      [[ -n ${brought_basenames["$base"]+_} ]] && continue
      if [[ -z ${qa_retry_basenames["$base"]+_} ]] && has_safe_local_handoff "$base"; then
        continue
      fi
      if ! $reprocess_completed && [[ -z ${qa_retry_basenames["$base"]+_} ]] && [[ -n ${processed_basenames["$base"]+_} ]]; then
        continue
      fi
      printf '%s\n' "$base"
    done
  )
  if (( ${#newest_candidates[@]} == 0 )); then
    log_info "--newest requested but all metadata basenames are already recorded in hld_files_brought.csv."
    exit 0
  fi
  newest_base=""
  newest_key=""
  for base in "${newest_candidates[@]}"; do
    order_key=$(newest_mode_order_key "$base")
    if [[ -z "$newest_base" || "$order_key" > "$newest_key" ]]; then
      newest_base="$base"
      newest_key="$order_key"
    fi
  done
  if [[ -z "$newest_base" ]]; then
    newest_base=$(printf '%s\n' "${newest_candidates[@]}" | sort | tail -n1)
    newest_key=""
  fi
  selected_bases=("$newest_base")
  if [[ -n "$newest_key" ]]; then
    log_info "--newest flag active; newest unprocessed basename selected: ${selected_bases[0]} (key ${newest_key})"
  else
    log_info "--newest flag active; newest unprocessed basename selected: ${selected_bases[0]}"
  fi
else
  start="$start_arg"
  end="$end_arg"

  if [[ ! $start =~ ^[0-9]{6}$ || ! $end =~ ^[0-9]{6}$ ]]; then
    log_info "Dates must be provided as YYMMDD; received start=${start} end=${end}" >&2
    exit 1
  fi

  start_key=$(ymd_to_bound_key "$start" "000000") || {
    log_info "Unable to compute comparison key for start date ${start}" >&2
    exit 1
  }
  end_key=$(ymd_to_bound_key "$end" "235959") || {
    log_info "Unable to compute comparison key for end date ${end}" >&2
    exit 1
  }
  start_bound="mi0${station}${start_key}"
  end_bound="mi0${station}${end_key}"

  for base in "${metadata_basenames[@]}"; do
    [[ -n ${brought_basenames["$base"]+_} ]] && continue
    if [[ -z ${qa_retry_basenames["$base"]+_} ]] && has_safe_local_handoff "$base"; then
      continue
    fi
    if ! $reprocess_completed && [[ -z ${qa_retry_basenames["$base"]+_} ]] && [[ -n ${processed_basenames["$base"]+_} ]]; then
      continue
    fi
    [[ "$base" < "$start_bound" ]] && continue
    [[ "$base" > "$end_bound" ]] && continue
    selected_bases+=("$base")
  done

  if (( ${#selected_bases[@]} == 0 )); then
    log_info "No basenames remain to download for the requested range ${start}-${end}; all listed entries are already recorded in hld_files_brought.csv."
    exit 0
  fi

  log_info "Range ${start}-${end} matched ${#selected_bases[@]} basename(s)."
fi

declare -A compressed_lookup=()
declare -A uncompressed_lookup=()
remote_lookup_failed=false

for base in "${selected_bases[@]}"; do
  log_info "Inspecting remote files for basename ${base}"
  printf -v base_prefix '%q' "$base"
  if ! remote_listing=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "${remote_user}@backuplip" "cd ${remote_dir_escaped} && ls -1 ${base_prefix}*" 2>/dev/null); then
    log_warn "Unable to query backup database for ${base}; request remains pending for a later run."
    remote_lookup_failed=true
    continue
  fi
  if [[ -z "$remote_listing" ]]; then
    log_info "  No remote files found for basename ${base}" >&2
    continue
  fi
  while IFS= read -r remote_entry; do
    remote_entry=${remote_entry//$'\r'/}
    [[ -z "$remote_entry" ]] && continue
    base_entry=$(strip_suffix "$remote_entry")
    if [[ -n ${brought_basenames["$base_entry"]+_} && -z ${active_reprocessing_basenames["$base_entry"]+_} ]]; then
      continue
    fi
    case "$remote_entry" in
      *.hld.tar.gz|*.hld-tar-gz)
        compressed_lookup["$remote_entry"]=1
        ;;
      *.hld)
        [[ "$remote_entry" =~ \.tar\.gz$ ]] && continue
        [[ "$remote_entry" =~ -tar-gz$ ]] && continue
        uncompressed_lookup["$remote_entry"]=1
        ;;
      *)
        continue
        ;;
    esac
  done <<< "$remote_listing"
done

if (( ${#compressed_lookup[@]} == 0 && ${#uncompressed_lookup[@]} == 0 )); then
  if $remote_lookup_failed; then
    log_warn "Backup database lookup failed; no pending basename was marked as brought."
  fi
  log_info "No remote files matched the selected basenames; nothing to transfer."
  exit 0
fi

if [[ -n "$compressed_list_file" ]]; then
  rm -f "$compressed_list_file"
fi
compressed_list_file=""
if (( ${#compressed_lookup[@]} > 0 )); then
  compressed_list_file=$(mktemp)
  printf '%s\n' "${!compressed_lookup[@]}" | sort -u > "$compressed_list_file"
fi

if [[ -n "$uncompressed_list_file" ]]; then
  rm -f "$uncompressed_list_file"
fi
uncompressed_list_file=""
if (( ${#uncompressed_lookup[@]} > 0 )); then
  uncompressed_list_file=$(mktemp)
  printf '%s\n' "${!uncompressed_lookup[@]}" | sort -u > "$uncompressed_list_file"
fi

compressed_count=0
uncompressed_count=0
if [[ -s "$compressed_list_file" ]]; then
  compressed_count=$(wc -l < "$compressed_list_file" | tr -d '[:space:]')
fi
if [[ -s "$uncompressed_list_file" ]]; then
  uncompressed_count=$(wc -l < "$uncompressed_list_file" | tr -d '[:space:]')
fi

if $random_mode; then
  if (( ${#selected_bases[@]} == 1 )); then
    log_info "Fetching HLD files for MINGO0${station} using randomly selected basename ${selected_bases[0]}"
  else
    log_info "Fetching HLD files for MINGO0${station} using ${#selected_bases[@]} randomly selected basenames"
  fi
elif $newest_mode; then
  log_info "Fetching HLD files for MINGO0${station} using newest basename ${selected_bases[0]} (--newest)"
else
  log_info "Fetching HLD files for MINGO0${station} for range ${start}-${end}"
fi
log_info "  Planned compressed downloads : $compressed_count"
log_info "  Planned uncompressed downloads: $uncompressed_count"
log_info ""

find "$compressed_directory" -maxdepth 1 -type f \
  \( -name '*.hld*.tar.gz' -o -name '*.hld-tar-gz' \) \
  -printf '%f\n' | sort -u > "$tmp_before_compressed"

find "$uncompressed_directory" -maxdepth 1 -type f \
  -name '*.hld' \
  -printf '%f\n' | sort -u > "$tmp_before_uncompressed"

if [[ -s "$compressed_list_file" ]]; then
  echo "Starting compressed transfers..."
  if rsync -av --info=progress2 \
      --files-from="$compressed_list_file" \
      --ignore-missing-args \
      --ignore-existing --partial --partial-dir=.rsync-partial --no-compress \
      "${remote_user}@backuplip:${remote_dir}" "$compressed_directory/"; then
    :
  else
    rsync_status=$?
    if (( rsync_status != 23 && rsync_status != 24 )); then
      exit "$rsync_status"
    fi
    log_warn "rsync reported status $rsync_status while transferring compressed files; continuing"
  fi
  while IFS= read -r filename; do
    [[ -z "$filename" ]] && continue
    target_path="${compressed_directory}/${filename}"
    if [[ -f "$target_path" ]]; then
      touch "$target_path"
    fi
  done < "$compressed_list_file"
fi

if [[ -s "$uncompressed_list_file" ]]; then
  echo "Starting uncompressed transfers..."
  if rsync -av --info=progress2 \
      --files-from="$uncompressed_list_file" \
      --ignore-missing-args \
      --ignore-existing --partial --partial-dir=.rsync-partial --no-compress \
      "${remote_user}@backuplip:${remote_dir}" "$uncompressed_directory/"; then
    :
  else
    rsync_status=$?
    if (( rsync_status != 23 && rsync_status != 24 )); then
      exit "$rsync_status"
    fi
    log_warn "rsync reported status $rsync_status while transferring uncompressed files; continuing"
  fi
  while IFS= read -r filename; do
    [[ -z "$filename" ]] && continue
    target_path="${uncompressed_directory}/${filename}"
    if [[ -f "$target_path" ]]; then
      touch "$target_path"
    fi
  done < "$uncompressed_list_file"
fi

if (( compressed_count == 0 && uncompressed_count == 0 )); then
  echo "No files matched the requested range; nothing to transfer."
fi

tmp_after_compressed=$(mktemp)
find "$compressed_directory" -maxdepth 1 -type f \
  \( -name '*.hld*.tar.gz' -o -name '*.hld-tar-gz' \) \
  -printf '%f\n' | sort -u > "$tmp_after_compressed"

tmp_after_uncompressed=$(mktemp)
find "$uncompressed_directory" -maxdepth 1 -type f \
  -name '*.hld' \
  -printf '%f\n' | sort -u > "$tmp_after_uncompressed"

tmp_new_compressed=$(mktemp)
comm -13 "$tmp_before_compressed" "$tmp_after_compressed" > "$tmp_new_compressed"

tmp_new_uncompressed=$(mktemp)
comm -13 "$tmp_before_uncompressed" "$tmp_after_uncompressed" > "$tmp_new_uncompressed"

if [[ -s "$tmp_new_compressed" || -s "$tmp_new_uncompressed" ]]; then
  new_downloads_file=$(mktemp)
  [[ -s "$tmp_new_compressed" ]] && cat "$tmp_new_compressed" >> "$new_downloads_file"
  [[ -s "$tmp_new_uncompressed" ]] && cat "$tmp_new_uncompressed" >> "$new_downloads_file"
  ensure_brought_csv
  while IFS= read -r brought_file; do
    [[ -z "$brought_file" ]] && continue
    base=$(strip_suffix "$brought_file")
    if [[ -z "$base" ]]; then
      continue
    fi
    if [[ -n ${brought_basenames["$base"]+_} ]]; then
      continue
    fi
    printf '%s,%s\n' "$base" "$csv_timestamp" >> "$brought_csv"
    brought_basenames["$base"]=1
  done < "$new_downloads_file"
fi

# if [[ -s "$tmp_new" ]]; then
#   awk -F',' -v OFS=',' -v newlist="$tmp_new" -v ts="$csv_timestamp" '
#     function canonical(name) {
#       gsub(/\r/, "", name)
#       sub(/\.hld\.tar\.gz$/, "", name)
#       sub(/\.hld-tar-gz$/, "", name)
#       sub(/\.tar\.gz$/, "", name)
#       sub(/\.hld$/, "", name)
#       sub(/\.dat$/, "", name)
#       return name
#     }
#     BEGIN {
#       while ((getline line < newlist) > 0) {
#         line = canonical(line)
#         if (line != "") {
#           new[line] = 1
#         }
#       }
#       close(newlist)
#     }
#     NR == 1 { print; next }
#     {
#       key = canonical($1)
#       if (key in new) {
#         if ($4 == "") {
#           $4 = ts
#         }
#         if ($5 == "") {
#           $5 = ts
#         }
#       }
#       print
#     }
#   ' "$csv_path" > "${csv_path}.tmp" && mv "${csv_path}.tmp" "$csv_path"
# fi

echo
echo '------------------------------------------------------'
echo "bring_reprocessing_files.sh completed on: $(date '+%Y-%m-%d %H:%M:%S')"
echo '------------------------------------------------------'
