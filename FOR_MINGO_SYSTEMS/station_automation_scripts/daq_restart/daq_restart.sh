#!/bin/bash
# Purpose: daq_restart.sh - restart DAQ when data is stale or missing.

# ------------------------------------------------------------------
# daq_restart.sh - restart DAQ when data is stale or missing.
#
# Logging policy:
#   - daq_restart.log contains concise operational events only.
#   - startup_TRB399.sh stdout/stderr is redirected to /dev/null so DAQ
#     daemons cannot inherit and keep writing to restart-owned log files.
#   - daq_restart_startup.log records bounded startup summaries only.
#   - both persistent logs are rotated by size in this script because the
#     generic station log cleaner does not cover these DAQ restart logs.
# ------------------------------------------------------------------

DATA_DIR="${DAQ_RESTART_DATA_DIR:-/home/rpcuser/gate/system/devices/TRB3/data/daqData/asci}"
STARTUP_SCRIPT="${DAQ_RESTART_STARTUP_SCRIPT:-/home/rpcuser/trbsoft/userscripts/trb/startup_TRB399.sh}"
LOG_DIR="${DAQ_RESTART_LOG_DIR:-/home/rpcuser/logs}"
LOG_FILE="${LOG_DIR}/daq_restart.log"
STARTUP_LOG="${LOG_DIR}/daq_restart_startup.log"
STATE_FILE="${LOG_DIR}/daq_restart.state"
MAIL_TO="csoneira.alarms@gmail.com"
MAIL_COUNT_FILE="${LOG_DIR}/daq_restart_no_file_mail_count"
THRESHOLD_SEC="${DAQ_RESTART_THRESHOLD_SEC:-$((2 * 60 * 60))}"
COOLDOWN_SEC="${DAQ_RESTART_COOLDOWN_SEC:-$((6 * 60 * 60))}"
MAX_CONSECUTIVE_RESTARTS="${DAQ_RESTART_MAX_CONSECUTIVE:-3}"
LOG_MAX_BYTES="${DAQ_RESTART_LOG_MAX_BYTES:-$((256 * 1024))}"
STARTUP_LOG_MAX_BYTES="${DAQ_RESTART_STARTUP_LOG_MAX_BYTES:-$((1024 * 1024))}"
ROTATE_KEEP="${DAQ_RESTART_ROTATE_KEEP:-5}"
STARTUP_TIMEOUT_SEC="${DAQ_RESTART_STARTUP_TIMEOUT_SEC:-$((5 * 60))}"
LOCK_FILE="${DAQ_RESTART_LOCK_FILE:-/tmp/daq_restart.lock}"
VERBOSE="0"

for arg in "$@"; do
    case "${arg}" in
        -v|--verbose) VERBOSE="1" ;;
    esac
done

mkdir -p "${LOG_DIR}"

rotate_file() {
    local file="$1"
    local max_bytes="$2"
    local keep="$3"
    local i

    [[ -f "${file}" ]] || return 0
    local size
    size=$(wc -c < "${file}" 2>/dev/null || echo 0)
    [[ "${size}" =~ ^[0-9]+$ ]] || size=0
    (( size <= max_bytes )) && return 0

    i=$((keep - 1))
    while (( i >= 1 )); do
        if [[ -e "${file}.${i}" ]]; then
            mv -f "${file}.${i}" "${file}.$((i + 1))"
        fi
        i=$((i - 1))
    done
    mv -f "${file}" "${file}.1"
    : > "${file}"
}

rotate_logs() {
    rotate_file "${LOG_FILE}" "${LOG_MAX_BYTES}" "${ROTATE_KEEP}"
    rotate_file "${STARTUP_LOG}" "${STARTUP_LOG_MAX_BYTES}" "${ROTATE_KEEP}"
}

log_msg() {
    rotate_logs
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "${LOG_FILE}"
    rotate_file "${LOG_FILE}" "${LOG_MAX_BYTES}" "${ROTATE_KEEP}"
}

vmsg() {
    [[ "${VERBOSE}" == "1" ]] && echo "$*"
}

load_state() {
    LAST_RESTART_EPOCH=0
    CONSECUTIVE_RESTARTS=0
    LAST_REASON=""
    LAST_EXIT_CODE=""

    [[ -f "${STATE_FILE}" ]] || return 0
    # shellcheck disable=SC1090
    . "${STATE_FILE}" 2>/dev/null || true
    [[ "${LAST_RESTART_EPOCH}" =~ ^[0-9]+$ ]] || LAST_RESTART_EPOCH=0
    [[ "${CONSECUTIVE_RESTARTS}" =~ ^[0-9]+$ ]] || CONSECUTIVE_RESTARTS=0
}

