#!/usr/bin/env bash
# Purpose: Copy the latest selected STEP-1 PDF reports into the documentation assets.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../../" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/quick_check_plots.conf"

OUTPUT_DIR="${REPO_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/PLOT_SCHEDULE/QUICK_CHECK_PLOTS/PLOTS"
RUNTIME_DIR="${REPO_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/PLOT_SCHEDULE/QUICK_CHECK_PLOTS/RUNTIME"
LAST_RUN_FILE="${RUNTIME_DIR}/last_sync_epoch"
SOURCE_ROOT="${REPO_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS"

SYNC_INTERVAL_MINUTES=1
if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

if [[ ! "${SYNC_INTERVAL_MINUTES}" =~ ^[0-9]+$ ]]; then
  echo "Invalid SYNC_INTERVAL_MINUTES='${SYNC_INTERVAL_MINUTES}' in ${CONFIG_FILE}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}" "${RUNTIME_DIR}"

now_epoch="$(date +%s)"
interval_seconds="$((SYNC_INTERVAL_MINUTES * 60))"
if [[ -f "${LAST_RUN_FILE}" && "${interval_seconds}" -gt 0 ]]; then
  last_run_epoch="$(<"${LAST_RUN_FILE}")"
  if [[ "${last_run_epoch}" =~ ^[0-9]+$ ]] && (( now_epoch - last_run_epoch < interval_seconds )); then
    exit 0
  fi
fi

copied_count=0
updated_count=0
unchanged_count=0
scanned_count=0

while IFS= read -r -d '' pdf_dir; do
  rel_path="${pdf_dir#${SOURCE_ROOT}/}"
  if [[ ! "${rel_path}" =~ ^(MINGO0[0-9])/STAGE_1/EVENT_DATA/STEP_1/(TASK_[0-9]+)/PLOTS/PDF_DIRECTORY$ ]]; then
    continue
  fi
  station_name="${BASH_REMATCH[1]}"
  task_name="${BASH_REMATCH[2]}"

  if [[ ! "${station_name}" =~ ^MINGO0[0-9]$ ]]; then
    continue
  fi
  if [[ ! "${task_name}" =~ ^TASK_[0-9]+$ ]]; then
    continue
  fi

  latest_pdf="$(
    find "${pdf_dir}" -maxdepth 1 -type f -iname '*.pdf' -printf '%T@\t%p\n' 2>/dev/null \
      | sort -n \
      | tail -n 1 \
      | cut -f2-
  )"
  if [[ -z "${latest_pdf}" ]]; then
    continue
  fi

  scanned_count=$((scanned_count + 1))
  latest_base="$(basename "${latest_pdf}")"
  managed_prefix="${station_name}__${task_name}__"
  dest_path="${OUTPUT_DIR}/${managed_prefix}${latest_base}"

  shopt -s nullglob
  matches=( "${OUTPUT_DIR}/${managed_prefix}"*.pdf )
  shopt -u nullglob

  needs_copy=0
  if [[ ! -f "${dest_path}" ]]; then
    needs_copy=1
  elif [[ "${latest_pdf}" -nt "${dest_path}" ]]; then
    needs_copy=1
  fi

  if (( ${#matches[@]} > 1 )); then
    needs_copy=1
  elif (( ${#matches[@]} == 1 )) && [[ "${matches[0]}" != "${dest_path}" ]]; then
    needs_copy=1
  fi

  if (( needs_copy == 0 )); then
    unchanged_count=$((unchanged_count + 1))
    continue
  fi

  for existing in "${matches[@]}"; do
    if [[ "${existing}" != "${dest_path}" ]]; then
      rm -f -- "${existing}"
    fi
  done

  existed_before=0
  if [[ -f "${dest_path}" ]]; then
    existed_before=1
  fi

  cp -pf -- "${latest_pdf}" "${dest_path}"
  if (( existed_before == 1 )); then
    updated_count=$((updated_count + 1))
  else
    copied_count=$((copied_count + 1))
  fi
done < <(
  find "${SOURCE_ROOT}" \
    -path '*/STAGE_1/EVENT_DATA/STEP_1/TASK_*/PLOTS/PDF_DIRECTORY' \
    -type d \
    -print0
)

printf '%s\n' "${now_epoch}" > "${LAST_RUN_FILE}"
printf '[%s] scanned=%d copied=%d updated=%d unchanged=%d\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" \
  "${scanned_count}" \
  "${copied_count}" \
  "${updated_count}" \
  "${unchanged_count}"
