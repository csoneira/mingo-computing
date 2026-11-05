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
# Script: PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_0/prepare_reprocessing_metadata.sh
# Purpose: prepare_reprocessing_metadata.sh.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/STAGES/STAGE_0/REPROCESSING/STEP_0/prepare_reprocessing_metadata.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# ---------------------------------------------------------------------------
# prepare_reprocessing_metadata.sh
#   Refresh and clean the STEP_0 metadata CSVs for STAGE_0 reprocessing.
#   Stores raw listings and filtered versions plus optional diagnostic plots.
# ---------------------------------------------------------------------------

set -euo pipefail

tmp_files_to_cleanup=()

cleanup_tmp_files() {
  local f
  if (( ${#tmp_files_to_cleanup[@]} == 0 )); then
    return 0
  fi
  for f in "${tmp_files_to_cleanup[@]}"; do
    [[ -n "$f" && -f "$f" ]] || continue
    rm -f "$f" || true
  done
  return 0
}
trap cleanup_tmp_files EXIT

log_info() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log_warn() {
  printf '[%s] [WARN] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

usage() {
  cat <<'USAGE'
Usage:
  prepare_reprocessing_metadata.sh <station> [--refresh-metadata|-m] [--plot] [--update-range]

Options:
  -h, --help            Show this help message and exit.
  -m, --refresh-metadata
                        Fetch the latest remote listing and update the metadata CSVs.
      --plot            Generate the metadata delta histogram PDF using the
                        current clean metadata CSV.
      --update-range    Rebuild the clean metadata CSV from the existing remote_database
                        using the configured thresholds/date range(s) (no remote fetch).
USAGE
  exit 1
}

if [[ ${1:-} =~ ^(-h|--help)$ ]]; then
  usage
fi

if (( $# < 1 )); then
  usage
fi

station="$1"
shift

refresh_metadata=false
plot_hist=false
update_range_only=false

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
    --update-range|--update-range-only)
      update_range_only=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage
      ;;
  esac
done

if $update_range_only && $refresh_metadata; then
  log_info "Cannot combine --update-range with --refresh-metadata; update range uses the existing remote_database only." >&2
  exit 1
fi

if ! $refresh_metadata && ! $plot_hist && ! $update_range_only; then
  usage
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MASTER_DIR="$SCRIPT_DIR"
while [[ "${MASTER_DIR}" != "/" && "$(basename "${MASTER_DIR}")" != "MINGO_ANALYSIS_SCRIPTS" ]]; do
  MASTER_DIR="$(dirname "${MASTER_DIR}")"
done
REPO_ROOT="$(dirname "$(dirname "${MASTER_DIR}")")"

config_file_shared="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/STAGE_0/REPROCESSING/config_reprocessing.yaml"
config_file_step="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_SCRIPTS/CONFIG_FILES/STAGE_0/REPROCESSING/STEP_0/config_step_0.yaml"

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

# whitelist (default)
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

if ! is_reprocessing_step_enabled "$station" 0; then
  log_info "Skipping station ${station}: STEP_0 disabled by reprocessing_run_matrix."
  exit 0
fi

station_directory="${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0${station}"
step0_directory="${station_directory}/STAGE_0/REPROCESSING/STEP_0"
metadata_directory="${step0_directory}/METADATA"
input_directory="${step0_directory}/INPUT_FILES"
output_directory="${step0_directory}/OUTPUT_FILES"
plots_directory="${step0_directory}/PLOTS"
mkdir -p "$metadata_directory" "$input_directory" "$output_directory" "$plots_directory"

min_filesize_mb=1    # default lower cutoff in MB (overridden by config)
max_filesize_mb=0    # default upper cutoff in MB; 0 disables upper bound
min_filesize_bytes=0
max_filesize_bytes=0
min_gap_minutes=10   # default min gap between files (minutes)
max_gap_minutes=120  # default max gap for plots (minutes)
min_gap_seconds=600
filtered_plot_csv=""

remote_host="backuplip"
remote_user="rpcuser"
remote_directory_root="/local/experiments/MINGOS"
remote_dir=""
remote_dir_escaped=""
raw_csv_max_age_days=7
raw_csv_max_age_seconds=$((raw_csv_max_age_days * 24 * 3600))
date_ranges_epoch_pairs=""
declare -a date_ranges_start_epochs=()
declare -a date_ranges_end_epochs=()
declare -a date_ranges_display_pairs=()
date_range_interval_count=0
date_range_filter_enabled=false

raw_csv="${input_directory}/remote_database_${station}.csv"
clean_csv="${output_directory}/clean_remote_database_${station}.csv"
qa_retry_manifest_csv="${output_directory}/qa_retry_manifest_${station}.csv"
metadata_tracking_csv="${metadata_directory}/metadata_refresh_history.csv"
metadata_tracking_header="executed_at,remote_file_count,clean_file_count"
filter_state_file="${metadata_directory}/metadata_filter_state_${station}.txt"
qa_retry_state_csv="${metadata_directory}/qa_retry_state_${station}.csv"
filter_state_version="1"
csv_header="basename,filesize_bytes,minutes_to_next"

strip_suffix() {
  local name="$1"
  name=${name%.hld.tar.gz}
  name=${name%.hld-tar-gz}
  name=${name%.tar.gz}
  name=${name%.hld}
  name=${name%.dat}
  printf '%s' "$name"
}

load_prepare_metadata_config() {
  local cfg_shared_path="$config_file_shared"
  local cfg_step_path="$config_file_step"
  [[ -f "$cfg_shared_path" || -f "$cfg_step_path" ]] || return 0

  local result
  if result=$(python3 - "$cfg_shared_path" "$cfg_step_path" "$station" <<'PY'
import sys
import shlex
from pathlib import Path
import os

try:
  import yaml
except ImportError:
  yaml = None

cfg_shared_path = sys.argv[1]
cfg_step_path = sys.argv[2]
station_raw = sys.argv[3]

def load_yaml_dict(path):
  if yaml is None or not path:
    return {}
  try:
    with open(path, "r") as handle:
      loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}
  except Exception:
    return {}

shared_data = load_yaml_dict(cfg_shared_path)
step_data = load_yaml_dict(cfg_step_path)
shared_cfg = shared_data.get("prepare_reprocessing_metadata")
step_cfg = step_data.get("prepare_reprocessing_metadata")
if not isinstance(shared_cfg, dict):
  shared_cfg = {}
if not isinstance(step_cfg, dict):
  step_cfg = {}

config = {}
config.update(shared_cfg)
config.update(step_cfg)
remote_host = config.get("remote_host") or ""
remote_user = config.get("remote_user") or ""
remote_root = config.get("remote_directory_root") or ""
raw_csv_max_age_days = config.get("raw_csv_max_age_days")

def parse_positive_int(value):
  if value in ("", None):
    return None
  try:
    parsed = int(float(value))
  except Exception:
    return None
  return parsed if parsed > 0 else None

repo_root = Path(os.environ["DATAFLOW_ROOT"])
if str(repo_root) not in sys.path:
  sys.path.append(str(repo_root))

epochs_serialized = ""
labels_serialized = ""
try:
  from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import (
    load_selection_for_paths,
    serialize_date_ranges_for_shell,
  )

  selection = load_selection_for_paths(
    [cfg_shared_path, cfg_step_path],
    master_config_root=repo_root / "PIPELINE" / "MINGO_ANALYSIS" / "MINGO_ANALYSIS_SCRIPTS" / "CONFIG_FILES",
  )
  from MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.selection_config import effective_date_ranges_for_station
  ranges = effective_date_ranges_for_station(station_raw, selection)
  epochs_serialized, labels_serialized = serialize_date_ranges_for_shell(ranges)
except Exception:
  pass

max_age_days = parse_positive_int(raw_csv_max_age_days)

def emit(key, value):
  print(f"{key}={shlex.quote(value if value is not None else '')}")

emit("PREP_REMOTE_HOST", str(remote_host))
emit("PREP_REMOTE_USER", str(remote_user))
emit("PREP_REMOTE_ROOT", str(remote_root))
emit("PREP_DATE_RANGES_EPOCHS", epochs_serialized)
emit("PREP_DATE_RANGES_LABELS", labels_serialized)
emit("PREP_RAW_CSV_MAX_AGE_DAYS", "" if max_age_days is None else str(max_age_days))
PY
  ); then
    eval "$result"
  fi

  local override
  override="${PREP_REMOTE_HOST:-}"
  if [[ -n "$override" ]]; then
    remote_host="$override"
  fi
  override="${PREP_REMOTE_USER:-}"
  if [[ -n "$override" ]]; then
    remote_user="$override"
  fi
  override="${PREP_REMOTE_ROOT:-}"
  if [[ -n "$override" ]]; then
    remote_directory_root="$override"
  fi

  override="${PREP_RAW_CSV_MAX_AGE_DAYS:-}"
  if [[ -n "$override" && "$override" =~ ^[0-9]+$ && "$override" -gt 0 ]]; then
    raw_csv_max_age_days="$override"
  fi
  raw_csv_max_age_seconds=$((10#$raw_csv_max_age_days * 24 * 3600))

  date_ranges_epoch_pairs="${PREP_DATE_RANGES_EPOCHS:-}"
  local labels_serialized
  labels_serialized="${PREP_DATE_RANGES_LABELS:-}"

  date_ranges_start_epochs=()
  date_ranges_end_epochs=()
  date_ranges_display_pairs=()
  date_range_interval_count=0
  date_range_filter_enabled=false

  if [[ -n "$date_ranges_epoch_pairs" ]]; then
    local -a epoch_chunks=()
    local -a label_chunks=()
    IFS=';' read -r -a epoch_chunks <<< "$date_ranges_epoch_pairs"
    IFS=';' read -r -a label_chunks <<< "$labels_serialized"
    local idx
    for idx in "${!epoch_chunks[@]}"; do
      local chunk start_epoch end_epoch
      chunk="${epoch_chunks[idx]}"
      [[ -z "$chunk" || "$chunk" != *,* ]] && continue
      start_epoch="${chunk%%,*}"
      end_epoch="${chunk#*,}"
      if [[ -n "$start_epoch" && ! "$start_epoch" =~ ^[0-9]+$ ]]; then
        continue
      fi
      if [[ -n "$end_epoch" && ! "$end_epoch" =~ ^[0-9]+$ ]]; then
        continue
      fi
      if [[ -z "$start_epoch" && -z "$end_epoch" ]]; then
        continue
      fi

      date_ranges_start_epochs+=("$start_epoch")
      date_ranges_end_epochs+=("$end_epoch")

      local label_chunk start_label end_label
      label_chunk="${label_chunks[idx]:-}"
      start_label=""
      end_label=""
      if [[ "$label_chunk" == *"|"* ]]; then
        start_label="${label_chunk%%|*}"
        end_label="${label_chunk#*|}"
      fi
      [[ -z "$start_label" ]] && start_label="-inf"
      [[ -z "$end_label" ]] && end_label="+inf"
      date_ranges_display_pairs+=("${start_label} to ${end_label}")
    done
  fi

  date_range_interval_count=${#date_ranges_start_epochs[@]}
  if (( date_range_interval_count > 0 )); then
    date_range_filter_enabled=true
    date_ranges_epoch_pairs=""
    for idx in "${!date_ranges_start_epochs[@]}"; do
      if [[ -n "$date_ranges_epoch_pairs" ]]; then
        date_ranges_epoch_pairs+=";"
      fi
      date_ranges_epoch_pairs+="${date_ranges_start_epochs[idx]},${date_ranges_end_epochs[idx]}"
    done
  fi
}

load_prepare_metadata_config "$station"
remote_directory_root="${remote_directory_root%/}"
remote_dir="${remote_directory_root}/MINGO0${station}/"
printf -v remote_dir_escaped '%q' "$remote_dir"

if $date_range_filter_enabled; then
  range_display="$(printf '%s; ' "${date_ranges_display_pairs[@]}")"
  range_display="${range_display%; }"
  log_info "Date range filtering enabled for clean metadata (${date_range_interval_count} interval(s)): ${range_display} (UTC)."
fi

load_size_thresholds() {
  local station_id="$1"
  local cfg_shared_path="$config_file_shared"
  local cfg_step_path="$config_file_step"
  if [[ -f "$cfg_shared_path" || -f "$cfg_step_path" ]]; then
    local result
    if result=$(python3 - "$station_id" "$cfg_shared_path" "$cfg_step_path" <<'PY'
import sys
try:
  import yaml
except ImportError:
  print(",")  # no config override available
  sys.exit(0)

station = sys.argv[1]
cfg_shared_path = sys.argv[2]
cfg_step_path = sys.argv[3]

def load_yaml_dict(path):
  if not path:
    return {}
  try:
    with open(path, "r") as f:
      loaded = yaml.safe_load(f) or {}
    return loaded if isinstance(loaded, dict) else {}
  except Exception:
    return {}

shared_data = load_yaml_dict(cfg_shared_path)
step_data = load_yaml_dict(cfg_step_path)

def get(key):
  val = None
  if key in shared_data:
    val = shared_data.get(key)
  if key in step_data and step_data.get(key) is not None:
    val = step_data.get(key)
  if val is None:
    return ""
  try:
    return float(val)
  except Exception:
    return ""

print(f"{get(f'min_size_mb_{station}')},{get(f'max_size_mb_{station}')}")
PY
    ); then
      local cfg_min cfg_max
      cfg_min="${result%%,*}"
      cfg_max="${result#*,}"
      if [[ -n "$cfg_min" ]]; then
        min_filesize_mb="$cfg_min"
      fi
      if [[ -n "$cfg_max" ]]; then
        max_filesize_mb="$cfg_max"
      fi
    fi
  fi

  min_filesize_bytes=$(MIN_MB="$min_filesize_mb" python3 - <<'PY'
import os
mb = float(os.environ.get("MIN_MB", "0"))
print(int(mb * 1024 * 1024))
PY
  )
  max_filesize_bytes=$(MAX_MB="$max_filesize_mb" python3 - <<'PY'
import os
mb = float(os.environ.get("MAX_MB", "0"))
print(int(mb * 1024 * 1024) if mb > 0 else 0)
PY
  )
}

load_time_thresholds() {
  local station_id="$1"
  local cfg_shared_path="$config_file_shared"
  local cfg_step_path="$config_file_step"
  if [[ -f "$cfg_shared_path" || -f "$cfg_step_path" ]]; then
    local result
    if result=$(python3 - "$station_id" "$cfg_shared_path" "$cfg_step_path" <<'PY'
import sys
try:
  import yaml
except ImportError:
  print(",")  # no config override available
  sys.exit(0)

station = sys.argv[1]
cfg_shared_path = sys.argv[2]
cfg_step_path = sys.argv[3]

def load_yaml_dict(path):
  if not path:
    return {}
  try:
    with open(path, "r") as f:
      loaded = yaml.safe_load(f) or {}
    return loaded if isinstance(loaded, dict) else {}
  except Exception:
    return {}

shared_data = load_yaml_dict(cfg_shared_path)
step_data = load_yaml_dict(cfg_step_path)

def get(key):
  val = None
  if key in shared_data:
    val = shared_data.get(key)
  if key in step_data and step_data.get(key) is not None:
    val = step_data.get(key)
  if val is None:
    return ""
  try:
    return float(val)
  except Exception:
    return ""

print(f"{get(f'min_gap_minutes_{station}')},{get(f'max_gap_minutes_{station}')}")
PY
    ); then
      local cfg_min cfg_max
      cfg_min="${result%%,*}"
      cfg_max="${result#*,}"
      if [[ -n "$cfg_min" ]]; then
        min_gap_minutes="$cfg_min"
      fi
      if [[ -n "$cfg_max" ]]; then
        max_gap_minutes="$cfg_max"
      fi
    fi
  fi

  min_gap_seconds=$(MIN_GAP_MINUTES="$min_gap_minutes" python3 - <<'PY'
import os
try:
  mg = float(os.environ.get("MIN_GAP_MINUTES", "0"))
except Exception:
  mg = 0.0
print(int(mg * 60))
PY
  )
}

ensure_filtered_plot_csv() {
  if [[ -n "${filtered_plot_csv:-}" && -s "$filtered_plot_csv" ]]; then
    return 0
  fi
  if [[ ! -s "$raw_csv" ]]; then
    return 1
  fi

  local tmp_filtered_plot
  tmp_filtered_plot=$(mktemp) || return 1
  if RAW_CSV="$raw_csv" OUT_CSV="$tmp_filtered_plot" MIN_BYTES="$min_filesize_bytes" MAX_BYTES="$max_filesize_bytes" MIN_GAP_MIN="$min_gap_minutes" DATE_RANGE_EPOCHS="$date_ranges_epoch_pairs" python3 <<'PY'
import csv
import datetime as dt
import os
import re

raw_path = os.environ["RAW_CSV"]
out_path = os.environ["OUT_CSV"]
min_bytes = int(os.environ.get("MIN_BYTES", "0") or 0)
max_bytes = int(os.environ.get("MAX_BYTES", "0") or 0)
min_gap = float(os.environ.get("MIN_GAP_MIN", "0") or 0.0)
date_ranges_env = os.environ.get("DATE_RANGE_EPOCHS", "").strip()
date_ranges = []
if date_ranges_env:
  for chunk in date_ranges_env.split(";"):
    chunk = chunk.strip()
    if not chunk or "," not in chunk:
      continue
    start_raw, end_raw = chunk.split(",", 1)
    start_raw = start_raw.strip()
    end_raw = end_raw.strip()
    start_epoch = int(start_raw) if start_raw else None
    end_epoch = int(end_raw) if end_raw else None
    if start_epoch is None and end_epoch is None:
      continue
    date_ranges.append((start_epoch, end_epoch))
date_filter_enabled = bool(date_ranges)

pattern = re.compile(r"([0-9]{11})$")

def is_in_selected_ranges(epoch: int) -> bool:
  for start_epoch, end_epoch in date_ranges:
    if start_epoch is not None and epoch < start_epoch:
      continue
    if end_epoch is not None and epoch > end_epoch:
      continue
    return True
  return False

def basename_epoch(base: str):
  match = pattern.search(base)
  if not match:
    return None
  key = match.group(1)
  yy = int(key[0:2])
  doy = int(key[2:5])
  hh = int(key[5:7])
  mm = int(key[7:9])
  ss = int(key[9:11])
  if doy < 1 or doy > 366:
    return None
  ts = dt.datetime(2000 + yy, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)
  return int(ts.timestamp())

rows = []
with open(raw_path, newline="") as handle:
  reader = csv.reader(handle)
  header = next(reader, None)
  for row in reader:
    if len(row) < 3:
      continue
    base = row[0].strip()
    try:
      size = float(row[1])
    except Exception:
      continue
    try:
      dt_val = float(row[2])
    except Exception:
      dt_val = None
    if size < min_bytes:
      continue
    if max_bytes > 0 and size > max_bytes:
      continue
    if dt_val is not None and dt_val < min_gap:
      continue
    if date_filter_enabled:
      epoch = basename_epoch(base)
      if epoch is None:
        continue
      if not is_in_selected_ranges(epoch):
        continue
    rows.append((base, size, dt_val))

with open(out_path, "w", newline="") as handle:
  writer = csv.writer(handle)
  writer.writerow(["basename", "filesize_bytes", "minutes_to_next"])
  for base, size, dt_val in rows:
    writer.writerow([base, int(size), "" if dt_val is None else f"{dt_val:.3f}"])
PY
  then
    filtered_plot_csv="$tmp_filtered_plot"
    tmp_files_to_cleanup+=("$tmp_filtered_plot")
    return 0
  else
    rm -f "$tmp_filtered_plot"
    return 1
  fi
}

build_qa_retry_manifest() {
  local summary now_ts
  now_ts="$(date '+%Y-%m-%d %H:%M:%S')"
  if ! summary=$(
    PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m MINGO_ANALYSIS.MINGO_ANALYSIS_SCRIPTS.common.reprocessing_qa_retry build-manifest \
      --config-path "$config_file_shared" \
      --config-path "$config_file_step" \
      --station "$station" \
      --clean-csv "$clean_csv" \
      --output-csv "$qa_retry_manifest_csv" \
      --state-csv "$qa_retry_state_csv" \
      --now-timestamp "$now_ts"
  ); then
    return 1
  fi
  log_info "QA retry manifest refreshed: ${summary}"
}

filter_existing_raw_csv() {
  local stats
  if [[ ! -s "$raw_csv" ]]; then
    log_info "Raw metadata CSV ${raw_csv} is missing; run with --refresh-metadata first." >&2
    return 1
  fi

  local tmp_filtered_plot tmp_clean
  tmp_filtered_plot=$(mktemp) || return 1
  tmp_clean=$(mktemp) || { rm -f "$tmp_filtered_plot"; return 1; }

  if stats=$(RAW_CSV="$raw_csv" OUT_FILTERED="$tmp_filtered_plot" OUT_CLEAN="$tmp_clean" MIN_BYTES="$min_filesize_bytes" MAX_BYTES="$max_filesize_bytes" MIN_GAP_MIN="$min_gap_minutes" DATE_RANGE_EPOCHS="$date_ranges_epoch_pairs" python3 <<'PY'
import csv
import datetime as dt
import os
import re

raw_path = os.environ["RAW_CSV"]
out_filtered = os.environ["OUT_FILTERED"]
out_clean = os.environ["OUT_CLEAN"]
min_bytes = int(os.environ.get("MIN_BYTES", "0") or 0)
max_bytes = int(os.environ.get("MAX_BYTES", "0") or 0)
min_gap = float(os.environ.get("MIN_GAP_MIN", "0") or 0.0)
date_ranges_env = os.environ.get("DATE_RANGE_EPOCHS", "").strip()
date_ranges = []
if date_ranges_env:
  for chunk in date_ranges_env.split(";"):
    chunk = chunk.strip()
    if not chunk or "," not in chunk:
      continue
    start_raw, end_raw = chunk.split(",", 1)
    start_raw = start_raw.strip()
    end_raw = end_raw.strip()
    start_epoch = int(start_raw) if start_raw else None
    end_epoch = int(end_raw) if end_raw else None
    if start_epoch is None and end_epoch is None:
      continue
    date_ranges.append((start_epoch, end_epoch))
date_filter_enabled = bool(date_ranges)

pattern = re.compile(r"([0-9]{11})$")
epoch_zero = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

def is_in_selected_ranges(epoch: int) -> bool:
  for start_epoch, end_epoch in date_ranges:
    if start_epoch is not None and epoch < start_epoch:
      continue
    if end_epoch is not None and epoch > end_epoch:
      continue
    return True
  return False

def parse_ts(base: str):
  m = pattern.search(base)
  if not m:
    return None
  key = m.group(1)
  try:
    yy = int(key[0:2]); doy = int(key[2:5]); hh = int(key[5:7]); mm = int(key[7:9]); ss = int(key[9:11])
  except Exception:
    return None
  if not (1 <= doy <= 366):
    return None
  try:
    return dt.datetime(2000 + yy, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)
  except Exception:
    return None

bases = []
sizes = []
minutes = []

with open(raw_path, newline="") as handle:
  reader = csv.reader(handle)
  header = next(reader, None)
  for row in reader:
    if not row:
      continue
    base = row[0].strip()
    if not base:
      continue
    try:
      size = float(row[1]) if len(row) > 1 else 0.0
    except Exception:
      size = 0.0
    dt_val = None
    if len(row) > 2 and row[2].strip():
      try:
        dt_val = float(row[2])
      except Exception:
        dt_val = None
    bases.append(base)
    sizes.append(size)
    minutes.append(dt_val)

total = len(bases)
timestamps = [parse_ts(b) for b in bases]
epochs = []
for ts in timestamps:
  if ts is None:
    epochs.append(None)
  else:
    delta = ts - epoch_zero
    epochs.append(int(delta.total_seconds()))

for i in range(total):
  if minutes[i] is None:
    if i + 1 < total and timestamps[i] and timestamps[i + 1]:
      delta = (timestamps[i + 1] - timestamps[i]).total_seconds() / 60.0
      if delta >= 0:
        minutes[i] = delta

filtered = []
removed_low = removed_high = removed_gap = removed_date = 0
for base, size, dt_val, epoch in zip(bases, sizes, minutes, epochs):
  if size < min_bytes:
    removed_low += 1
    continue
  if max_bytes > 0 and size > max_bytes:
    removed_high += 1
    continue
  if dt_val is not None and dt_val < min_gap:
    removed_gap += 1
    continue
  if date_filter_enabled:
    if epoch is None or not is_in_selected_ranges(epoch):
      removed_date += 1
      continue
  filtered.append((base, int(size), "" if dt_val is None else f"{dt_val:.3f}"))

with open(out_filtered, "w", newline="") as handle:
  writer = csv.writer(handle)
  writer.writerow(["basename", "filesize_bytes", "minutes_to_next"])
  writer.writerows(filtered)

with open(out_clean, "w", newline="") as handle:
  writer = csv.writer(handle)
  writer.writerow(["basename"])
  for base, _, _ in filtered:
    writer.writerow([base])

print(f"{len(bases)},{len(filtered)},{removed_low},{removed_high},{removed_gap},{removed_date}")
PY
  ); then
    IFS=',' read -r raw_count clean_count removed_low removed_high removed_gap removed_date <<<"$stats"
    removed_date=${removed_date:-0}
    mv "$tmp_clean" "$clean_csv"
    filtered_plot_csv="$tmp_filtered_plot"
    tmp_files_to_cleanup+=("$filtered_plot_csv")
    log_info "Metadata filtering (existing raw): raw=${raw_count} entries, clean=${clean_count} entries. Filtered out (size low=${removed_low}, size high=${removed_high}, gap=${removed_gap}, date_range=${removed_date})."
    return 0
  else
    rm -f "$tmp_filtered_plot" "$tmp_clean"
    return 1
  fi
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

# Returns 0 (true) when the epoch should be skipped due to the configured date range.
should_skip_due_to_date_range() {
  local epoch="$1"
  if ! $date_range_filter_enabled; then
    return 1
  fi
  if [[ -z "$epoch" ]]; then
    return 0
  fi
  local current=$((10#$epoch))
  local idx start_epoch end_epoch
  for idx in "${!date_ranges_start_epochs[@]}"; do
    start_epoch="${date_ranges_start_epochs[idx]}"
    end_epoch="${date_ranges_end_epochs[idx]}"
    if [[ -n "$start_epoch" ]] && (( current < 10#$start_epoch )); then
      continue
    fi
    if [[ -n "$end_epoch" ]] && (( current > 10#$end_epoch )); then
      continue
    fi
    return 1
  done
  return 0
}

filter_close_metadata_entries() {
  local csv_file="$1"
  if [[ ! -s "$csv_file" ]]; then
    return 0
  fi

  local header
  if ! header=$(head -n1 "$csv_file"); then
    return 1
  fi

  local -a basenames=()
  local -a lines=()
  while IFS= read -r line; do
    line=${line//$'\r'/}
    [[ -z "$line" ]] && continue
    basenames+=("${line%%,*}")
    lines+=("$line")
  done < <(tail -n +2 "$csv_file")

  local total=${#basenames[@]}
  if (( total == 0 )); then
    return 0
  fi
  local gap_limit=${min_gap_seconds:-600}

  local -a keep_flags
  keep_flags=()
  for ((i = 0; i < total; i++)); do
    keep_flags[i]=1
  done

  for ((i = 0; i < total - 1; i++)); do
    local prev="${basenames[i]}"
    local next="${basenames[i + 1]}"
    [[ -z "$prev" || -z "$next" ]] && continue
    local prev_epoch next_epoch
    if ! prev_epoch=$(basename_to_epoch "$prev"); then
      continue
    fi
    if ! next_epoch=$(basename_to_epoch "$next"); then
      continue
    fi
    local delta=$((next_epoch - prev_epoch))
    if (( delta >= 0 && delta < gap_limit )); then
      keep_flags[i]=0
    fi
  done

  local tmp_filtered
  tmp_filtered=$(mktemp) || return 1
  printf '%s\n' "$header" > "$tmp_filtered"
  local removed=0
  for ((i = 0; i < total; i++)); do
    if (( keep_flags[i] == 1 )); then
      printf '%s\n' "${lines[i]}" >>"$tmp_filtered"
    else
      ((removed++))
    fi
  done

  if (( removed > 0 )); then
    mv "$tmp_filtered" "$csv_file"
    local gap_minutes_display=$((gap_limit / 60))
    log_info "Metadata filter removed ${removed} basename(s) closer than ${gap_minutes_display} minutes apart."
  else
    rm -f "$tmp_filtered"
  fi
}

filter_file_sizes() {
  local csv_file="$1"
  local min_bytes="$2"
  local max_bytes="$3"
  if [[ ! -s "$csv_file" ]]; then
    return 0
  fi

  local header
  if ! IFS= read -r header < "$csv_file"; then
    return 1
  fi

  local tmp_filtered
  tmp_filtered=$(mktemp) || return 1
  printf '%s\n' "$header" > "$tmp_filtered"

  local removed=0
  local kept=0
  local removed_low=0
  local removed_high=0
  while IFS= read -r line; do
    line=${line//$'\r'/}
    [[ -z "$line" ]] && continue
    local base size_bytes
    base=${line%%,*}
    size_bytes=${line#*,}
    if [[ -z "$size_bytes" || ! "$size_bytes" =~ ^[0-9]+$ ]]; then
      ((removed++))
      continue
    fi
    if (( size_bytes < min_bytes )); then
      ((removed++))
      ((removed_low++))
      continue
    fi
    if (( max_bytes > 0 && size_bytes > max_bytes )); then
      ((removed++))
      ((removed_high++))
      continue
    fi
    if (( size_bytes >= min_bytes )); then
      printf '%s\n' "$line" >>"$tmp_filtered"
      ((kept++))
    else
      ((removed++))
    fi
  done < <(tail -n +2 "$csv_file")

  if (( removed > 0 )); then
    mv "$tmp_filtered" "$csv_file"
    local upper_display="${max_bytes}"
    if (( max_bytes <= 0 )); then
      upper_display="inf"
    fi
    log_info "Metadata filter removed ${removed} file(s) outside size bounds [${min_bytes}, ${upper_display}] bytes; kept ${kept}. (low=${removed_low}, high=${removed_high})"
  else
    rm -f "$tmp_filtered"
  fi
}

ensure_metadata_tracking_csv() {
  if [[ ! -f "$metadata_tracking_csv" || ! -s "$metadata_tracking_csv" ]]; then
    printf '%s\n' "$metadata_tracking_header" > "$metadata_tracking_csv"
  fi
}

record_metadata_history() {
  local raw_total="$1"
  local clean_total="$2"
  ensure_metadata_tracking_csv
  printf '%s,%s,%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$raw_total" "$clean_total" >> "$metadata_tracking_csv"
}

raw_csv_signature() {
  local csv_path="$1"
  if [[ ! -e "$csv_path" ]]; then
    printf 'missing'
    return 0
  fi
  stat -c '%s:%Y' "$csv_path" 2>/dev/null || printf 'unknown'
}

calculate_filter_fingerprint() {
  local raw_signature payload
  raw_signature=$(raw_csv_signature "$raw_csv")
  payload=$(
    cat <<EOF
version=${filter_state_version}
station=${station}
raw_signature=${raw_signature}
min_filesize_bytes=${min_filesize_bytes}
max_filesize_bytes=${max_filesize_bytes}
min_gap_minutes=${min_gap_minutes}
date_ranges_epoch_pairs=${date_ranges_epoch_pairs}
EOF
  )

  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$payload" | sha256sum | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    printf '%s' "$payload" | shasum -a 256 | awk '{print $1}'
  else
    printf '%s' "$payload" | cksum | awk '{print $1 ":" $2}'
  fi
}

saved_filter_fingerprint() {
  if [[ ! -f "$filter_state_file" ]]; then
    printf ''
    return 0
  fi
  awk -F= '$1=="fingerprint"{print $2; exit}' "$filter_state_file" 2>/dev/null || true
}

write_filter_state_file() {
  local fingerprint="$1"
  local raw_signature
  raw_signature=$(raw_csv_signature "$raw_csv")

  {
    printf 'version=%s\n' "$filter_state_version"
    printf 'updated_at=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')"
    printf 'station=%s\n' "$station"
    printf 'raw_csv=%s\n' "$raw_csv"
    printf 'raw_signature=%s\n' "$raw_signature"
    printf 'min_filesize_bytes=%s\n' "$min_filesize_bytes"
    printf 'max_filesize_bytes=%s\n' "$max_filesize_bytes"
    printf 'min_gap_minutes=%s\n' "$min_gap_minutes"
    printf 'date_ranges_epoch_pairs=%s\n' "$date_ranges_epoch_pairs"
    printf 'fingerprint=%s\n' "$fingerprint"
  } > "$filter_state_file"
}

should_skip_filter_rebuild() {
  [[ -s "$raw_csv" ]] || return 1
  [[ -s "$clean_csv" ]] || return 1

  local current saved
  current=$(calculate_filter_fingerprint)
  saved=$(saved_filter_fingerprint)
  [[ -n "$current" && -n "$saved" && "$current" == "$saved" ]]
}

rebuild_clean_metadata_if_needed() {
  if should_skip_filter_rebuild; then
    log_info "Metadata filtering skipped: raw metadata and filter settings (including date range(s)) are unchanged."
    return 0
  fi

  if filter_existing_raw_csv; then
    local fp
    fp=$(calculate_filter_fingerprint)
    if [[ -n "$fp" ]]; then
      write_filter_state_file "$fp"
    fi
    return 0
  fi
  return 1
}

plot_metadata_time_deltas() {
  local csv_file="$1"
  local station_label="$2"
  local plot_dir="$3"

  if [[ ! -s "$csv_file" ]]; then
    log_info "Metadata CSV ${csv_file} is empty; skipping histogram generation."
    return 1
  fi

  mkdir -p "$plot_dir" || return 1
  local plot_path="${plot_dir}/metadata_time_differences_${station_label}.pdf"

  if PLOT_CSV="$csv_file" PLOT_PATH="$plot_path" STATION_LABEL="$station_label" MAX_GAP_MINUTES="$max_gap_minutes" python3 <<'PY'
import csv
import datetime as dt
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv_path = os.environ["PLOT_CSV"]
plot_path = os.environ["PLOT_PATH"]
station_label = os.environ.get("STATION_LABEL", "")

basenames = []
with open(csv_path, newline="") as handle:
  reader = csv.reader(handle)
  next(reader, None)
  for row in reader:
    if not row:
      continue
    base = row[0].strip()
    if base:
      basenames.append(base)

pattern = re.compile(r"([0-9]{11})$")
timestamps = []
for base in basenames:
  match = pattern.search(base)
  if not match:
    continue
  key = match.group(1)
  yy = int(key[0:2])
  doy = int(key[2:5])
  hh = int(key[5:7])
  mm = int(key[7:9])
  ss = int(key[9:11])
  if doy < 1 or doy > 366:
    continue
  year = 2000 + yy
  ts = dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)
  timestamps.append(ts)

timestamps.sort()

title = f"Metadata time differences for {station_label}" if station_label else "Metadata time differences"
try:
  max_range = float(os.environ.get("MAX_GAP_MINUTES", "0"))
except Exception:
  max_range = 0.0

def render_message(message: str) -> None:
  fig, ax = plt.subplots(figsize=(8, 4.5))
  ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12)
  ax.set_axis_off()
  fig.suptitle(title)
  fig.tight_layout()
  fig.savefig(plot_path, format="pdf")
  plt.close(fig)

if len(timestamps) < 2:
  render_message("Not enough metadata entries\nto compute time differences.")
else:
  diffs = []
  for idx in range(len(timestamps) - 1):
    delta = timestamps[idx + 1] - timestamps[idx]
    minutes = delta.total_seconds() / 60.0
    if minutes < 0:
      continue
    if max_range > 0 and minutes > max_range:
      continue
    diffs.append(minutes)

  if not diffs:
    msg = "No metadata time differences"
    if max_range > 0:
      msg += f" within 0-{max_range:.0f} minutes."
    render_message(msg)
  else:
    bins = "auto" if len(diffs) > 1 else 1
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(diffs, bins=bins, color="#1f77b4", edgecolor="black", alpha=0.8)
    if max_range > 0:
      ax.set_xlim(0, max_range)
    ax.set_title(title)
    if max_range > 0:
      ax.set_xlabel(f"Minutes between consecutive files (0-{max_range:.0f})")
    else:
      ax.set_xlabel("Minutes between consecutive files")
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(plot_path, format="pdf")
    plt.close(fig)
PY
  then
    log_info "Histogram of metadata time differences saved to ${plot_path}"
    return 0
  else
    log_info "Failed to create metadata histogram at ${plot_path}" >&2
    return 1
  fi
}

plot_metadata_file_sizes() {
  local csv_file="$1"
  local station_label="$2"
  local plot_dir="$3"
  local min_mb="$4"
  local max_mb="$5"

  if [[ ! -s "$csv_file" ]]; then
    log_info "Metadata CSV ${csv_file} is empty; skipping filesize histogram generation."
    return 1
  fi

  mkdir -p "$plot_dir" || return 1
  local plot_path="${plot_dir}/metadata_file_sizes_${station_label}.pdf"

  if PLOT_CSV="$csv_file" PLOT_PATH="$plot_path" STATION_LABEL="$station_label" MIN_MB="$min_mb" MAX_MB="$max_mb" python3 <<'PY'
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv_path = os.environ["PLOT_CSV"]
plot_path = os.environ["PLOT_PATH"]
station_label = os.environ.get("STATION_LABEL", "")
min_mb = float(os.environ.get("MIN_MB", "0.0"))
max_mb = float(os.environ.get("MAX_MB", "0.0"))

sizes_mb = []
with open(csv_path, newline="") as handle:
  reader = csv.reader(handle)
  next(reader, None)
  for row in reader:
    if len(row) < 2:
      continue
    try:
      size_bytes = float(row[1])
    except ValueError:
      continue
    if size_bytes < 0:
      continue
    sizes_mb.append(size_bytes / (1024 * 1024))

title = f"Metadata file sizes for {station_label}" if station_label else "Metadata file sizes"

def render_message(message: str) -> None:
  fig, ax = plt.subplots(figsize=(8, 4.5))
  ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12)
  ax.set_axis_off()
  fig.suptitle(title)
  fig.tight_layout()
  fig.savefig(plot_path, format="pdf")
  plt.close(fig)

if not sizes_mb:
  render_message("No file sizes available for histogram.")
else:
  bins = "auto" if len(sizes_mb) > 1 else 1
  fig, ax = plt.subplots(figsize=(10, 6))
  ax.hist(sizes_mb, bins=bins, color="#ff7f0e", edgecolor="black", alpha=0.8)
  if min_mb > 0:
    ax.axvline(min_mb, color="red", linestyle="--", linewidth=1.5, label=f"Min size {min_mb:.2f} MB")
  if max_mb > 0:
    ax.axvline(max_mb, color="green", linestyle="--", linewidth=1.5, label=f"Max size {max_mb:.2f} MB")
  if min_mb > 0 or max_mb > 0:
    ax.legend()
  ax.set_title(title)
  ax.set_xlabel("File size (MB)")
  ax.set_ylabel("Count")
  ax.grid(axis="y", alpha=0.3)
  fig.tight_layout()
  fig.savefig(plot_path, format="pdf")
  plt.close(fig)
PY
  then
    log_info "Histogram of metadata file sizes saved to ${plot_path}"
    return 0
  else
    log_info "Failed to create metadata filesize histogram at ${plot_path}" >&2
    return 1
  fi
}

plot_size_vs_time_delta() {
  local csv_file="$1"
  local station_label="$2"
  local plot_dir="$3"
  local prefix="$4"
  local min_mb="${5:-0}"
  local max_mb="${6:-0}"

  if [[ ! -s "$csv_file" ]]; then
    log_info "Metadata CSV ${csv_file} is empty; skipping size vs duration scatter (${prefix})."
    return 1
  fi

  mkdir -p "$plot_dir" || return 1
  local plot_path="${plot_dir}/metadata_size_vs_dt_${prefix}_${station_label}.pdf"

  if PLOT_CSV="$csv_file" PLOT_PATH="$plot_path" STATION_LABEL="$station_label" MAX_GAP_MINUTES="$max_gap_minutes" MIN_MB="$min_mb" MAX_MB="$max_mb" python3 <<'PY'
import csv
import datetime as dt
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

csv_path = os.environ["PLOT_CSV"]
plot_path = os.environ["PLOT_PATH"]
station_label = os.environ.get("STATION_LABEL", "")
try:
  max_range = float(os.environ.get("MAX_GAP_MINUTES", "0"))
except Exception:
  max_range = 0.0
try:
  min_mb = float(os.environ.get("MIN_MB", "0"))
except Exception:
  min_mb = 0.0
try:
  max_mb = float(os.environ.get("MAX_MB", "0"))
except Exception:
  max_mb = 0.0

rows = []
with open(csv_path, newline="") as handle:
  reader = csv.reader(handle)
  next(reader, None)
  for row in reader:
    if len(row) < 2:
      continue
    base = row[0].strip()
    try:
      size_bytes = float(row[1])
    except ValueError:
      continue
    size_mb = size_bytes / (1024 * 1024)
    if min_mb > 0 and size_mb < min_mb:
      continue
    if max_mb > 0 and size_mb > max_mb:
      continue
    rows.append((base, size_bytes))

pattern = re.compile(r"([0-9]{11})$")

def parse_ts(name: str):
  m = pattern.search(name)
  if not m:
    return None
  key = m.group(1)
  yy = int(key[0:2])
  doy = int(key[2:5])
  hh = int(key[5:7])
  mm = int(key[7:9])
  ss = int(key[9:11])
  if doy < 1 or doy > 366:
    return None
  try:
    return dt.datetime(2000 + yy, 1, 1) + dt.timedelta(days=doy - 1, hours=hh, minutes=mm, seconds=ss)
  except Exception:
    return None

rows_with_ts = []
for base, size in rows:
  ts = parse_ts(base)
  if ts is None:
    continue
  rows_with_ts.append((ts, size))

rows_with_ts.sort(key=lambda x: x[0])

if len(rows_with_ts) < 2:
  fig, ax = plt.subplots(figsize=(8, 4.5))
  ax.text(0.5, 0.5, "Not enough entries for scatter", ha="center", va="center", fontsize=12)
  ax.set_axis_off()
  fig.suptitle(f"Size vs duration for {station_label}")
  fig.tight_layout()
  fig.savefig(plot_path, format="pdf")
  plt.close(fig)
else:
  deltas = []
  sizes_mb = []
  for idx in range(len(rows_with_ts) - 1):
    t_cur, size_cur = rows_with_ts[idx]
    t_next, _ = rows_with_ts[idx + 1]
    delta_min = (t_next - t_cur).total_seconds() / 60.0
    if delta_min < 0:
      continue
    if max_range > 0 and delta_min > max_range:
      continue
    deltas.append(delta_min)
    sizes_mb.append(size_cur / (1024 * 1024))

  fig, ax = plt.subplots(figsize=(10, 6))
  ax.scatter(deltas, sizes_mb, s=1, alpha=0.6, color="#2ca02c")
  if deltas:
    min_delta = min(deltas)
    max_delta = max_range if max_range > 0 else max(deltas)
    ax.set_xlim(min_delta, max_delta)
    label_range = f"{min_delta:.0f}-{max_delta:.0f}" if max_range > 0 else "data range"
  else:
    label_range = ""
  if max_range > 0:
    ax.set_xlabel(f"Minutes until next file ({label_range or f'0-{max_range:.0f}'})")
  else:
    ax.set_xlabel("Minutes until next file" + (f" ({label_range})" if label_range else ""))
  ax.set_ylabel("File size (MB)")
  ax.set_title(f"Size vs duration for {station_label} (per file)")
  ax.grid(alpha=0.3)
  fig.tight_layout()
  fig.savefig(plot_path, format="pdf")
  plt.close(fig)
PY
  then
    log_info "Scatter size vs duration saved to ${plot_path}"
    return 0
  else
    log_info "Failed to create size vs duration scatter at ${plot_path}" >&2
    return 1
  fi
}

raw_csv_is_fresh_and_nonempty() {
  local csv_path="$1"
  local max_age_seconds="$2"

  [[ -s "$csv_path" ]] || return 1
  [[ "$max_age_seconds" =~ ^[0-9]+$ ]] || return 1

  local modified_epoch now_epoch age_seconds
  if ! modified_epoch=$(stat -c %Y "$csv_path" 2>/dev/null); then
    return 1
  fi
  now_epoch=$(date +%s)
  age_seconds=$((now_epoch - modified_epoch))
  if (( age_seconds < 0 )); then
    age_seconds=0
  fi

  (( age_seconds <= max_age_seconds ))
}

refresh_metadata_csv() {
  if raw_csv_is_fresh_and_nonempty "$raw_csv" "$raw_csv_max_age_seconds"; then
    log_info "Skipping remote metadata refresh: ${raw_csv} is non-empty and not older than ${raw_csv_max_age_days} day(s)."
    return 0
  fi

  log_info "Refreshing metadata CSV for MINGO0${station} from remote listing..."

  local tmp_listing
  tmp_listing=$(mktemp) || return 1
  if ! ssh -o BatchMode=yes "${remote_user}@${remote_host}" "cd ${remote_dir_escaped} && find . -maxdepth 1 -type f \\( -name '*.hld' -o -name '*.hld.tar.gz' -o -name '*.hld-tar-gz' -o -name '*.tar.gz' -o -name '*.dat' \\) -printf '%f,%s\n'" > "$tmp_listing"; then
    log_warn "unable to refresh metadata; could not list remote directory ${remote_user}@${remote_host}:${remote_dir}"
    rm -f "$tmp_listing"
    return 1
  fi

  declare -A refreshed_bases=()
  declare -A base_sizes=()
  local remote_entry
  while IFS= read -r remote_entry; do
    remote_entry=${remote_entry//$'\r'/}
    [[ -z "$remote_entry" ]] && continue
    local file_name file_size
    file_name=${remote_entry%%,*}
    file_size=${remote_entry#*,}
    [[ -z "$file_name" ]] && continue
    [[ $file_name =~ \.hld ]] || continue
    if [[ -z "$file_size" || ! "$file_size" =~ ^[0-9]+$ ]]; then
      file_size=0
    fi
    local base
    base=$(strip_suffix "$file_name")
    [[ -z "$base" ]] && continue
    [[ $base =~ ^(mi|minI) ]] || continue
    refreshed_bases["$base"]=1
    if [[ -n ${base_sizes["$base"]:-} ]]; then
      if (( file_size > base_sizes["$base"] )); then
        base_sizes["$base"]=$file_size
      fi
    else
      base_sizes["$base"]=$file_size
    fi
  done < "$tmp_listing"
  rm -f "$tmp_listing"

  if (( ${#refreshed_bases[@]} == 0 )); then
    log_info "Metadata refresh found no basenames; existing CSV left unchanged."
    return 1
  fi

  local tmp_sorted
  tmp_sorted=$(mktemp) || return 1
  printf '%s\n' "${!refreshed_bases[@]}" | sort > "$tmp_sorted"

  # Build entries with epochs and minutes_to_next
  local -a bases epochs sizes minutes_to_next entries_filtered
  while IFS= read -r base; do
    bases+=("$base")
    sizes+=("${base_sizes[$base]:-0}")
    if epoch_val=$(basename_to_epoch "$base"); then
      epochs+=("$epoch_val")
    else
      epochs+=("")
    fi
  done < "$tmp_sorted"

  local total=${#bases[@]}
  minutes_to_next=()
  for ((i = 0; i < total; i++)); do
    local curr_epoch="${epochs[i]}"
    local next_epoch=""
    if (( i + 1 < total )); then
      next_epoch="${epochs[i + 1]}"
    fi
    if [[ -n "$curr_epoch" && -n "$next_epoch" ]]; then
      local delta_sec=$((next_epoch - curr_epoch))
      if (( delta_sec >= 0 )); then
        minutes_to_next[i]=$(DELTA="$delta_sec" python3 - <<'PY'
import os
delta = int(os.environ.get("DELTA", "0"))
print(f"{delta/60:.3f}")
PY
        )
      else
        minutes_to_next[i]=""
      fi
    else
      minutes_to_next[i]=""
    fi
  done

  {
    printf '%s\n' "$csv_header"
    for ((i = 0; i < total; i++)); do
      printf '%s,%s,%s\n' "${bases[i]}" "${sizes[i]}" "${minutes_to_next[i]}"
    done
  } > "$raw_csv"

  # Filter using size and min-gap (toward next file)
  entries_filtered=()
  local removed_size_low=0 removed_size_high=0 removed_gap=0 removed_date=0 kept=0
  for ((i = 0; i < total; i++)); do
    local base="${bases[i]}"
    local size_bytes="${sizes[i]}"
    local dt_min="${minutes_to_next[i]}"
    local epoch="${epochs[i]}"

    if [[ -z "$size_bytes" || ! "$size_bytes" =~ ^[0-9]+$ ]]; then
      ((removed_size_low++))
      continue
    fi
    if (( size_bytes < min_filesize_bytes )); then
      ((removed_size_low++))
      continue
    fi
    if (( max_filesize_bytes > 0 && size_bytes > max_filesize_bytes )); then
      ((removed_size_high++))
      continue
    fi

    if [[ -n "$dt_min" ]]; then
      # dt_min is a float string; compare using python for simplicity
      if ! DT_MIN="$dt_min" MIN_GAP="$min_gap_minutes" python3 - <<'PY'
import os, sys
dt = float(os.environ.get("DT_MIN", "0"))
min_gap = float(os.environ.get("MIN_GAP", "0"))
sys.exit(0 if dt >= min_gap else 1)
PY
      then
        ((removed_gap++))
        continue
      fi
    fi

    if should_skip_due_to_date_range "$epoch"; then
      ((removed_date++))
      continue
    fi

    entries_filtered+=("$base,${size_bytes},${dt_min}")
    ((kept++))
  done

  # Write clean CSV with only basename column
  {
    printf 'basename\n'
    for entry in "${entries_filtered[@]}"; do
      printf '%s\n' "${entry%%,*}"
    done
  } > "$clean_csv"

  # Prepare filtered data CSV for plotting (full columns)
  local tmp_filtered_plot
  tmp_filtered_plot=$(mktemp)
  tmp_files_to_cleanup+=("$tmp_filtered_plot")
  {
    printf '%s\n' "$csv_header"
    for entry in "${entries_filtered[@]}"; do
      printf '%s\n' "$entry"
    done
  } > "$tmp_filtered_plot"
  filtered_plot_csv="$tmp_filtered_plot"

  local raw_count clean_count
  raw_count=$total
  clean_count=$kept
  log_info "Metadata CSV refreshed: raw=${raw_count} entries, clean=${clean_count} entries."
  log_info "Filtered out (size low=${removed_size_low}, size high=${removed_size_high}, gap=${removed_gap}, date_range=${removed_date})."

  record_metadata_history "$raw_count" "$clean_count"

  rm -f "$tmp_sorted"
  return 0
}

# Load thresholds (overrides defaults with station-specific config if present)
load_time_thresholds "$station"
load_size_thresholds "$station"

if $update_range_only; then
  log_info "Rebuilding clean metadata from existing remote_database_${station}.csv using the configured date range(s) thresholds."
fi

if $refresh_metadata; then
  if refresh_metadata_csv; then
    log_info "Metadata refresh completed."
  else
    log_info "Metadata refresh could not update the CSV; continuing with existing entries."
  fi
  # Rebuild clean/plot CSVs only when raw metadata or filter settings changed.
  rebuild_clean_metadata_if_needed || {
    log_info "Unable to build clean metadata from refreshed raw CSV; aborting." >&2
    exit 1
  }
else
  rebuild_clean_metadata_if_needed || {
    log_info "Unable to build clean metadata from existing raw CSV; aborting." >&2
    exit 1
  }
fi

if $plot_hist; then
  if [[ ! -s "$clean_csv" ]]; then
    log_info "Clean metadata CSV ${clean_csv} is missing; run with --refresh-metadata first." >&2
    exit 1
  fi
  if [[ -s "$raw_csv" ]]; then
    plot_size_vs_time_delta "$raw_csv" "MINGO0${station}" "$plots_directory" "before_filter" 0 0 || true
  fi
  ensure_filtered_plot_csv || true
  filtered_source="${filtered_plot_csv:-$raw_csv}"
  if [[ -s "$filtered_source" ]]; then
    plot_metadata_time_deltas "$filtered_source" "MINGO0${station}" "$plots_directory" || true
    plot_metadata_file_sizes "$filtered_source" "MINGO0${station}" "$plots_directory" "$min_filesize_mb" "$max_filesize_mb" || true
    plot_size_vs_time_delta "$filtered_source" "MINGO0${station}" "$plots_directory" "after_filter" "$min_filesize_mb" "$max_filesize_mb" || true
  else
    log_info "Filtered plot CSV missing; skipping filtered plots."
  fi
fi

build_qa_retry_manifest || {
  log_warn "Unable to rebuild QA retry manifest for station ${station}."
  exit 1
}

log_info "STEP_0 metadata preparation finished."
