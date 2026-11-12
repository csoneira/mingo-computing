#!/usr/bin/env bash
# Purpose: Run a stepped high-voltage plateau scan with clean DAQ file boundaries.

set -Eeuo pipefail

PROGRAM_NAME="$(basename "$0")"
START_HV="5.2"
END_HV="5.5"
STEP_HV="0.05"
TIME_PER_VOLTAGE_MIN="60"
SAFE_HV="5.3"
SETTLE_SECONDS="300"
ASSUME_YES=0
DRY_RUN=0

HV_DIR="${PLATEAU_HV_DIR:-/home/rpcuser/bin/HV}"
HV_BINARY="${PLATEAU_HV_BINARY:-${HV_DIR}/hv}"
DAQ_DIR="${PLATEAU_DAQ_DIR:-/home/rpcuser/trbsoft/userscripts/trb}"
DAQ_START_SCRIPT="${PLATEAU_DAQ_START_SCRIPT:-${DAQ_DIR}/startRun.sh}"
DAQ_START_LOG="${PLATEAU_DAQ_START_LOG:-/tmp/plateau_CLI_daq_start.log}"
LOCK_FILE="${PLATEAU_LOCK_FILE:-/tmp/plateau_CLI.lock}"
DAQ_STOP_TIMEOUT_SECONDS="${PLATEAU_DAQ_STOP_TIMEOUT_SECONDS:-30}"
DAQ_START_TIMEOUT_SECONDS="${PLATEAU_DAQ_START_TIMEOUT_SECONDS:-30}"
FILE_CLOSE_GRACE_SECONDS="${PLATEAU_FILE_CLOSE_GRACE_SECONDS:-2}"

HARDWARE_TOUCHED=0
COMPLETED=0

usage() {
    cat <<EOF
Usage:
  ${PROGRAM_NAME} [options]

Run a high-voltage plateau scan. Each voltage interval is placed in a fresh
DAQ run: DABC is stopped cleanly with SIGINT, the HV is changed, settling is
allowed, and DABC is started again.

Options:
  -s, --start KV          Starting HV in kV (default: ${START_HV})
  -e, --end KV            Ending HV in kV, included when reached (default: ${END_HV})
  -i, --step KV           Positive HV increment in kV (default: ${STEP_HV})
  -t, --time MIN          Measurement time per voltage in minutes (default: ${TIME_PER_VOLTAGE_MIN})
  -f, --safe KV           Safe HV restored after the scan (default: ${SAFE_HV})
  -w, --settle SEC        Settling time after each HV change (default: ${SETTLE_SECONDS})
  -y, --yes               Skip the interactive confirmation
  -n, --dry-run           Print actions without controlling HV, DAQ, or sleeping
  -h, --help              Show this help and exit

Environment overrides:
  PLATEAU_HV_DIR, PLATEAU_HV_BINARY, PLATEAU_DAQ_DIR,
  PLATEAU_DAQ_START_SCRIPT, PLATEAU_DAQ_START_LOG, PLATEAU_LOCK_FILE,
  PLATEAU_DAQ_STOP_TIMEOUT_SECONDS, PLATEAU_DAQ_START_TIMEOUT_SECONDS,
  PLATEAU_FILE_CLOSE_GRACE_SECONDS

Examples:
  ${PROGRAM_NAME} -s 5.1 -e 5.8 -i 0.06 -t 120 -f 5.6
  ${PROGRAM_NAME} --start 5.1 --end 5.8 --step 0.06 --time 120 --safe 5.6
  ${PROGRAM_NAME} -s 5.1 -e 5.22 -i 0.06 -t 1 -f 5.3 -w 0 --dry-run --yes
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_value() {
    (( "$2" >= 2 )) || die "Option $1 requires a value. Use --help."
}

is_positive_decimal() {
    [[ "$1" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]] &&
        awk -v value="$1" 'BEGIN { exit !(value > 0) }'
}

is_nonnegative_integer() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

while (( $# > 0 )); do
    case "$1" in
        -s|--start) require_value "$1" "$#"; START_HV="$2"; shift 2 ;;
        -e|--end) require_value "$1" "$#"; END_HV="$2"; shift 2 ;;
        -i|--step) require_value "$1" "$#"; STEP_HV="$2"; shift 2 ;;
        -t|--time) require_value "$1" "$#"; TIME_PER_VOLTAGE_MIN="$2"; shift 2 ;;
        -f|--safe) require_value "$1" "$#"; SAFE_HV="$2"; shift 2 ;;
        -w|--settle) require_value "$1" "$#"; SETTLE_SECONDS="$2"; shift 2 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        --)
            shift
            (( $# == 0 )) || die "Unexpected positional arguments: $*"
            ;;
        -*) die "Unknown option: $1. Use --help." ;;
        *) die "Unexpected positional argument: $1. Use --help." ;;
    esac
