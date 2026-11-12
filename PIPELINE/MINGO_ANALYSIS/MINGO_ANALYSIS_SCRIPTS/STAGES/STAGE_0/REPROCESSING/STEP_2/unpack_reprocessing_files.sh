#!/bin/bash
# Purpose: Unpack the selected reprocessing HLD files for the requested station.

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
# Usage: ./unpack_reprocessing_files.sh <station>
# Example: ./unpack_reprocessing_files.sh 1

# What to really change when the directory is changed:
#    unpack.sh, of course, the cd should lead to software
#    initConf.m, the HOME line, THAT MUST END WITH A SLASH
#    

log_ts() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
    printf '[%s] [UNPACK_STEP_2] %s\n' "$(log_ts)" "$*"
}

log_warn() {
    printf '[%s] [UNPACK_STEP_2] [WARN] %s\n' "$(log_ts)" "$*" >&2
}

log_error() {
    printf '[%s] [UNPACK_STEP_2] [ERROR] %s\n' "$(log_ts)" "$*" >&2
}

if [[ ${1:-} =~ ^(-h|--help)$ ]]; then
    cat <<'EOF'
unpack_reprocessing_files.sh
Unpacks compressed HLD archives and prepares data for STAGE_0 processing.

Usage:
  unpack_reprocessing_files.sh <station> [--loop|-l] [--newest|-n] [--max-parallel|-p N]

Options:
  -h, --help       Show this help message and exit.
  -l, --loop       Process every pending HLD sequentially (repeat single-run workflow).
  -n, --newest     Select the newest pending HLD (after normalizing its prefix).
  -p, --max-parallel N  Allow up to N concurrent runs for this station (default 5).

Provide the numeric station identifier (1-4). The script ensures only one
instance runs per-station and operates on files queued in STAGE_0 buffers.
EOF
    exit 0
fi

