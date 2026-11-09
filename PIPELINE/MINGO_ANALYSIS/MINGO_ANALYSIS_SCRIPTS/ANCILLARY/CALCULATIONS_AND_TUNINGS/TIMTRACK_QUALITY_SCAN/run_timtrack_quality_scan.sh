#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh
# Purpose: Periodically scan TimTrack convergence settings and refresh plots.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-05
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/run_timtrack_quality_scan.sh [options]
# Inputs: Config file + scan profiles CSV + Task 4 metadata files.
# Outputs: Task 4 metadata appends + scan log CSV + scan plots.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
DEFAULT_CONFIG_PATH="${SCRIPT_DIR}/CONFIGS/timtrack_quality_scan.conf"
if [[ ! -f "${DEFAULT_CONFIG_PATH}" ]]; then
  # Backward compatibility with legacy location.
  DEFAULT_CONFIG_PATH="${SCRIPT_DIR}/timtrack_quality_scan.conf"
fi
PLOT_SCRIPT_PATH="${SCRIPT_DIR}/timtrack_quality_scan_plotter.py"

CONFIG_PATH="${DEFAULT_CONFIG_PATH}"
PLOT_ONLY=false
RUN_ONCE=false
MAX_CYCLES=0
STATION_OVERRIDE=""
INTERVAL_OVERRIDE=""
INVOKE_TASK4_OVERRIDE=""
ASSUME_YES=false

usage() {
  cat <<'EOF'
run_timtrack_quality_scan.sh
Automates TimTrack convergence scanning by cycling (d0, cocut, iter_max) profiles.

Usage:
  run_timtrack_quality_scan.sh [--config <path>] [--once] [--max-cycles <n>] [--plot-only]
                               [--run-task4|--no-run-task4] [--station <0-4>] [--interval-minutes <n>]
                               [--yes]

Options:
  --config <path>            Path to scan config file.
                             Default: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/CONFIGS/timtrack_quality_scan.conf
  --once                     Run one scan cycle and exit.
  --max-cycles <n>           Stop after n cycles (0 = no limit).
  --plot-only                Skip scanning and generate plots from existing metadata.
  --run-task4                Force Task 4 execution mode for this run.
  --no-run-task4             Force metadata-only mode for this run.
  --station <0-4>            Override station from config.
  --interval-minutes <n>     Override interval_minutes from config.
  --yes                      Skip interactive confirmation prompt.
                             For finite planned runs, prefer config:
                               stop_after_profile_sweep=true
                               restore_default_after_sweep=true
  -h, --help                 Show this help and exit.
EOF
}

log_ts() {
  date '+%Y-%m-%d %H:%M:%S'
}

log_info() {
  printf '[%s] [TIMTRACK_SCAN] %s\n' "$(log_ts)" "$*"
}

log_err() {
  printf '[%s] [TIMTRACK_SCAN] [ERROR] %s\n' "$(log_ts)" "$*" >&2
}

