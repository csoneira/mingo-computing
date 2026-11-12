#!/bin/bash
# Purpose: split_gas_logs.sh – demultiplex clean_gas_weight_measurements.log.

# ------------------------------------------------------------------
# split_gas_logs.sh – demultiplex clean_gas_weight_measurements.log
# into weight_YYYY-MM-DD.log files.  Current‑day entries remain in
# /home/rpcuser/logs; previous days are moved to /home/rpcuser/logs/done
# ------------------------------------------------------------------

LOG_DIR="~/logs"
DONE_DIR="${LOG_DIR}/done"
SRC_LOG="${LOG_DIR}/clean_gas_weight_measurements.log"

mkdir -p "${DONE_DIR}"

# Use a lock to avoid concurrent truncation by parallel bot invocations.
exec 200>"${SRC_LOG}.lock"
flock -x 200

# Bail out silently if there is nothing to process.
[[ ! -s "${SRC_LOG}" ]] && exit 0

TODAY=$(date '+%Y-%m-%d')

# Read and demultiplex.
while IFS= read -r LINE || [[ -n "${LINE}" ]]; do
    DATE_PART=$(printf '%s\n' "${LINE}" | awk '{print $1}')
    [[ -z "${DATE_PART}" ]] && continue   # skip malformed lines

    if [[ "${DATE_PART}" == "${TODAY}" ]]; then
        TARGET="${LOG_DIR}/weight_${DATE_PART}.log"
    else
        TARGET="${DONE_DIR}/weight_${DATE_PART}.log"
    fi
    echo "${LINE}" >> "${TARGET}"
done < "${SRC_LOG}"

# Truncate the aggregate log now that entries have been dispatched.
: > "${SRC_LOG}"

exit 0