if (( $# < 1 || $# > 4 )); then
    echo "Usage: $0 <station> [--loop|-l] [--newest|-n] [--max-parallel|-p N]"
    exit 1
fi
random_file=false  # set to true to enable random selection

original_args="$*"
station=$1
shift

if [[ ! "$station" =~ ^[0-9]+$ ]]; then
    echo "Station identifier must be a number between 1 and 4."
    exit 1
fi

station=$((10#$station))
if (( station < 1 || station > 4 )); then
    echo "Station identifier must be between 1 and 4."
    exit 1
fi

station_code=$(printf "%02d" "$station")
station_prefix=$(printf "mi0%d" "$station")
station_prefix_lower="${station_prefix,,}"


loop_mode=false
newest_mode=false
max_parallel=5

while (( $# > 0 )); do
    case "$1" in
        --loop|-l)
            loop_mode=true
            ;;
        --newest|-n)
            newest_mode=true
            ;;
        --max-parallel|-p)
            if [[ -n "${2:-}" && "${2}" =~ ^[0-9]+$ && ${2} -ge 1 ]]; then
                max_parallel="${2}"
                shift
            else
                log_error "--max-parallel requires a positive integer."
                exit 1
            fi
            ;;
        *)
            echo "Usage: $0 <station> [--loop|-l] [--newest|-n]"
            exit 1
            ;;
    esac
    shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "${MASTER_DIR}" != "/" && "$(basename "${MASTER_DIR}")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
    MASTER_DIR="$(dirname "${MASTER_DIR}")"
done
REPO_ROOT="$(dirname "$(dirname "${MASTER_DIR}")")"

config_file_shared="${MASTER_DIR}/SUPPORT/CONFIG_FILES/STAGE_0/REPROCESSING/config_reprocessing.yaml"
config_file_step="${MASTER_DIR}/SUPPORT/CONFIG_FILES/STAGE_0/REPROCESSING/STEP_2/config_step_2.yaml"
reprocessing_policy_script="${MASTER_DIR}/SUPPORT/SHARED_CODE/reprocessing_policy.py"
UNPACKER_ROOT="${MASTER_DIR}/STAGES/STAGE_0/REPROCESSING/UNPACKER_ZERO_STAGE_FILES"

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
    from PIPELINE.MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.selection_config import load_selection_for_paths, station_is_selected
    selection = load_selection_for_paths(
        [cfg_path],
        master_config_root=repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "SUPPORT" / "CONFIG_FILES",
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

if ! is_reprocessing_step_enabled "$station" 2; then
    log_info "Skipping station ${station}: STEP_2 disabled by reprocessing_run_matrix."
    exit 0
fi

resolve_reprocessing_policy_field() {
    local field="$1"
    python3 "$reprocessing_policy_script" \
        --shared "$config_file_shared" \
        --local "$config_file_step" \
        --step 2 \
        --station "$station" \
        --field "$field"
}

if [[ "$(resolve_reprocessing_policy_field stations)" != "true" ]]; then
    log_info "Skipping station ${station}: not included in the resolved STEP_2 stations policy."
    exit 0
fi

reprocess_completed=$(resolve_reprocessing_policy_field reprocess_completed_stations)
log_info "Resolved STEP_2 policy: station=${station}, reprocess_completed=${reprocess_completed}."

# --------------------------------------------------------------------------------------------
# Prevent the script from running multiple instances -----------------------------------------
# --------------------------------------------------------------------------------------------

# Variables
script_name=$(basename "$0")
script_args="$original_args"
current_pid=$$

script_path=$(readlink -f "$0")
running_count=$(
    ps -eo pid=,args= \
        | grep -Ec "^[[:space:]]*[0-9]+[[:space:]]+(/usr/bin/|/bin/)?bash[[:space:]]+${script_path}[[:space:]]+${station}([[:space:]]|$)" \
        || true
)
if (( running_count > 0 )); then
    ((running_count-=1))
fi

if (( running_count >= max_parallel )); then
    echo "------------------------------------------------------"
    echo "$(date): Max parallel limit reached for station $station_code ($running_count/$max_parallel). Exiting."
    echo "------------------------------------------------------"
    exit 1
fi

echo "$(date) - Running instances for station $station_code: $running_count (limit $max_parallel). Proceeding..."
echo "------------------------------------------------------"
echo "unpack_reprocessing_files.sh started on: $(date)"
echo "Station: ${station_code} (loop_mode=$loop_mode, newest_mode=$newest_mode, max_parallel=$max_parallel)"
echo "Running the script..."
if $reprocess_completed; then
    echo "Station ${station} is in reprocess_completed_stations: duplicate-protection checks are disabled."
fi

STATIONS_BASE="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"
station_directory="${STATIONS_BASE}/MINGO${station_code}"
reprocessing_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_2"
step0_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_0"
step0_output_directory="${step0_directory}/OUTPUT_FILES"
step0_metadata_directory="${step0_directory}/METADATA"
step_1_output_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_1/OUTPUT_FILES"
step_1_output_compressed="${step_1_output_directory}/COMPRESSED_HLDS"
step_1_output_uncompressed="${step_1_output_directory}/UNCOMPRESSED_HLDS"
qa_retry_manifest_csv="${step0_output_directory}/qa_retry_manifest_${station}"
qa_retry_manifest_csv="${qa_retry_manifest_csv}.csv"
qa_retry_state_csv="${step0_metadata_directory}/qa_retry_state_${station}.csv"
active_reprocessing_csv="${REPO_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/STATE/REPROCESS_BASENAMES/active_reprocessing.csv"
input_directory="${reprocessing_directory}/INPUT_FILES"
unprocessed_uncompressed="${input_directory}/UNPROCESSED"
completed_uncompressed="${input_directory}/COMPLETED"
processing_directory="${input_directory}/PROCESSING"
error_directory="${input_directory}/ERROR"
metadata_directory="${reprocessing_directory}/METADATA"
stage0_to_1_directory="${station_directory}/STAGE_0_TO_1"
task0_directory="${station_directory}/STAGE_1/EVENT_DATA/STEP_1/TASK_0"
task0_input_directory="${task0_directory}/INPUT_FILES"
task0_output_directory="${task0_directory}/OUTPUT_FILES"
task0_execution_csv="${task0_directory}/METADATA/task_0_metadata_execution.csv"
stage1_product_metadata_directory="${station_directory}/STAGE_1_PRODUCTS/EVENT_DATA/METADATA"
# csv_path="${station_directory}/database_status_${station_code}.csv"

mkdir -p \
    "$unprocessed_uncompressed" \
    "$completed_uncompressed" \
    "$processing_directory" \
    "$error_directory" \
    "$metadata_directory" \
    "$stage0_to_1_directory"

dat_unpacked_csv="${metadata_directory}/dat_files_unpacked.csv"
dat_unpacked_header="dat_name,execution_timestamp,execution_duration_s,actually_unpacked"
declare -A dat_unpacked_basenames=()
declare -A qa_retry_basenames=()
declare -A active_reprocessing_basenames=()

# csv_path="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0${station}/database_status_${station}.csv"
csv_header="basename,start_date,hld_remote_add_date,hld_local_add_date,dat_add_date,list_ev_name,list_ev_add_date,acc_name,acc_add_date,merge_add_date"

ensure_dat_unpacked_csv() {
    if [[ ! -f "$dat_unpacked_csv" || ! -s "$dat_unpacked_csv" ]]; then
        printf '%s\n' "$dat_unpacked_header" > "$dat_unpacked_csv"
        return
    fi
    local current_header
    current_header=$(head -n 1 "$dat_unpacked_csv")
    if [[ "$current_header" != "$dat_unpacked_header" ]]; then
        local tmp_file
        tmp_file=$(mktemp)
        printf '%s\n' "$dat_unpacked_header" > "$tmp_file"
        if [[ "$current_header" == *"actually_unpacked"* ]]; then
            tail -n +2 "$dat_unpacked_csv" >> "$tmp_file"
        else
            tail -n +2 "$dat_unpacked_csv" | while IFS= read -r line; do
                [[ -z "$line" ]] && continue
                printf '%s,1\n' "$line"
            done >> "$tmp_file"
        fi
        mv "$tmp_file" "$dat_unpacked_csv"
    fi
}

record_dat_unpacked_entry() {
    local dat_name="$1"
    local exec_timestamp="$2"
    local exec_duration="$3"
    local actual_flag="${4:-1}"
    ensure_dat_unpacked_csv
    printf '%s,%s,%s,%s\n' "$dat_name" "$exec_timestamp" "$exec_duration" "$actual_flag" >> "$dat_unpacked_csv"
}

load_dat_unpacked_basenames() {
    dat_unpacked_basenames=()
    if [[ ! -s "$dat_unpacked_csv" ]]; then
        return
    fi
    local first=true
    while IFS=',' read -r dat_name _rest; do
        if $first; then
            first=false
            continue
        fi
        dat_name=${dat_name//$'\r'/}
        [[ -z "$dat_name" ]] && continue
        local base
        base=$(strip_suffix "$dat_name")
        [[ -z "$base" ]] && base="$dat_name"
        dat_unpacked_basenames["$base"]=1
    done < "$dat_unpacked_csv"
}

load_qa_retry_manifest_basenames() {
    qa_retry_basenames=()
    if [[ ! -s "$qa_retry_manifest_csv" ]]; then
        return
    fi
    while IFS=',' read -r retry_base _rest; do
        retry_base=${retry_base//$'\r'/}
        [[ -z "$retry_base" || "$retry_base" == "basename" ]] && continue
        qa_retry_basenames["$retry_base"]=1
    done < "$qa_retry_manifest_csv"
}

load_active_reprocessing_basenames() {
    active_reprocessing_basenames=()
    [[ -s "$active_reprocessing_csv" ]] || return 0
    while IFS="," read -r request_station request_base _task _requested_at stage0_fallback _rest; do
        [[ "$request_station" == "MINGO${station_code}" ]] || continue
        [[ "$stage0_fallback" == "1" ]] || continue
        [[ -n "$request_base" ]] && active_reprocessing_basenames["$request_base"]=1
    done < "$active_reprocessing_csv"
}

mark_qa_retry_admitted_state() {
    local base="$1"
    local admitted_at="$2"
    [[ -n "$base" ]] || return 0
    [[ -n ${qa_retry_basenames["$base"]+_} ]] || return 0

    local summary
    if summary=$(
        PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.SUPPORT.SHARED_CODE.reprocessing_qa_retry mark-admitted \
            --state-csv "$qa_retry_state_csv" \
            --basename "$base" \
            --admitted-at "$admitted_at"
    ); then
        log_info "QA retry admission recorded for ${base}: ${summary}"
    else
        log_warn "failed to update QA retry admission state for ${base}"
    fi
}

# ensure_csv() {
#     if [[ ! -f "$csv_path" || ! -s "$csv_path" ]]; then
#         printf '%s\n' "$csv_header" > "$csv_path"
#         return
#     fi
#     local current_header
#     current_header=$(head -n1 "$csv_path")
#     if [[ "$current_header" != "$csv_header" ]]; then
#         local upgrade_tmp
#         upgrade_tmp=$(mktemp)
#         {
#             printf '%s\n' "$csv_header"
#             tail -n +2 "$csv_path" | awk -F',' -v OFS=',' '{ while (NF < 10) { $(NF+1)="" } if (NF > 10) { NF=10 } print }'
#         } > "$upgrade_tmp"
#         mv "$upgrade_tmp" "$csv_path"
#     fi
# }

# ensure_csv

strip_suffix() {
    local name="$1"
    name=${name%.hld.tar.gz}
    name=${name%.hld-tar-gz}
    name=${name%.tar.gz}
    name=${name%.hld}
    name=${name%.dat}
    printf '%s' "$name"
}

has_stage1_handoff_evidence() {
    local base="$1"
    [[ -n "$base" ]] || return 1

    if [[ -f "$stage0_to_1_directory/${base}.dat" || -f "$task0_output_directory/raw_${base}.parquet" ]]; then
        return 0
    fi

    shopt -s nullglob
    local -a task0_inputs=("$task0_input_directory"/*/"${base}.dat")
    shopt -u nullglob
    if (( ${#task0_inputs[@]} > 0 )); then
        return 0
    fi

    shopt -s nullglob
    local metadata_csv
    local -a execution_metadata_files=(
        "$task0_execution_csv"
        "$stage1_product_metadata_directory"/TASK_*/task_*_metadata_execution.csv
    )
    shopt -u nullglob
    for metadata_csv in "${execution_metadata_files[@]}"; do
        if [[ -s "$metadata_csv" ]] && grep -Fq "${base}," "$metadata_csv"; then
            return 0
        fi
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

order_key_after_prefix() {
    local base="$1"
    local normalized="${base,,}"
    if [[ $normalized == mini* ]]; then
        normalized="mi01${normalized:4}"
    fi
    if [[ -n "$station_prefix_lower" && $normalized == ${station_prefix_lower}* ]]; then
        printf '%s' "${normalized:${#station_prefix_lower}}"
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

compute_start_date() {
    local name="$1"
    local base
    base=$(strip_suffix "$name")
    if [[ $base =~ ([0-9]{11})$ ]]; then
        local digits=${BASH_REMATCH[1]}
        local yy=${digits:0:2}
        local doy=${digits:2:3}
        local hhmmss=${digits:5:6}
        local hh=${hhmmss:0:2}
        local mm=${hhmmss:2:2}
        local ss=${hhmmss:4:2}
        local year=$((2000 + 10#$yy))
        local offset=$((10#$doy - 1))
        (( offset < 0 )) && offset=0
        date -d "${year}-01-01 +${offset} days ${hh}:${mm}:${ss}" '+%Y-%m-%d_%H.%M.%S' 2>/dev/null || printf ''
    else
        printf ''
    fi
}

extract_station_code_from_name() {
    local artifact="${1##*/}"
    local lowered="${artifact,,}"
    if [[ "$lowered" =~ ^mini ]]; then
        printf '01'
        return 0
    fi
    if [[ "$lowered" =~ ^mi0([0-9]) ]]; then
        local digit="${BASH_REMATCH[1]}"
        case "$digit" in
            1|2|3|4)
                printf '%02d' "$digit"
                return 0
                ;;
        esac
    fi
    return 1
}

relocate_artifact_to_station() {
    local file_path="$1"
    local target_code="$2"
    local relative_subdir="$3"
    if [[ -z "$file_path" || -z "$target_code" || -z "$relative_subdir" ]]; then
        return 1
    fi
    local target_dir="${STATIONS_BASE}/MINGO${target_code}/${relative_subdir}"
    mkdir -p "$target_dir"
    local destination="${target_dir}/$(basename "$file_path")"
    echo "--> Redirecting $(basename "$file_path") to ${target_dir}"
    mv "$file_path" "$destination"
}

# declare -A csv_rows=()
# if [[ -s "$csv_path" ]]; then
#     while IFS=',' read -r existing_basename _; do
#         [[ -z "$existing_basename" || "$existing_basename" == "basename" ]] && continue
#         existing_basename=${existing_basename//$'\r'/}
#         csv_rows["$existing_basename"]=1
#     done < "$csv_path"
# fi

# append_row_if_missing() {
#     local base="$1"
#     local remote_date="$2"
#     local local_date="$3"
#     local dat_date="$4"
#     [[ -z "$base" ]] && return
#     if [[ -n ${csv_rows["$base"]+_} ]]; then
#         return
#     fi
#     local start_value
#     start_value=$(compute_start_date "$base")
#     printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
#         "$base" "$start_value" "$remote_date" "$local_date" "$dat_date" "" "" "" "" "" >> "$csv_path"
#     csv_rows["$base"]=1
# }

move_step1_outputs_to_unprocessed() {
    local moved_any=false
    shopt -s nullglob

    if [[ -d "$step_1_output_compressed" ]]; then
        for archive in "$step_1_output_compressed"/*.tar.gz "$step_1_output_compressed"/*.hld-tar-gz; do
            [[ -e "$archive" ]] || continue
            echo "Extracting $(basename "$archive") into UNPROCESSED..."
            if tar -xvzf "$archive" --strip-components=3 -C "$unprocessed_uncompressed"; then
                moved_any=true
                rm -f "$archive"
            else
                log_warn "failed to extract $(basename "$archive")"
            fi
        done
    fi

    if [[ -d "$step_1_output_uncompressed" ]]; then
        for file in "$step_1_output_uncompressed"/*.hld "$step_1_output_uncompressed"/*.HLD; do
            [[ -e "$file" ]] || continue
            local target
            target="$unprocessed_uncompressed/$(basename "$file")"
            if [[ -e "$target" ]]; then
                echo "Skipping $(basename "$file") — already present in UNPROCESSED."
                continue
            fi
            mv "$file" "$target"
            moved_any=true
        done
    fi

    shopt -u nullglob

    if $moved_any; then
        echo "Moved STEP_1 outputs into UNPROCESSED queue."
    fi
}

hld_input_directory="${UNPACKER_ROOT}/system/devices/TRB3/mingo${station_code}/data/daqData/rawData/dat" # <--------------------------------------------
asci_output_directory="${UNPACKER_ROOT}/system/devices/TRB3/mingo${station_code}/data/daqData/asci" # <--------------------------------------------
dest_directory="$stage0_to_1_directory"

route_dat_outputs() {
    local record_array_name="$1"
    local record=false
    if [[ -n "$record_array_name" ]]; then
        record=true
        local -n record_ref="$record_array_name"
    fi

    shopt -s nullglob
    local moved_any=false
    for dat_path in "$asci_output_directory"/*.dat*; do
        [[ -f "$dat_path" ]] || continue
        local fname dest_station destination_dir
        fname=$(basename "$dat_path")
        dest_station=$(extract_station_code_from_name "$fname" 2>/dev/null || true)
        [[ -z "$dest_station" ]] && dest_station="$station_code"
        destination_dir="${STATIONS_BASE}/MINGO${dest_station}/STAGE_0_TO_1"
        mkdir -p "$destination_dir"
        if [[ -e "$destination_dir/$fname" ]]; then
            if $reprocess_completed; then
                echo "reprocess_completed=true: replacing existing $fname in ${destination_dir}."
                rm -f "$destination_dir/$fname"
            else
                echo "Skipping $fname — already present in ${destination_dir}."
                continue
            fi
        fi
        if mv "$dat_path" "$destination_dir/$fname"; then
            touch "$destination_dir/$fname"
            moved_any=true
            if [[ "$dest_station" != "$station_code" ]]; then
                echo "--> Routed $fname to station ${dest_station} STAGE_0_TO_1."
            else
                echo "Moved $fname to STAGE_0_TO_1."
                if $record; then
                    record_ref+=("$fname")
                fi
            fi
        else
            log_warn "failed to move $fname into ${destination_dir}"
        fi
    done
    shopt -u nullglob

    if $moved_any; then
        echo "Drained unpacker output directory (${asci_output_directory})."
    fi
}

wait_for_unpacker_slot() {
    local max_wait=300
    local stale_age=600
    local start_epoch
    start_epoch=$(date +%s)

    while true; do
        if [[ -d "${hld_input_directory}/semaphore" ]]; then
            echo "Unpacker semaphore present; waiting..."
            sleep 5
            continue
        fi

        local now foreign_files=()
        shopt -s nullglob
        for leftover in "$hld_input_directory"/*.hld "$hld_input_directory"/*.HLD; do
            [[ -e "$leftover" ]] || continue
            local fname owner mtime age
            fname=$(basename "$leftover")
            owner=$(extract_station_code_from_name "$fname" 2>/dev/null || true)
            mtime=$(stat -c %Y "$leftover" 2>/dev/null || echo 0)
            now=$(date +%s)
            age=$((now - mtime))

            if [[ -z "$owner" || "$owner" == "$station_code" ]]; then
                mkdir -p "$completed_uncompressed"
                mv "$leftover" "$completed_uncompressed/$fname"
                echo "Parked leftover $fname into COMPLETED."
                continue
            fi

            if (( age > stale_age )); then
                local redirect_dir="${STATIONS_BASE}/MINGO${owner}/STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/UNPROCESSED"
                mkdir -p "$redirect_dir"
                mv "$leftover" "$redirect_dir/$fname"
                echo "--> Redirected stale foreign HLD $fname back to station ${owner} queue."
                continue
            fi

            foreign_files+=("$fname")
        done
        shopt -u nullglob

        if (( ${#foreign_files[@]} == 0 )); then
            return 0
        fi

        now=$(date +%s)
        if (( now - start_epoch >= max_wait )); then
            echo "Timeout waiting for unpacker input to clear (${foreign_files[*]} still present)." >&2
            return 1
        fi

        echo "Unpacker input busy with ${foreign_files[*]}; waiting..."
        sleep 5
    done
}

process_single_hld() {
    local script_start_time script_start_epoch script_end_epoch script_duration
    local csv_timestamp
    local -a new_dat_files=()

    script_start_time="$(date '+%Y-%m-%d %H:%M:%S')"
    script_start_epoch=$(date +%s)
    csv_timestamp="$(date '+%Y-%m-%d %H:%M:%S')"

    load_dat_unpacked_basenames
    load_qa_retry_manifest_basenames
    load_active_reprocessing_basenames
    if $reprocess_completed; then
        echo "Loaded ${#dat_unpacked_basenames[@]} previously unpacked basenames (reprocess_completed=true, so they will be reprocessed if present)."
    else
        echo "Loaded ${#dat_unpacked_basenames[@]} previously unpacked basenames as exclusions."
    fi
    echo "Loaded ${#qa_retry_basenames[@]} active QA retry basenames from STEP_0 manifest."
    echo "Loaded ${#active_reprocessing_basenames[@]} active operator reprocessing basenames requiring Stage 0."

    echo "Creating necessary directories..."
    mkdir -p \
        "$unprocessed_uncompressed" \
        "$completed_uncompressed" \
        "$processing_directory" \
        "$error_directory" \
        "$dest_directory" \
        "$hld_input_directory" \
        "$asci_output_directory"

    move_step1_outputs_to_unprocessed

    echo ""
    echo "Ready to process uncompressed HLD files from UNPROCESSED..."

    shopt -s nullglob
    local -a stale_processing=("$processing_directory"/*.hld "$processing_directory"/*.HLD)
    if (( ${#stale_processing[@]} > 0 )); then
        echo "Found file(s) already in PROCESSING; moving them to ERROR."
        for stale in "${stale_processing[@]}"; do
            [[ -e "$stale" ]] || continue
            local stale_name
            stale_name=$(basename "$stale")
            mv "$stale" "$error_directory/$stale_name"
            echo "  -> $stale_name moved to ERROR."
        done
    fi
    shopt -u nullglob

    echo "Selecting one HLD file to unpack..."
    local relocated_candidates=false
    shopt -s nullglob
    local -a candidate_files=("$unprocessed_uncompressed"/*.hld "$unprocessed_uncompressed"/*.HLD)
    local source_stage="UNPROCESSED"

    if (( ${#candidate_files[@]} == 0 )); then
        echo "UNPROCESSED is empty; checking PROCESSING."
        local -a processing_candidates=("$processing_directory"/*.hld "$processing_directory"/*.HLD)
        if (( ${#processing_candidates[@]} > 0 )); then
            for proc in "${processing_candidates[@]}"; do
                [[ -e "$proc" ]] || continue
                local proc_name
                proc_name=$(basename "$proc")
                echo "  -> Found $proc_name in PROCESSING; moving to ERROR."
                mv "$proc" "$error_directory/$proc_name"
            done
        fi
        echo "UNPROCESSED and PROCESSING are empty so we are done for now."
        # candidate_files=("$completed_uncompressed"/*.hld "$completed_uncompressed"/*.HLD)
        # candidate_files=("$completed_uncompressed"/*.hld "$completed_uncompressed"/*.HLD)
        # source_stage="COMPLETED"
    fi
    shopt -u nullglob

    if (( ${#candidate_files[@]} > 0 )); then
        local -a filtered_candidates=()
        local candidate
        for candidate in "${candidate_files[@]}"; do
            [[ -e "$candidate" ]] || continue
            local candidate_station=""
            candidate_station=$(extract_station_code_from_name "$candidate" 2>/dev/null || true)
            if [[ -n "$candidate_station" && "$candidate_station" != "$station_code" ]]; then
                if relocate_artifact_to_station "$candidate" "$candidate_station" "STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/UNPROCESSED"; then
                    relocated_candidates=true
                    continue
                else
                    log_warn "failed to relocate $(basename "$candidate") to station $candidate_station"
                fi
            fi
            local candidate_base
            candidate_base=$(strip_suffix "$(basename "$candidate")")
            [[ -z "$candidate_base" ]] && candidate_base="$(basename "$candidate")"
            if [[ -n ${dat_unpacked_basenames["$candidate_base"]+_} ]]; then
                if [[ -n ${active_reprocessing_basenames["$candidate_base"]+_} ]]; then
                    echo "  -> Re-processing $(basename "$candidate") (active operator Stage 0 fallback)."
                elif [[ -n ${qa_retry_basenames["$candidate_base"]+_} ]]; then
                    echo "  -> Re-processing $(basename "$candidate") (active QA retry manifest entry)."
                elif $reprocess_completed; then
                    echo "  -> Re-processing $(basename "$candidate") (record exists in dat_files_unpacked.csv; reprocess_completed=true)."
                elif ! has_stage1_handoff_evidence "$candidate_base"; then
                    echo "  -> Re-processing $(basename "$candidate") (unpack record exists but no Stage 1 handoff remains)."
                else
                    echo "  -> Skipping $(basename "$candidate") (already unpacked with Stage 1 handoff evidence)."
                    mv -f "$candidate" "$completed_uncompressed/$(basename "$candidate")"
                    echo "     Moved to COMPLETED to avoid repeated checks."
                    local skip_timestamp
                    skip_timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
                    record_dat_unpacked_entry "$candidate_base" "$skip_timestamp" 0 0
                    continue
                fi
            fi
            filtered_candidates+=("$candidate")
        done
        candidate_files=("${filtered_candidates[@]}")
    fi

    if (( ${#candidate_files[@]} == 0 )); then
        if [[ "$relocated_candidates" == true ]]; then
            echo "All HLD files in the queue belonged to other stations and were reassigned."
        fi
        echo "No HLD files available in UNPROCESSED or PROCESSING."
        return 3  # Queue exhausted, not an unpacking failure.
    fi

    local selected_file
    if [ "$random_file" = true ]; then
        selected_file="${candidate_files[RANDOM % ${#candidate_files[@]}]}"
    elif $newest_mode; then
        local best_candidate=""
        local best_key=""
        local path base order_key
        for path in "${candidate_files[@]}"; do
            [[ -e "$path" ]] || continue
            base=$(strip_suffix "$(basename "$path")")
            [[ -z "$base" ]] && base="$(basename "$path")"
            order_key=$(order_key_after_prefix "$base")
            if [[ -z "$best_candidate" || "$order_key" > "$best_key" ]]; then
                best_candidate="$path"
                best_key="$order_key"
            fi
        done
        if [[ -z "$best_candidate" ]]; then
            best_candidate="${candidate_files[0]}"
            best_key=""
        fi
        selected_file="$best_candidate"
        echo "--newest flag active; newest pending basename selected: $(basename "$selected_file")"
    else
        local random_index=$((RANDOM % ${#candidate_files[@]}))
        selected_file="${candidate_files[random_index]}"
        echo "No --newest flag; randomly selected: $(basename "$selected_file")"
    fi

    echo "Selected HLD file: $(basename "$selected_file") [source: $source_stage]"

    local selected_base
    selected_base=$(strip_suffix "$(basename "$selected_file")")
    [[ -z "$selected_base" ]] && selected_base="$(basename "$selected_file")"
    # append_row_if_missing "$selected_base" "" "$csv_timestamp" ""

    # awk -F',' -v OFS=',' -v key="$selected_base" -v ts="$csv_timestamp" '
    #     NR == 1 { print; next }
    #     {
    #         if ($1 == key && $4 == "") {
    #             $4 = ts
    #         }
    #         print
    #     }
    # ' "$csv_path" > "${csv_path}.tmp" && mv "${csv_path}.tmp" "$csv_path"

    local filename name_no_ext prefix ss ss_val ss_new new_filename
    filename=$(basename "$selected_file")
    local processing_path="$processing_directory/$filename"

    if [[ -e "$processing_path" ]]; then
        log_warn "$filename already existed in PROCESSING; moving old copy to ERROR"
        mv "$processing_path" "$error_directory/$filename"
    fi

    if ! mv "$selected_file" "$processing_path"; then
        log_warn "failed to move $filename into PROCESSING"
        return 1
    fi

    mark_qa_retry_admitted_state "$selected_base" "$csv_timestamp"

    {
        flock -w 300 200 || { echo "Another unpacking is in progress; try again shortly." >&2; return 1; }

        if ! wait_for_unpacker_slot; then
            echo "Unpacker input is busy with other station files. Try again later."
            return 1
        fi

        route_dat_outputs

        if ! cp "$processing_path" "$hld_input_directory/$filename"; then
            log_warn "failed to copy $filename into unpacker input directory"
            return 1
        fi

        name_no_ext="${filename%.hld}"
        prefix="${name_no_ext:0:${#name_no_ext}-2}"
        ss="${name_no_ext: -2}"
        ss_val=$((10#$ss))

        if (( ss_val < 30 )); then
            ss_new=$(printf "%02d" $((ss_val + 1)))
        else
            ss_new=$(printf "%02d" $((ss_val - 1)))
        fi

        new_filename="${prefix}${ss_new}.hld"

        echo "Original file: $filename"
        echo "Copied as:     $new_filename"
        cp "$hld_input_directory/$filename" "$hld_input_directory/$new_filename"

        echo ""
        echo ""
        echo "Running unpacking..."
        export RPCSYSTEM="mingo${station_code}"
        export RPCRUNMODE=oneRun

        if ! "${UNPACKER_ROOT}/bin/unpack.sh"; then
            echo "Unpacking failed for $filename. Moving in-flight files to ERROR." >&2
            local failed_path failed_name
            for failed_path in "$hld_input_directory/$filename" "$hld_input_directory/$new_filename" "$processing_path"; do
                [[ -e "$failed_path" ]] || continue
                failed_name=$(basename "$failed_path")
                mv -f "$failed_path" "$error_directory/$failed_name"
            done
            return 1
        fi

        echo ""
        echo ""

        echo "Moving dat files into STAGE_0_TO_1..."
        route_dat_outputs new_dat_files
    } 200>"${hld_input_directory}/.unpacker_io.lock"

    if [ -d "$hld_input_directory" ]; then
        echo "Archiving processed HLD files into COMPLETED..."
        shopt -s nullglob
        for processed in "$hld_input_directory/$filename" "$hld_input_directory/$new_filename"; do
            [[ -e "$processed" ]] || continue
            local name
            name=$(basename "$processed")
            if [[ -e "$completed_uncompressed/$name" ]]; then
                rm -f "$completed_uncompressed/$name"
            fi
            mv "$processed" "$completed_uncompressed/$name"
        done
        shopt -u nullglob
    fi

    shopt -s nullglob
    for processed in "$processing_directory"/*.hld "$processing_directory"/*.HLD; do
        [[ -e "$processed" ]] || continue
        local name
        name=$(basename "$processed")
        if [[ -e "$completed_uncompressed/$name" ]]; then
            rm -f "$completed_uncompressed/$name"
        fi
        mv "$processed" "$completed_uncompressed/$name"
    done
    shopt -u nullglob

    local BASE_ROOT SUBDIRS
    BASE_ROOT="$STATIONS_BASE"
    SUBDIRS=(
        "STAGE_0/REPROCESSING/STEP_1/OUTPUT_FILES/COMPRESSED_HLDS"
        "STAGE_0/REPROCESSING/STEP_1/OUTPUT_FILES/UNCOMPRESSED_HLDS"
        "STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/UNPROCESSED"
        "STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/COMPLETED"
        "STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/PROCESSING"
        "STAGE_0/REPROCESSING/STEP_2/INPUT_FILES/ERROR"
        "STAGE_0_TO_1"
    )

    local station_loop
    for station_loop in {1..4}; do
        local station_id
        station_id=$(printf "%02d" "$station_loop")
        local station_dir
        station_dir="${BASE_ROOT}/MINGO${station_id}"

        local subdir
        for subdir in "${SUBDIRS[@]}"; do
            local current_dir
            current_dir="${station_dir}/${subdir}"
            [[ -d "$current_dir" ]] || continue

            find "$current_dir" -maxdepth 1 -type f \( \
                -name "mi0*.dat" -o \
                -name "mi0*.hld" -o \
                -name "mi0*.hld.tar.gz" -o \
                -name "mi0*.hld-tar-gz" \
            \) | while read -r file; do
                local filename file_station target_dir
                filename=$(basename "$file")
                file_station=${filename:2:2}
                if [[ "$file_station" != "$station_id" ]]; then
                    target_dir="${BASE_ROOT}/MINGO${file_station}/${subdir}"
                    echo "--> Moving $filename from MINGO${station_id}/${subdir} to MINGO${file_station}/${subdir}"
                    mkdir -p "$target_dir"
                    mv "$file" "$target_dir/"
                fi
            done
        done
    done

    script_end_epoch=$(date +%s)
    script_duration=$((script_end_epoch - script_start_epoch))
    if (( script_duration < 0 )); then
        script_duration=0
    fi

    if (( ${#new_dat_files[@]} > 0 )); then
        local dat_name dat_base
        for dat_name in "${new_dat_files[@]}"; do
            dat_base=$(strip_suffix "$dat_name")
            [[ -z "$dat_base" ]] && dat_base="$dat_name"
            local actual_flag=1
            if [[ -n ${dat_unpacked_basenames["$dat_base"]+_} ]]; then
                actual_flag=2
            fi
            record_dat_unpacked_entry "$dat_base" "$script_start_time" "$script_duration" "$actual_flag"
        done
    fi

    echo '------------------------------------------------------'
    echo "unpack_reprocessing_files.sh completed on: $(date '+%Y-%m-%d %H:%M:%S')"
    echo '------------------------------------------------------'

    return 0
}

while true; do
    if process_single_hld; then
        $loop_mode || break
    else
        result=$?
        # An empty queue completes normally, including before the first file.
        [[ $result -eq 3 ]] && break
        exit "$result"
    fi
done
exit 0