save_state() {
    local tmp_file="${STATE_FILE}.$$"
    {
        printf 'LAST_RESTART_EPOCH=%s\n' "${LAST_RESTART_EPOCH:-0}"
        printf 'CONSECUTIVE_RESTARTS=%s\n' "${CONSECUTIVE_RESTARTS:-0}"
        printf 'LAST_REASON=%q\n' "${LAST_REASON:-}"
        printf 'LAST_EXIT_CODE=%q\n' "${LAST_EXIT_CODE:-}"
    } > "${tmp_file}"
    mv -f "${tmp_file}" "${STATE_FILE}"
}

send_mail() {
    local subject body
    subject="DAQ restart: no data files found"
    body="DAQ restart triggered at $(date '+%Y-%m-%d %H:%M:%S').\nNo files found in ${DATA_DIR}.\nHost: $(hostname)"
    if command -v mail >/dev/null 2>&1; then
        printf '%b\n' "${body}" | mail -s "${subject}" "${MAIL_TO}"
        return $?
    fi
    if command -v mailx >/dev/null 2>&1; then
        printf '%b\n' "${body}" | mailx -s "${subject}" "${MAIL_TO}"
        return $?
    fi
    log_msg "WARN mailer not found mailers=mail,mailx"
    return 1
}

run_startup() {
    local exit_code start_epoch end_epoch duration_sec
    start_epoch=$(date +%s)

    # Close fd 200 for the startup command so DAQ daemons cannot inherit the
    # restart lock. Send stdout/stderr to /dev/null because startup_TRB399.sh
    # can spawn long-lived children that inherit open descriptors.
    if command -v timeout >/dev/null 2>&1; then
        timeout "${STARTUP_TIMEOUT_SEC}" "${STARTUP_SCRIPT}" >/dev/null 2>&1 200>&-
        exit_code=$?
    else
        "${STARTUP_SCRIPT}" >/dev/null 2>&1 200>&-
        exit_code=$?
    fi

    end_epoch=$(date +%s)
    duration_sec=$((end_epoch - start_epoch))

    rotate_file "${STARTUP_LOG}" "${STARTUP_LOG_MAX_BYTES}" "${ROTATE_KEEP}"
    printf '%s startup summary exit_code=%s duration_sec=%s output_capture=disabled reason=prevent_daemon_fd_inheritance\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "${exit_code}" "${duration_sec}" >> "${STARTUP_LOG}"
    rotate_file "${STARTUP_LOG}" "${STARTUP_LOG_MAX_BYTES}" "${ROTATE_KEEP}"

    STARTUP_OUTPUT_BYTES="0"
    STARTUP_OUTPUT_LINES="0"
    STARTUP_DURATION_SEC="${duration_sec}"
    STARTUP_TMP_OUT=""
    return "${exit_code}"
}
if command -v flock >/dev/null 2>&1; then
    exec 200>"${LOCK_FILE}"
    if ! flock -n 200; then
        log_msg "INFO skipped reason=lock_busy"
        vmsg "INFO another instance is running; exiting."
        exit 0
    fi
else
    log_msg "WARN flock_not_found overlap_protection=disabled"
fi

rotate_logs
load_state

last_file=""
last_mtime=""
no_files="false"

if [[ -d "${DATA_DIR}" ]]; then
    last_file=$(ls -1t "${DATA_DIR}" 2>/dev/null | head -n 1)
else
    log_msg "WARN data_dir_missing path=${DATA_DIR}"
    vmsg "WARN data dir missing: ${DATA_DIR}"
fi

if [[ -z "${last_file}" ]]; then
    no_files="true"
else
    if [[ -f "${DATA_DIR}/${last_file}" ]]; then
        last_mtime=$(stat -c %Y "${DATA_DIR}/${last_file}" 2>/dev/null || true)
    fi
    if [[ -z "${last_mtime}" ]]; then
        no_files="true"
    fi
fi

restart_needed="false"
reason=""
age_sec=""
now_epoch=$(date +%s)

if [[ "${no_files}" == "true" ]]; then
    restart_needed="true"
    reason="no_files"