done

is_positive_decimal "${START_HV}" || die "Starting HV must be a positive number."
is_positive_decimal "${END_HV}" || die "Ending HV must be a positive number."
is_positive_decimal "${STEP_HV}" || die "HV step must be a positive number."
is_positive_decimal "${SAFE_HV}" || die "Safe HV must be a positive number."
is_nonnegative_integer "${TIME_PER_VOLTAGE_MIN}" ||
    die "Measurement time must be a nonnegative integer number of minutes."
is_nonnegative_integer "${SETTLE_SECONDS}" ||
    die "Settling time must be a nonnegative integer number of seconds."
is_nonnegative_integer "${DAQ_STOP_TIMEOUT_SECONDS}" ||
    die "PLATEAU_DAQ_STOP_TIMEOUT_SECONDS must be a nonnegative integer."
is_nonnegative_integer "${DAQ_START_TIMEOUT_SECONDS}" ||
    die "PLATEAU_DAQ_START_TIMEOUT_SECONDS must be a nonnegative integer."
is_nonnegative_integer "${FILE_CLOSE_GRACE_SECONDS}" ||
    die "PLATEAU_FILE_CLOSE_GRACE_SECONDS must be a nonnegative integer."

awk -v start="${START_HV}" -v end="${END_HV}"     'BEGIN { exit !(end >= start) }' ||
    die "Ending HV must be greater than or equal to starting HV."

for command in awk date flock pgrep seq sleep; do
    command -v "${command}" >/dev/null 2>&1 ||
        die "Required command is unavailable: ${command}"
done

if (( DRY_RUN == 0 )); then
    [[ -d "${HV_DIR}" ]] || die "HV directory does not exist: ${HV_DIR}"
    [[ -x "${HV_BINARY}" ]] || die "HV binary is not executable: ${HV_BINARY}"
    [[ -d "${DAQ_DIR}" ]] || die "DAQ directory does not exist: ${DAQ_DIR}"
    [[ -r "${DAQ_START_SCRIPT}" ]] ||
        die "DAQ start script is not readable: ${DAQ_START_SCRIPT}"
fi

mkdir -p "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
flock -n 9 || die "Another plateau scan is already active (lock: ${LOCK_FILE})."