is_true() {
  case "${1,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_path() {
  local raw_path="$1"
  if [[ -z "${raw_path}" ]]; then
    printf '%s\n' ""
    return
  fi
  if [[ "${raw_path}" = /* ]]; then
    printf '%s\n' "${raw_path}"
  else
    printf '%s\n' "${REPO_ROOT}/${raw_path}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --plot-only)
      PLOT_ONLY=true
      shift
      ;;
    --run-task4)
      INVOKE_TASK4_OVERRIDE="true"
      shift
      ;;
    --no-run-task4)
      INVOKE_TASK4_OVERRIDE="false"
      shift
      ;;
    --once)
      RUN_ONCE=true
      shift
      ;;
    --max-cycles)
      MAX_CYCLES="${2:-0}"
      shift 2
      ;;
    --station)
      STATION_OVERRIDE="${2:-}"
      shift 2
      ;;
    --interval-minutes)
      INTERVAL_OVERRIDE="${2:-}"
      shift 2
      ;;
    --yes)
      ASSUME_YES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_err "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "${CONFIG_PATH}" ]]; then
  log_err "Config file not found: ${CONFIG_PATH}"
  exit 1
fi

# shellcheck source=/dev/null
source "${CONFIG_PATH}"

station="${station:-0}"
interval_minutes="${interval_minutes:-2}"
runs_per_profile="${runs_per_profile:-1}"
invoke_task4="${invoke_task4:-false}"
continue_on_task_failure="${continue_on_task_failure:-true}"
restore_on_exit="${restore_on_exit:-false}"
tail_rows="${tail_rows:-300}"
use_cocut_range="${use_cocut_range:-true}"
fixed_d0="${fixed_d0:-10}"
fixed_iter_max="${fixed_iter_max:-100}"
cocut_min="${cocut_min:-0.25}"
cocut_max="${cocut_max:-2.0}"
cocut_step="${cocut_step:-0.25}"
stop_after_profile_sweep="${stop_after_profile_sweep:-false}"
restore_default_after_sweep="${restore_default_after_sweep:-false}"
default_d0="${default_d0:-${fixed_d0}}"
default_cocut="${default_cocut:-${cocut_max}}"
default_iter_max="${default_iter_max:-${fixed_iter_max}}"
profiles_csv="${profiles_csv:-}"
plot_output_dir="${plot_output_dir:-PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/OUTPUT}"
scan_log_csv="${scan_log_csv:-PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/OUTPUT/timtrack_quality_scan_log.csv}"
run_reference_csv="${run_reference_csv:-PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/ANCILLARY/TIMTRACK_QUALITY_SCAN/OUTPUT/timtrack_quality_scan_run_reference.csv}"
plot_run_back="${plot_run_back:-0}"
task4_script="${task4_script:-PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_1/EVENT_DATA/COIN_TRIGGER/TASK_4/script_4_list_to_fit.py}"
task4_parameters_csv="${task4_parameters_csv:-PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/SUPPORT/CONFIG_FILES/STAGE_1/EVENT_DATA/STEP_1/TASK_4/config_parameters_task_4.csv}"
task4_specific_metadata_csv="${task4_specific_metadata_csv:-}"
task4_profiling_metadata_csv="${task4_profiling_metadata_csv:-}"

if [[ -n "${STATION_OVERRIDE}" ]]; then
  station="${STATION_OVERRIDE}"
fi
if [[ -n "${INTERVAL_OVERRIDE}" ]]; then
  interval_minutes="${INTERVAL_OVERRIDE}"
fi
if [[ -n "${INVOKE_TASK4_OVERRIDE}" ]]; then
  invoke_task4="${INVOKE_TASK4_OVERRIDE}"
fi

if ! [[ "${station}" =~ ^[0-4]$ ]]; then
  log_err "station must be 0..4, got '${station}'"
  exit 1
fi
if ! [[ "${interval_minutes}" =~ ^[0-9]+$ ]] || [[ "${interval_minutes}" -lt 0 ]]; then
  log_err "interval_minutes must be a non-negative integer"
  exit 1
fi
if ! [[ "${runs_per_profile}" =~ ^[0-9]+$ ]] || [[ "${runs_per_profile}" -lt 1 ]]; then
  log_err "runs_per_profile must be an integer >= 1"
  exit 1
fi
if ! [[ "${MAX_CYCLES}" =~ ^[0-9]+$ ]]; then
  log_err "--max-cycles must be a non-negative integer"
  exit 1
fi
if ! [[ "${plot_run_back}" =~ ^-?[0-9]+$ ]]; then
  log_err "plot_run_back must be an integer (e.g. 0 for latest, 1 for previous, -1 to disable run filtering)"
  exit 1
fi

PROFILES_CSV_ABS="$(resolve_path "${profiles_csv}")"
PLOT_OUTPUT_DIR_ABS="$(resolve_path "${plot_output_dir}")"
SCAN_LOG_CSV_ABS="$(resolve_path "${scan_log_csv}")"
RUN_REFERENCE_CSV_ABS="$(resolve_path "${run_reference_csv}")"
TASK4_SCRIPT_ABS="$(resolve_path "${task4_script}")"
TASK4_PARAMETERS_CSV_ABS="$(resolve_path "${task4_parameters_csv}")"

station_label="$(printf 'MINGO%02d' "${station}")"
if [[ -z "${task4_specific_metadata_csv}" ]]; then
  TASK4_SPECIFIC_CSV_ABS="${REPO_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/${station_label}/STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_specific.csv"
else
  TASK4_SPECIFIC_CSV_ABS="$(resolve_path "${task4_specific_metadata_csv}")"
fi
if [[ -z "${task4_profiling_metadata_csv}" ]]; then
  TASK4_PROFILING_CSV_ABS="${REPO_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/${station_label}/STAGE_1/EVENT_DATA/STEP_1/TASK_4/METADATA/task_4_metadata_profiling.csv"
else
  TASK4_PROFILING_CSV_ABS="$(resolve_path "${task4_profiling_metadata_csv}")"
fi

mkdir -p "${PLOT_OUTPUT_DIR_ABS}"
mkdir -p "$(dirname "${SCAN_LOG_CSV_ABS}")"
mkdir -p "$(dirname "${RUN_REFERENCE_CSV_ABS}")"

LOCK_PATH="${PLOT_OUTPUT_DIR_ABS}/timtrack_quality_scan.lock"
exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  log_err "Another scan instance is already running (lock: ${LOCK_PATH})"
  exit 1
fi

for required_path in \
  "${TASK4_PARAMETERS_CSV_ABS}" \
  "${PLOT_SCRIPT_PATH}"
do
  if [[ ! -f "${required_path}" ]]; then
    log_err "Required file not found: ${required_path}"
    exit 1
  fi
done

if ! is_true "${use_cocut_range}" && [[ ! -f "${PROFILES_CSV_ABS}" ]]; then
  log_err "profiles_csv not found and use_cocut_range=false: ${PROFILES_CSV_ABS}"
  exit 1
fi

if is_true "${invoke_task4}" && [[ ! -f "${TASK4_SCRIPT_ABS}" ]]; then
  log_err "Task 4 script not found: ${TASK4_SCRIPT_ABS}"
  exit 1
fi

ensure_scan_log_header() {
  if [[ ! -f "${SCAN_LOG_CSV_ABS}" ]]; then
    cat > "${SCAN_LOG_CSV_ABS}" <<'EOF'
execution_timestamp,cycle,profile_id,station,d0,cocut,iter_max,task4_exit_code,task4_duration_s,specific_rows,profiling_rows,specific_last_timestamp,profiling_last_timestamp
EOF
  fi
}

ensure_run_reference_header() {
  if [[ ! -f "${RUN_REFERENCE_CSV_ABS}" ]]; then
    cat > "${RUN_REFERENCE_CSV_ABS}" <<'EOF'
run_timestamp,cycle,profile_id,station,d0,cocut,iter_max,invoke_task4,specific_rows_before,specific_rows_after,profiling_rows_before,profiling_rows_after,new_specific_rows,new_profiling_rows,basename_count,basenames,specific_last_timestamp,profiling_last_timestamp
EOF
  fi
}

metadata_snapshot() {
  python3 - "${TASK4_SPECIFIC_CSV_ABS}" "${TASK4_PROFILING_CSV_ABS}" <<'PY'
import sys
from pathlib import Path
import pandas as pd

specific_path = Path(sys.argv[1])
profiling_path = Path(sys.argv[2])

def snap(path: Path):
    if not path.exists():
        return 0, "", ""
    try:
        usecols = ["execution_timestamp"]
        if path == specific_path:
            usecols.append("filename_base")
        df = pd.read_csv(path, usecols=usecols, low_memory=False)
    except Exception:
        return 0, "", ""
    if df.empty:
        return 0, "", ""
    last_ts = str(df["execution_timestamp"].iloc[-1])
    last_base = ""
    if "filename_base" in df.columns:
        last_base = str(df["filename_base"].iloc[-1])
    return int(len(df)), last_ts, last_base

spec_rows, spec_ts, spec_base = snap(specific_path)
prof_rows, prof_ts, _ = snap(profiling_path)
print(f"{spec_rows},{prof_rows},{spec_ts},{prof_ts},{spec_base}")
PY
}

run_plotter() {
  python3 "${PLOT_SCRIPT_PATH}" \
    --specific-csv "${TASK4_SPECIFIC_CSV_ABS}" \
    --profiling-csv "${TASK4_PROFILING_CSV_ABS}" \
    --output-dir "${PLOT_OUTPUT_DIR_ABS}" \
    --tail-rows "${tail_rows}" \
    --scan-log "${SCAN_LOG_CSV_ABS}" \
    --run-reference-log "${RUN_REFERENCE_CSV_ABS}" \
    --run-back "${plot_run_back}" \
    --title-prefix "${station_label}"
}

declare -a PROFILE_ROWS=()
load_profiles() {
  if is_true "${use_cocut_range}"; then
    mapfile -t PROFILE_ROWS < <(
      python3 - "${fixed_d0}" "${fixed_iter_max}" "${cocut_min}" "${cocut_max}" "${cocut_step}" <<'PY'
import sys

def fail(msg: str) -> None:
    raise SystemExit(msg)

try:
    d0 = float(sys.argv[1])
    iter_max = int(float(sys.argv[2]))
    cocut_min = float(sys.argv[3])
    cocut_max = float(sys.argv[4])
    cocut_step = float(sys.argv[5])
except Exception as exc:
    fail(f"Invalid cocut range config: {exc}")

if iter_max <= 0:
    fail("fixed_iter_max must be > 0")
if cocut_step <= 0:
    fail("cocut_step must be > 0")

direction = 1.0 if cocut_max >= cocut_min else -1.0
step = abs(cocut_step) * direction
eps = max(1e-12, abs(step) * 1e-9)

def keep(x: float, end: float) -> bool:
    return x <= end + eps if direction > 0 else x >= end - eps

values = []
x = cocut_min
guard = 0
while keep(x, cocut_max) and guard < 100000:
    values.append(round(x, 12))
    x += step
    guard += 1

if guard >= 100000:
    fail("cocut range generation exceeded guard limit")
if not values:
    values = [round(cocut_min, 12)]
if abs(values[-1] - cocut_max) > eps:
    values.append(round(cocut_max, 12))

# Deduplicate while preserving order after rounding.
seen = set()
ordered = []
for value in values:
    key = f"{value:.12g}"
    if key in seen:
        continue
    seen.add(key)
    ordered.append(value)

for cocut in ordered:
    cocut_txt = f"{cocut:g}"
    d0_txt = f"{d0:g}"
    print(f"cocut_{cocut_txt},{d0_txt},{cocut_txt},{iter_max}")
PY
    )
  else
    if [[ -z "${PROFILES_CSV_ABS}" ]]; then
      log_err "profiles_csv must be set when use_cocut_range=false"
      exit 1
    fi
    if [[ ! -f "${PROFILES_CSV_ABS}" ]]; then
      log_err "profiles_csv not found: ${PROFILES_CSV_ABS}"
      exit 1
    fi
    mapfile -t PROFILE_ROWS < <(
      python3 - "${PROFILES_CSV_ABS}" <<'PY'
import csv
import sys

csv_path = sys.argv[1]
with open(csv_path, newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    required = {"profile_id", "d0", "cocut", "iter_max"}
    missing = required.difference(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required profile column(s): {sorted(missing)}")
    for row in reader:
        enabled = str(row.get("enabled", "1")).strip().lower()
        if enabled in {"0", "false", "no", "off", "n"}:
            continue
        profile_id = str(row["profile_id"]).strip()
        d0 = str(row["d0"]).strip()
        cocut = str(row["cocut"]).strip()
        iter_max = str(row["iter_max"]).strip()
        if not profile_id or not d0 or not cocut or not iter_max:
            continue
        print(f"{profile_id},{d0},{cocut},{iter_max}")
PY
    )
  fi

  if [[ "${#PROFILE_ROWS[@]}" -eq 0 ]]; then
    if is_true "${use_cocut_range}"; then
      log_err "No cocut profiles generated from config range."
    else
      log_err "No enabled profiles found in ${PROFILES_CSV_ABS}"
    fi
    exit 1
  fi
}

set_task4_convergence() {
  local d0_value="$1"
  local cocut_value="$2"
  local iter_max_value="$3"
  local target_column="default"
  if [[ "${station}" != "0" ]]; then
    target_column="station_${station}"
  fi

  python3 - "${TASK4_PARAMETERS_CSV_ABS}" "${target_column}" "${d0_value}" "${cocut_value}" "${iter_max_value}" <<'PY'
import csv
import sys
from pathlib import Path

csv_path = Path(sys.argv[1])
target_column = sys.argv[2]
d0_value = sys.argv[3]
cocut_value = sys.argv[4]
iter_max_value = sys.argv[5]

with csv_path.open("r", newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    fieldnames = list(reader.fieldnames or [])
    if not fieldnames:
        raise SystemExit(f"No header found in {csv_path}")
    if target_column not in fieldnames:
        raise SystemExit(f"Column '{target_column}' not found in {csv_path}")
    rows = list(reader)

required = {"d0": d0_value, "cocut": cocut_value, "iter_max": iter_max_value}
seen = set()
for row in rows:
    name = str(row.get("parameter", "")).strip()
    if name in required:
        row[target_column] = required[name]
        seen.add(name)

missing = sorted(set(required).difference(seen))
if missing:
    raise SystemExit(f"Missing convergence parameter row(s) in CSV: {missing}")

with csv_path.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
PY
}

append_scan_log_row() {
  local cycle="$1"
  local profile_id="$2"
  local d0_value="$3"
  local cocut_value="$4"
  local iter_max_value="$5"
  local exit_code="$6"
  local duration_s="$7"
  local snapshot_csv="$8"
  local now_ts

  now_ts="$(date '+%Y-%m-%d_%H.%M.%S')"
  IFS=',' read -r spec_rows prof_rows spec_ts prof_ts spec_base <<< "${snapshot_csv}"
  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "${now_ts}" \
    "${cycle}" \
    "${profile_id}" \
    "${station}" \
    "${d0_value}" \
    "${cocut_value}" \
    "${iter_max_value}" \
    "${exit_code}" \
    "${duration_s}" \
    "${spec_rows}" \
    "${prof_rows}" \
    "${spec_ts}" \
    "${prof_ts}" \
    >> "${SCAN_LOG_CSV_ABS}"
}

extract_run_basenames() {
  local start_rows="$1"
  local end_rows="$2"
  python3 - "${TASK4_SPECIFIC_CSV_ABS}" "${start_rows}" "${end_rows}" <<'PY'
import sys
from pathlib import Path
import pandas as pd

csv_path = Path(sys.argv[1])
start_rows = int(float(sys.argv[2]))
end_rows = int(float(sys.argv[3]))

if not csv_path.exists() or end_rows <= start_rows:
    print("0,")
    raise SystemExit(0)

try:
    df = pd.read_csv(csv_path, usecols=["filename_base"], low_memory=False)
except Exception:
    print("0,")
    raise SystemExit(0)

start_rows = max(0, start_rows)
end_rows = min(len(df), end_rows)
if end_rows <= start_rows:
    print("0,")
    raise SystemExit(0)

rows = df.iloc[start_rows:end_rows]
seen = set()
ordered = []
for value in rows["filename_base"].astype(str):
    name = value.strip()
    if not name or name.lower() == "nan":
        continue
    if name in seen:
        continue
    seen.add(name)
    ordered.append(name)

print(f"{len(ordered)},{';'.join(ordered)}")
PY
}

append_run_reference_row() {
  local cycle="$1"
  local profile_id="$2"
  local d0_value="$3"
  local cocut_value="$4"
  local iter_max_value="$5"
  local before_snapshot="$6"
  local after_snapshot="$7"

  local now_ts
  local spec_rows_before prof_rows_before spec_ts_before prof_ts_before spec_base_before
  local spec_rows_after prof_rows_after spec_ts_after prof_ts_after spec_base_after
  local basenames_payload basename_count basenames
  local new_specific_rows new_profiling_rows

  now_ts="$(date '+%Y-%m-%d_%H.%M.%S')"
  IFS=',' read -r spec_rows_before prof_rows_before spec_ts_before prof_ts_before spec_base_before <<< "${before_snapshot}"
  IFS=',' read -r spec_rows_after prof_rows_after spec_ts_after prof_ts_after spec_base_after <<< "${after_snapshot}"

  new_specific_rows=$((spec_rows_after - spec_rows_before))
  new_profiling_rows=$((prof_rows_after - prof_rows_before))
  if (( new_specific_rows < 0 )); then
    new_specific_rows=0
  fi
  if (( new_profiling_rows < 0 )); then
    new_profiling_rows=0
  fi

  basenames_payload="$(extract_run_basenames "${spec_rows_before}" "${spec_rows_after}")"
  IFS=',' read -r basename_count basenames <<< "${basenames_payload}"

  printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
    "${now_ts}" \
    "${cycle}" \
    "${profile_id}" \
    "${station}" \
    "${d0_value}" \
    "${cocut_value}" \
    "${iter_max_value}" \
    "${invoke_task4}" \
    "${spec_rows_before}" \
    "${spec_rows_after}" \
    "${prof_rows_before}" \
    "${prof_rows_after}" \
    "${new_specific_rows}" \
    "${new_profiling_rows}" \
    "${basename_count}" \
    "${basenames}" \
    "${spec_ts_after}" \
    "${prof_ts_after}" \
    >> "${RUN_REFERENCE_CSV_ABS}"
}

backup_config=""
restore_config() {
  if [[ -n "${backup_config}" ]] && [[ -f "${backup_config}" ]]; then
    cp "${backup_config}" "${TASK4_PARAMETERS_CSV_ABS}"
    log_info "Restored Task 4 convergence config from backup."
  fi
}

restore_default_convergence() {
  log_info "Restoring default convergence values: d0=${default_d0} cocut=${default_cocut} iter_max=${default_iter_max}"
  set_task4_convergence "${default_d0}" "${default_cocut}" "${default_iter_max}"
}

format_minutes_human() {
  local total_min="$1"
  local hours minutes
  if [[ "${total_min}" -lt 60 ]]; then
    printf '%dm' "${total_min}"
    return
  fi
  hours=$((total_min / 60))
  minutes=$((total_min % 60))
  printf '%dh%02dm' "${hours}" "${minutes}"
}

confirm_scan_plan() {
  local planned_cycles="$1"
  local stop_mode="$2"
  local wait_minutes=0
  local wait_text
  local duration_note
  local response

  if [[ "${planned_cycles}" -gt 0 ]]; then
    if is_true "${invoke_task4}"; then
      if [[ "${planned_cycles}" -gt 1 ]]; then
        wait_minutes=$(((planned_cycles - 1) * interval_minutes))
      fi
      duration_note="plus Task 4 runtime per cycle"
    else
      if [[ "${RUN_ONCE}" != true ]]; then
        wait_minutes=$((planned_cycles * interval_minutes))
      fi
      duration_note="metadata-only wait time"
    fi
    wait_text="$(format_minutes_human "${wait_minutes}")"
    log_info "Planned scan summary: stop_mode=${stop_mode} cycles=${planned_cycles} profiles=${#PROFILE_ROWS[@]} interval=${interval_minutes}min"
    log_info "Estimated duration: ${wait_text} (${duration_note})."
  else
    log_info "Planned scan summary: stop_mode=continuous (no automatic stop), profiles=${#PROFILE_ROWS[@]} interval=${interval_minutes}min"
    if is_true "${invoke_task4}"; then
      log_info "Estimated duration: open-ended (includes Task 4 runtime per cycle)."
    else
      log_info "Estimated duration: open-ended (metadata-only mode)."
    fi
  fi

  if [[ "${ASSUME_YES}" == true ]]; then
    log_info "Confirmation skipped (--yes)."
    return
  fi
  if [[ ! -t 0 ]]; then
    log_info "No interactive terminal detected; proceeding without confirmation prompt."
    return
  fi

  read -r -p "[TIMTRACK_SCAN] Continue with this run? [y/N] " response
  case "${response,,}" in
    y|yes)
      ;;
    *)
      log_info "Run cancelled by user before cycle start."
      exit 0
      ;;
  esac
}

if [[ "${PLOT_ONLY}" == true ]]; then
  log_info "Running plot-only mode."
  run_plotter
  log_info "Plot-only mode finished."
  exit 0
fi

if is_true "${restore_on_exit}"; then
  backup_config="${PLOT_OUTPUT_DIR_ABS}/config_parameters_task_4.backup.$(date '+%Y%m%d_%H%M%S').csv"
  cp "${TASK4_PARAMETERS_CSV_ABS}" "${backup_config}"
  trap restore_config EXIT INT TERM
fi

ensure_scan_log_header
ensure_run_reference_header
load_profiles

if is_true "${use_cocut_range}"; then
  log_info "Loaded ${#PROFILE_ROWS[@]} cocut scan points from config range (${cocut_min} -> ${cocut_max}, step=${cocut_step}, d0=${fixed_d0}, iter_max=${fixed_iter_max})"
else
  log_info "Loaded ${#PROFILE_ROWS[@]} scan profiles from ${PROFILES_CSV_ABS}"
fi
log_info "Station=${station_label} interval=${interval_minutes}min invoke_task4=${invoke_task4} runs_per_profile=${runs_per_profile}"
if is_true "${stop_after_profile_sweep}"; then
  log_info "Planned finite run enabled: stop after one full sweep of ${#PROFILE_ROWS[@]} profile(s)."
  if is_true "${restore_default_after_sweep}"; then
    log_info "Will restore defaults at sweep end: d0=${default_d0} cocut=${default_cocut} iter_max=${default_iter_max}"
  fi
fi

planned_cycles=0
stop_mode="continuous"
if [[ "${RUN_ONCE}" == true ]]; then
  planned_cycles=1
  stop_mode="run_once"
elif [[ "${MAX_CYCLES}" -gt 0 ]]; then
  planned_cycles="${MAX_CYCLES}"
  stop_mode="max_cycles"
elif is_true "${stop_after_profile_sweep}"; then
  planned_cycles="${#PROFILE_ROWS[@]}"
  stop_mode="profile_sweep"
fi
confirm_scan_plan "${planned_cycles}" "${stop_mode}"

cycle_index=0
profile_index=0

while true; do
  cycle_index=$((cycle_index + 1))
  IFS=',' read -r profile_id d0_value cocut_value iter_max_value <<< "${PROFILE_ROWS[profile_index]}"
  before_snapshot="$(metadata_snapshot)"

  log_info "Cycle ${cycle_index}: profile=${profile_id} d0=${d0_value} cocut=${cocut_value} iter_max=${iter_max_value}"
  set_task4_convergence "${d0_value}" "${cocut_value}" "${iter_max_value}"

  if is_true "${invoke_task4}"; then
    for run_i in $(seq 1 "${runs_per_profile}"); do
      start_s="$(date +%s)"
      if python3 "${TASK4_SCRIPT_ABS}" "${station}"; then
        exit_code=0
      else
        exit_code=$?
        log_err "Task 4 run failed (cycle=${cycle_index}, run=${run_i}, profile=${profile_id}, rc=${exit_code})"
      fi
      end_s="$(date +%s)"
      duration_s="$((end_s - start_s))"
      snapshot_csv="$(metadata_snapshot)"
      append_scan_log_row \
        "${cycle_index}" \
        "${profile_id}" \
        "${d0_value}" \
        "${cocut_value}" \
        "${iter_max_value}" \
        "${exit_code}" \
        "${duration_s}" \
        "${snapshot_csv}"

      if [[ "${exit_code}" -ne 0 ]] && ! is_true "${continue_on_task_failure}"; then
        log_err "Stopping scan due to task failure and continue_on_task_failure=false."
        exit "${exit_code}"
      fi
    done
  else
    # Metadata-only mode: convergence is rotated here, data processing runs elsewhere.
    if [[ "${RUN_ONCE}" != true ]]; then
      sleep_seconds=$((interval_minutes * 60))
      if [[ "${sleep_seconds}" -gt 0 ]]; then
        log_info "Waiting ${interval_minutes} minute(s) for external Task 4 runs."
        sleep "${sleep_seconds}"
      fi
    fi

    snapshot_csv="$(metadata_snapshot)"
    append_scan_log_row \
      "${cycle_index}" \
      "${profile_id}" \
      "${d0_value}" \
      "${cocut_value}" \
      "${iter_max_value}" \
      "" \
      "" \
      "${snapshot_csv}"
  fi

  append_run_reference_row \
    "${cycle_index}" \
    "${profile_id}" \
    "${d0_value}" \
    "${cocut_value}" \
    "${iter_max_value}" \
    "${before_snapshot}" \
    "${snapshot_csv}"

  if ! run_plotter; then
    log_err "Plotter failed after cycle ${cycle_index}."
    if ! is_true "${continue_on_task_failure}"; then
      exit 1
    fi
  fi

  completed_profile_sweep=false
  if is_true "${stop_after_profile_sweep}" && [[ "${profile_index}" -eq $(( ${#PROFILE_ROWS[@]} - 1 )) ]]; then
    completed_profile_sweep=true
  fi

  if [[ "${RUN_ONCE}" == true ]]; then
    log_info "Run-once mode finished after cycle ${cycle_index}."
    break
  fi
  if [[ "${MAX_CYCLES}" -gt 0 ]] && [[ "${cycle_index}" -ge "${MAX_CYCLES}" ]]; then
    log_info "Reached max cycles (${MAX_CYCLES})."
    break
  fi
  if [[ "${completed_profile_sweep}" == true ]]; then
    log_info "Completed one full planned sweep after cycle ${cycle_index}."
    if is_true "${restore_default_after_sweep}"; then
      restore_default_convergence
    fi
    break
  fi

  profile_index=$(((profile_index + 1) % ${#PROFILE_ROWS[@]}))
  if is_true "${invoke_task4}"; then
    sleep_seconds=$((interval_minutes * 60))
    if [[ "${sleep_seconds}" -gt 0 ]]; then
      log_info "Sleeping ${interval_minutes} minute(s) before next cycle."
      sleep "${sleep_seconds}"
    fi
  fi
done

log_info "TimTrack quality scan completed."