else
    age_sec=$((now_epoch - last_mtime))
    if [[ "${age_sec}" -ge "${THRESHOLD_SEC}" ]]; then
        restart_needed="true"
        reason="stale"
    fi
fi

if [[ "${restart_needed}" != "true" ]]; then
    echo "0" > "${MAIL_COUNT_FILE}"
    CONSECUTIVE_RESTARTS=0
    LAST_REASON="healthy"
    LAST_EXIT_CODE="0"
    save_state
    log_msg "OK healthy last_file=${last_file:-NONE} age_sec=${age_sec:-NA} threshold_sec=${THRESHOLD_SEC}"
    vmsg "OK data present last_file=${last_file} age_sec=${age_sec} threshold_sec=${THRESHOLD_SEC}"
    exit 0
fi

elapsed_since_restart=$((now_epoch - LAST_RESTART_EPOCH))
if (( LAST_RESTART_EPOCH > 0 && elapsed_since_restart < COOLDOWN_SEC && CONSECUTIVE_RESTARTS >= MAX_CONSECUTIVE_RESTARTS )); then
    log_msg "WARN restart_suppressed reason=${reason} cooldown_remaining_sec=$((COOLDOWN_SEC - elapsed_since_restart)) consecutive_restarts=${CONSECUTIVE_RESTARTS} last_file=${last_file:-NONE} age_sec=${age_sec:-NA}"
    vmsg "WARN restart suppressed by cooldown."
    exit 0
fi

log_msg "INFO restart_triggered reason=${reason} last_file=${last_file:-NONE} age_sec=${age_sec:-NA} consecutive_before=${CONSECUTIVE_RESTARTS}"
vmsg "INFO restart triggered reason=${reason} last_file=${last_file:-NONE} age_sec=${age_sec:-NA}"

if [[ ! -x "${STARTUP_SCRIPT}" ]]; then
    LAST_RESTART_EPOCH="${now_epoch}"
    CONSECUTIVE_RESTARTS=$((CONSECUTIVE_RESTARTS + 1))
    LAST_REASON="${reason}"
    LAST_EXIT_CODE="127"
    save_state
    log_msg "ERROR startup_missing path=${STARTUP_SCRIPT} exit_code=127"
    vmsg "ERROR startup script missing or not executable: ${STARTUP_SCRIPT}"
    exit 0
fi

run_startup
startup_exit=$?
startup_tmp="${STARTUP_TMP_OUT:-}"
LAST_RESTART_EPOCH="${now_epoch}"
LAST_REASON="${reason}"
LAST_EXIT_CODE="${startup_exit}"

if [[ "${startup_exit}" -eq 0 ]]; then
    CONSECUTIVE_RESTARTS=$((CONSECUTIVE_RESTARTS + 1))
    log_msg "INFO startup_succeeded exit_code=0 duration_sec=${STARTUP_DURATION_SEC:-NA} output_bytes=${STARTUP_OUTPUT_BYTES:-NA} startup_log=${STARTUP_LOG}"
    vmsg "INFO startup script succeeded."
else
    CONSECUTIVE_RESTARTS=$((CONSECUTIVE_RESTARTS + 1))
    log_msg "ERROR startup_failed exit_code=${startup_exit} duration_sec=${STARTUP_DURATION_SEC:-NA} output_bytes=${STARTUP_OUTPUT_BYTES:-NA} startup_log=${STARTUP_LOG} output_capture=disabled"
    vmsg "ERROR startup script failed exit_code=${startup_exit}."
fi

save_state

if [[ "${no_files}" == "true" ]]; then
    count=0
    if [[ -f "${MAIL_COUNT_FILE}" ]]; then
        count=$(cat "${MAIL_COUNT_FILE}" 2>/dev/null || echo 0)
        [[ "${count}" =~ ^[0-9]+$ ]] || count=0
    fi
    if [[ "${count}" -lt 5 ]]; then
        if send_mail; then
            count=$((count + 1))
            echo "${count}" > "${MAIL_COUNT_FILE}"
            log_msg "INFO no_file_mail_sent count=${count}"
            vmsg "INFO no-file mail sent count=${count}"
        else
            log_msg "WARN no_file_mail_failed"
            vmsg "WARN no-file mail failed."
        fi
    else
        log_msg "INFO no_file_mail_suppressed count=${count}"
        vmsg "INFO no-file mail suppressed count=${count}"
    fi
else
    echo "0" > "${MAIL_COUNT_FILE}"
    vmsg "INFO mail count reset (files present)."
fi

exit 0