mapfile -t VOLTAGES < <(seq "${START_HV}" "${STEP_HV}" "${END_HV}")
(( ${#VOLTAGES[@]} > 0 )) || die "The requested voltage sequence is empty."

TIME_PER_VOLTAGE_SECONDS=$((TIME_PER_VOLTAGE_MIN * 60))
MEASUREMENT_SECONDS=$((${#VOLTAGES[@]} * TIME_PER_VOLTAGE_SECONDS))
EXPECTED_SECONDS=$((MEASUREMENT_SECONDS + ${#VOLTAGES[@]} * SETTLE_SECONDS))
MEASUREMENT_HOURS="$(awk -v seconds="${MEASUREMENT_SECONDS}" 'BEGIN { printf "%.2f", seconds / 3600 }')"
EXPECTED_HOURS="$(awk -v seconds="${EXPECTED_SECONDS}" 'BEGIN { printf "%.2f", seconds / 3600 }')"

printf 'Plateau measurement time: %s hours\n' "${MEASUREMENT_HOURS}"
printf 'Expected wall time including HV settling: %s hours\n' "${EXPECTED_HOURS}"
printf 'Voltage points (%d): %s kV\n' "${#VOLTAGES[@]}" "${VOLTAGES[*]}"
printf 'Safe final voltage: %s kV\n' "${SAFE_HV}"
printf 'HV controller: %s\n' "${HV_BINARY}"
printf 'DAQ start script: %s\n' "${DAQ_START_SCRIPT}"
printf 'DAQ transition: clean SIGINT stop; no SIGKILL fallback\n'

if (( ASSUME_YES == 0 )); then
    read -r -p "Do you want to continue (Y/N)? " answer
    case "${answer^^}" in
        Y|YES) ;;
        *) printf 'Plateau scan cancelled.\n'; exit 0 ;;
    esac
fi

sleep_for() {
    local seconds="$1"
    local reason="$2"
    if (( DRY_RUN == 1 )); then
        log "[DRY-RUN] Would sleep ${seconds} seconds (${reason})."
    elif (( seconds > 0 )); then
        sleep "${seconds}"
    fi
}

daq_pids() {
    pgrep -x dabc_exe 2>/dev/null || true
}

stop_daq_cleanly() {
    local -a pids=()
    local deadline
    mapfile -t pids < <(daq_pids)
    if (( ${#pids[@]} == 0 )); then
        log "DAQ is already stopped."
        return 0
    fi
    if (( DRY_RUN == 1 )); then
        log "[DRY-RUN] Would send SIGINT to DABC PID(s): ${pids[*]}"
        return 0
    fi

    log "Requesting clean DABC shutdown with SIGINT (PID(s): ${pids[*]})."
    kill -INT "${pids[@]}"
    deadline=$((SECONDS + DAQ_STOP_TIMEOUT_SECONDS))
    while (( SECONDS < deadline )); do
        mapfile -t pids < <(daq_pids)
        (( ${#pids[@]} == 0 )) && break
        sleep 1
    done
    mapfile -t pids < <(daq_pids)
    if (( ${#pids[@]} > 0 )); then
        printf 'ERROR: DABC did not stop cleanly within %s seconds (PID(s): %s).\n'             "${DAQ_STOP_TIMEOUT_SECONDS}" "${pids[*]}" >&2
        printf 'ERROR: Refusing SIGKILL and refusing to change HV while DAQ is active.\n' >&2
        return 1
    fi
    sleep_for "${FILE_CLOSE_GRACE_SECONDS}" "file-close grace period"
    log "DAQ stopped cleanly; acquisition file boundary is closed."
}

set_hv() {
    local voltage="$1"
    if (( DRY_RUN == 1 )); then
        log "[DRY-RUN] Would set HV to ${voltage} kV with ${HV_BINARY}."
    else
        (cd "${HV_DIR}" && "${HV_BINARY}" -b 0 -I 1 -V "${voltage}" -on)
        log "HV set to ${voltage} kV."
    fi
}

start_daq() {
    local deadline
    local -a pids=()
    mapfile -t pids < <(daq_pids)
    if (( ${#pids[@]} > 0 )); then
        log "DAQ is already running (PID(s): ${pids[*]})."
        return 0
    fi
    if (( DRY_RUN == 1 )); then
        log "[DRY-RUN] Would start DAQ with ${DAQ_START_SCRIPT}."
        return 0
    fi

    : >"${DAQ_START_LOG}"
    (
        cd "${DAQ_DIR}"
        nohup /bin/bash "${DAQ_START_SCRIPT}" >>"${DAQ_START_LOG}" 2>&1 </dev/null &
    )
    deadline=$((SECONDS + DAQ_START_TIMEOUT_SECONDS))
    while (( SECONDS < deadline )); do
        mapfile -t pids < <(daq_pids)
        (( ${#pids[@]} > 0 )) && break
        sleep 1
    done
    mapfile -t pids < <(daq_pids)
    if (( ${#pids[@]} == 0 )); then
        printf 'ERROR: DAQ did not start within %s seconds. Startup output (%s):\n'             "${DAQ_START_TIMEOUT_SECONDS}" "${DAQ_START_LOG}" >&2
        tail -n 40 "${DAQ_START_LOG}" >&2 || true
        return 1
    fi
    log "DAQ started (PID(s): ${pids[*]})."
}

restore_after_failure() {
    local original_status="$1"
    trap - EXIT INT TERM
    set +e
    if (( HARDWARE_TOUCHED == 1 && COMPLETED == 0 && DRY_RUN == 0 )); then
        log "Interrupted or failed; attempting safe recovery."
        if stop_daq_cleanly; then
            set_hv "${SAFE_HV}"
            start_daq
        else
            log "Safe recovery could not stop DAQ; HV was left unchanged."
        fi
    fi
    exit "${original_status}"
}

trap 'exit 130' INT TERM
trap 'restore_after_failure $?' EXIT

HARDWARE_TOUCHED=1
stop_daq_cleanly || die "Cannot establish a clean initial DAQ boundary."

for voltage in "${VOLTAGES[@]}"; do
    printf '%s\n' '***************************'
    log "Starting plateau point at ${voltage} kV."
    set_hv "${voltage}"
    sleep_for "${SETTLE_SECONDS}" "HV settling"
    start_daq || die "DAQ failed to start at ${voltage} kV."
    sleep_for "${TIME_PER_VOLTAGE_SECONDS}" "measurement at ${voltage} kV"
    stop_daq_cleanly ||
        die "DAQ failed to stop cleanly after measurement at ${voltage} kV."
    log "Completed plateau point at ${voltage} kV."
done

set_hv "${SAFE_HV}"
start_daq || die "DAQ failed to restart at the safe HV."
COMPLETED=1
log "Plateau measurement ended; safe HV ${SAFE_HV} kV restored and DAQ running."
