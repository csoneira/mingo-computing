#!/usr/bin/env bash
# Purpose: Run simultaneous or plane-by-plane CAEN HV scans with clean DAQ.

set -Eeuo pipefail

PROGRAM_NAME="$(basename "$0")"

START_HV="5.2"
END_HV="5.5"
STEP_HV="0.05"
TIME_PER_VOLTAGE_MIN="60"
POINTS=""
FINISH_AT=""
SAFE_HV="5.3"
NOMINAL_HV=""
SETTLE_SECONDS="300"
CAEN_ISET="1"

ASSUME_YES=0
DRY_RUN=0
TIME_WAS_SET=0
SCAN_MODE="all-channels"

CAEN_DIR="${PLATEAU_CAEN_DIR:-/home/rpcuser/CAEN}"
CAEN_CONTROLLER="${PLATEAU_CAEN_CONTROLLER:-${CAEN_DIR}/monitor.py}"
CAEN_CHANNELS="${PLATEAU_CAEN_CHANNELS:-0 1 2 3 4 5 6 7}"
ALL_CAEN_CHANNELS="0 1 2 3 4 5 6 7"

DAQ_DIR="${PLATEAU_DAQ_DIR:-/home/rpcuser/trbsoft/userscripts/trb}"
DAQ_START_SCRIPT="${PLATEAU_DAQ_START_SCRIPT:-${DAQ_DIR}/startRun.sh}"
DAQ_START_LOG="${PLATEAU_DAQ_START_LOG:-/tmp/plateau_CAEN_CLI_daq_start.log}"
LOCK_FILE="${PLATEAU_LOCK_FILE:-/tmp/plateau_CAEN_CLI.lock}"
DAQ_STOP_TIMEOUT_SECONDS="${PLATEAU_DAQ_STOP_TIMEOUT_SECONDS:-30}"
DAQ_START_TIMEOUT_SECONDS="${PLATEAU_DAQ_START_TIMEOUT_SECONDS:-30}"
FILE_CLOSE_GRACE_SECONDS="${PLATEAU_FILE_CLOSE_GRACE_SECONDS:-2}"

HARDWARE_TOUCHED=0
COMPLETED=0

usage() {
    cat <<EOF
Usage:
  ${PROGRAM_NAME} [options]

Run a high-voltage plateau scan using the CAEN power supply. Each voltage
interval is placed in a fresh DAQ run:

  1. Stop DABC cleanly with SIGINT.
  2. Apply the voltage to all configured channels or only one detector plane.
  3. Wait for HV settling.
  4. Start DABC.
  5. Acquire for the requested time.
  6. Stop DABC and continue to the next voltage.

Voltage arguments are specified in kV. They are converted internally to volts
before being passed to monitor.py.

Options:
  -s, --start KV          Starting HV in kV
                           (default: ${START_HV})
  -e, --end KV            Ending HV in kV, included when reached
                           (default: ${END_HV})
  -i, --step KV           Positive HV increment in kV
                           (default: ${STEP_HV})
  -p, --points N          Number of evenly spaced points, endpoints included
  --finish-at DATETIME    Allocate dwell time to finish by a UTC date/time
                           (example: '2026-10-19 06:00:00 UTC')
  -t, --time MIN          Measurement time per voltage in minutes
                           (default: ${TIME_PER_VOLTAGE_MIN})
  -f, --safe KV           Safe HV restored after the scan
                           (default: ${SAFE_HV})
  --nominal KV            Required nominal HV for --plane-by-plane mode
  --plane-by-plane        Scan P1..P4 in sequence, changing only each plane's
                           pair (P1: 0,4; P2: 1,5; P3: 2,6; P4: 3,7)
  --all-channels          Apply each point to all configured channels
  -w, --settle SEC        Settling time after scan channels are updated
                           (default: ${SETTLE_SECONDS})
  -c, --current VALUE     CAEN ISET applied to every channel
                           (default: ${CAEN_ISET})
  -y, --yes               Skip the interactive confirmation
  -n, --dry-run           Print actions without controlling HV, DAQ, or sleeping
  -h, --help              Show this help and exit

Environment overrides:
  PLATEAU_CAEN_DIR
  PLATEAU_CAEN_CONTROLLER
  PLATEAU_CAEN_CHANNELS
  PLATEAU_DAQ_DIR
  PLATEAU_DAQ_START_SCRIPT
  PLATEAU_DAQ_START_LOG
  PLATEAU_LOCK_FILE
  PLATEAU_DAQ_STOP_TIMEOUT_SECONDS
  PLATEAU_DAQ_START_TIMEOUT_SECONDS
  PLATEAU_FILE_CLOSE_GRACE_SECONDS

Examples:
  ${PROGRAM_NAME} -s 5.1 -e 5.8 -i 0.06 -t 120 -f 5.6
  ${PROGRAM_NAME} --start 5.1 --end 5.8 --step 0.06 --time 120 --safe 5.6
  ${PROGRAM_NAME} --start 5.4 --end 5.8 --points 5 --finish-at '2026-10-19 06:00:00 UTC' --safe 5.5
  ${PROGRAM_NAME} --start 5.2 --end 5.8 --points 10 --time 1440 --nominal 5.5 --plane-by-plane
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

validate_channel_list() {
    local channel
    local -a channels=()

    read -r -a channels <<<"${CAEN_CHANNELS}"
    (( ${#channels[@]} > 0 )) ||
        die "PLATEAU_CAEN_CHANNELS contains no channels."

    for channel in "${channels[@]}"; do
        [[ "${channel}" =~ ^[0-7]$ ]] ||
            die "Invalid CAEN channel '${channel}'. Valid channels are 0 to 7."
    done
}

while (( $# > 0 )); do
    case "$1" in
        -s|--start)
            require_value "$1" "$#"
            START_HV="$2"
            shift 2
            ;;
        -e|--end)
            require_value "$1" "$#"
            END_HV="$2"
            shift 2
            ;;
        -i|--step)
            require_value "$1" "$#"
            STEP_HV="$2"
            shift 2
            ;;
        -p|--points)
            require_value "$1" "$#"
            POINTS="$2"
            shift 2
            ;;
        --finish-at)
            require_value "$1" "$#"
            FINISH_AT="$2"
            shift 2
            ;;
        -t|--time)
            require_value "$1" "$#"
            TIME_PER_VOLTAGE_MIN="$2"
            TIME_WAS_SET=1
            shift 2
            ;;
        -f|--safe)
            require_value "$1" "$#"
            SAFE_HV="$2"
            shift 2
            ;;
        -w|--settle)
            require_value "$1" "$#"
            SETTLE_SECONDS="$2"
            shift 2
            ;;
        -c|--current)
            require_value "$1" "$#"
            CAEN_ISET="$2"
            shift 2
            ;;
        --nominal)
            require_value "$1" "$#"
            NOMINAL_HV="$2"
            shift 2
            ;;
        --plane-by-plane)
            SCAN_MODE="plane-by-plane"
            shift
            ;;
        --all-channels)
            SCAN_MODE="all-channels"
            shift
            ;;
        -y|--yes)
            ASSUME_YES=1
            shift
            ;;
        -n|--dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            (( $# == 0 )) || die "Unexpected positional arguments: $*"
            ;;
        -*)
            die "Unknown option: $1. Use --help."
            ;;
        *)
            die "Unexpected positional argument: $1. Use --help."
            ;;
    esac
done

is_positive_decimal "${START_HV}" ||
    die "Starting HV must be a positive number."
is_positive_decimal "${END_HV}" ||
    die "Ending HV must be a positive number."
is_positive_decimal "${STEP_HV}" ||
    die "HV step must be a positive number."
is_positive_decimal "${SAFE_HV}" ||
    die "Safe HV must be a positive number."
is_positive_decimal "${CAEN_ISET}" ||
    die "CAEN ISET must be a positive number."

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

if [[ -n "${POINTS}" ]]; then
    is_nonnegative_integer "${POINTS}" && (( POINTS >= 1 )) ||
        die "Point count must be a positive integer."
fi

if [[ -n "${FINISH_AT}" && "${TIME_WAS_SET}" == 1 ]]; then
    die "Use either --finish-at or --time, not both."
fi

awk -v start="${START_HV}" -v end="${END_HV}" \
    'BEGIN { exit !(end >= start) }' ||
    die "Ending HV must be greater than or equal to starting HV."

validate_channel_list

if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    [[ -n "${NOMINAL_HV}" ]] ||
        die "--plane-by-plane requires --nominal KV so the other planes remain at their nominal value."
    is_positive_decimal "${NOMINAL_HV}" ||
        die "Nominal HV must be a positive number."
fi

if [[ -n "${FINISH_AT}" ]]; then
    FINISH_EPOCH="$(date -d "${FINISH_AT}" +%s 2>/dev/null)" ||
        die "Cannot parse --finish-at. Use a UTC time such as '2026-10-19 06:00:00 UTC'."
    (( FINISH_EPOCH > $(date +%s) )) ||
        die "--finish-at must be in the future."
fi

for command in awk date flock pgrep seq sleep tail; do
    command -v "${command}" >/dev/null 2>&1 ||
        die "Required command is unavailable: ${command}"
done

if (( DRY_RUN == 0 )); then
    [[ -d "${CAEN_DIR}" ]] ||
        die "CAEN directory does not exist: ${CAEN_DIR}"
    [[ -x "${CAEN_CONTROLLER}" ]] ||
        die "CAEN controller is not executable: ${CAEN_CONTROLLER}"
    [[ -d "${DAQ_DIR}" ]] ||
        die "DAQ directory does not exist: ${DAQ_DIR}"
    [[ -r "${DAQ_START_SCRIPT}" ]] ||
        die "DAQ start script is not readable: ${DAQ_START_SCRIPT}"
fi

mkdir -p "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
flock -n 9 ||
    die "Another CAEN plateau scan is already active (lock: ${LOCK_FILE})."

if [[ -n "${POINTS}" ]]; then
    if (( POINTS == 1 )); then
        awk -v start="${START_HV}" -v end="${END_HV}" 'BEGIN { exit !(start == end) }' ||
            die "A one-point scan requires identical start and end voltages."
        VOLTAGES=("${START_HV}")
    else
        mapfile -t VOLTAGES < <(
            awk -v start="${START_HV}" -v end="${END_HV}" -v points="${POINTS}" \
                'BEGIN { for (i = 0; i < points; i++) printf "%.6f\n", start + i * (end - start) / (points - 1) }'
        )
    fi
else
    mapfile -t VOLTAGES < <(seq "${START_HV}" "${STEP_HV}" "${END_HV}")
fi
(( ${#VOLTAGES[@]} > 0 )) ||
    die "The requested voltage sequence is empty."

declare -a PLANE_CHANNELS=("0 4" "1 5" "2 6" "3 7")
SCAN_GROUPS=1
if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    SCAN_GROUPS=4
fi
TOTAL_VOLTAGE_POINTS=$((${#VOLTAGES[@]} * SCAN_GROUPS))

if [[ -n "${FINISH_AT}" ]]; then
    remaining_seconds=$((FINISH_EPOCH - $(date +%s)))
    # Reserve DAQ stop/start limits, settling intervals, and a ten-minute
    # margin for CAEN command and system timing variation.
    fixed_overhead=$((TOTAL_VOLTAGE_POINTS * SETTLE_SECONDS + \
        TOTAL_VOLTAGE_POINTS * (DAQ_START_TIMEOUT_SECONDS + DAQ_STOP_TIMEOUT_SECONDS + FILE_CLOSE_GRACE_SECONDS) + \
        DAQ_STOP_TIMEOUT_SECONDS + DAQ_START_TIMEOUT_SECONDS + 600))
    available_measurement_seconds=$((remaining_seconds - fixed_overhead))
    (( available_measurement_seconds > 0 )) ||
        die "There is not enough time before --finish-at for settling, DAQ transitions, and the safety margin."
    TIME_PER_VOLTAGE_SECONDS=$((available_measurement_seconds / TOTAL_VOLTAGE_POINTS))
else
    TIME_PER_VOLTAGE_SECONDS=$((TIME_PER_VOLTAGE_MIN * 60))
fi
MEASUREMENT_SECONDS=$((TOTAL_VOLTAGE_POINTS * TIME_PER_VOLTAGE_SECONDS))
EXPECTED_SECONDS=$((MEASUREMENT_SECONDS + TOTAL_VOLTAGE_POINTS * SETTLE_SECONDS + \
    TOTAL_VOLTAGE_POINTS * (DAQ_START_TIMEOUT_SECONDS + DAQ_STOP_TIMEOUT_SECONDS + FILE_CLOSE_GRACE_SECONDS) + \
    DAQ_STOP_TIMEOUT_SECONDS + DAQ_START_TIMEOUT_SECONDS))

MEASUREMENT_HOURS="$(
    awk -v seconds="${MEASUREMENT_SECONDS}" \
        'BEGIN { printf "%.2f", seconds / 3600 }'
)"
EXPECTED_HOURS="$(
    awk -v seconds="${EXPECTED_SECONDS}" \
        'BEGIN { printf "%.2f", seconds / 3600 }'
)"

printf 'Plateau measurement time: %s hours\n' "${MEASUREMENT_HOURS}"
printf 'Expected wall time including HV settling: %s hours\n' "${EXPECTED_HOURS}"
printf 'Scan mode: %s\n' "${SCAN_MODE}"
printf 'Voltage points per scan group (%d): %s kV\n' "${#VOLTAGES[@]}" "${VOLTAGES[*]}"
printf 'Total DAQ measurement points: %d\n' "${TOTAL_VOLTAGE_POINTS}"
printf 'Dwell per point: %d seconds (%.2f hours)\n' "${TIME_PER_VOLTAGE_SECONDS}" \
    "$(awk -v seconds="${TIME_PER_VOLTAGE_SECONDS}" 'BEGIN { printf "%.2f", seconds / 3600 }')"
if [[ -n "${FINISH_AT}" ]]; then
    printf 'Requested finish: %s\n' "${FINISH_AT}"
fi
if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    printf 'Nominal voltage for non-scanned planes and final state: %s kV\n' "${NOMINAL_HV}"
else
    printf 'Safe final voltage: %s kV\n' "${SAFE_HV}"
fi
printf 'CAEN controller: %s\n' "${CAEN_CONTROLLER}"
printf 'CAEN channels: %s\n' "${CAEN_CHANNELS}"
printf 'CAEN ISET per channel: %s\n' "${CAEN_ISET}"
printf 'DAQ start script: %s\n' "${DAQ_START_SCRIPT}"
printf 'DAQ transition: clean SIGINT stop; no SIGKILL fallback\n'

if (( ASSUME_YES == 0 )); then
    read -r -p "Do you want to continue (Y/N)? " answer
    case "${answer^^}" in
        Y|YES)
            ;;
        *)
            printf 'Plateau scan cancelled.\n'
            exit 0
            ;;
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
        printf 'ERROR: DABC did not stop cleanly within %s seconds (PID(s): %s).\n' \
            "${DAQ_STOP_TIMEOUT_SECONDS}" "${pids[*]}" >&2
        printf 'ERROR: Refusing SIGKILL and refusing to change HV while DAQ is active.\n' \
            >&2
        return 1
    fi

    sleep_for "${FILE_CLOSE_GRACE_SECONDS}" "file-close grace period"
    log "DAQ stopped cleanly; acquisition file boundary is closed."
}

kv_to_volts() {
    local voltage_kv="$1"

    awk -v voltage_kv="${voltage_kv}" \
        'BEGIN { printf "%.3f", voltage_kv * 1000.0 }'
}

set_hv_all_channels() {
    set_hv_channels "$1" "${CAEN_CHANNELS}"
}

set_hv_channels() {
    local voltage_kv="$1"
    local channel_list="$2"
    local voltage_v
    local channel
    local -a channels=()

    voltage_v="$(kv_to_volts "${voltage_kv}")"
    read -r -a channels <<<"${channel_list}"

    log "Applying ${voltage_kv} kV (${voltage_v} V) to CAEN channels: ${channels[*]}."

    for channel in "${channels[@]}"; do
        if (( DRY_RUN == 1 )); then
            log "[DRY-RUN] Would run: ${CAEN_CONTROLLER} -CH ${channel} -I ${CAEN_ISET} -V ${voltage_v} -ON"
            continue
        fi

        if ! (
            cd "${CAEN_DIR}"
            "${CAEN_CONTROLLER}" \
                -CH "${channel}" \
                -I "${CAEN_ISET}" \
                -V "${voltage_v}" \
                -ON
        ); then
            printf 'ERROR: Failed to configure CAEN channel %s at %s kV (%s V).\n' \
                "${channel}" "${voltage_kv}" "${voltage_v}" >&2
            return 1
        fi

        log "CAEN channel ${channel}: VSET=${voltage_v} V, ISET=${CAEN_ISET}, ON."
    done

    log "CAEN channels ${channels[*]} are set to ${voltage_kv} kV."
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
        nohup /bin/bash "${DAQ_START_SCRIPT}" \
            >>"${DAQ_START_LOG}" 2>&1 </dev/null 9>&- &
    )

    deadline=$((SECONDS + DAQ_START_TIMEOUT_SECONDS))
    while (( SECONDS < deadline )); do
        mapfile -t pids < <(daq_pids)
        (( ${#pids[@]} > 0 )) && break
        sleep 1
    done

    mapfile -t pids < <(daq_pids)

    if (( ${#pids[@]} == 0 )); then
        printf 'ERROR: DAQ did not start within %s seconds. Startup output (%s):\n' \
            "${DAQ_START_TIMEOUT_SECONDS}" "${DAQ_START_LOG}" >&2
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
            if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
                recovery_result=0
                set_hv_channels "${RECOVERY_HV}" "${ALL_CAEN_CHANNELS}" || recovery_result=$?
            else
                recovery_result=0
                set_hv_all_channels "${RECOVERY_HV}" || recovery_result=$?
            fi
            if (( recovery_result == 0 )); then
                start_daq ||
                    log "Safe HV was restored, but DAQ could not be restarted."
            else
                log "Safe recovery failed while restoring CAEN channel voltages."
            fi
        else
            log "Safe recovery could not stop DAQ; HV was left unchanged."
        fi
    fi

    exit "${original_status}"
}

trap 'exit 130' INT TERM
trap 'restore_after_failure $?' EXIT

HARDWARE_TOUCHED=1
RECOVERY_HV="${SAFE_HV}"
if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    RECOVERY_HV="${NOMINAL_HV}"
fi

stop_daq_cleanly ||
    die "Cannot establish a clean initial DAQ boundary."

if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    set_hv_channels "${NOMINAL_HV}" "${ALL_CAEN_CHANNELS}" ||
        die "Failed to establish nominal HV on all CAEN channels."

    for plane_index in 0 1 2 3; do
        plane_number=$((plane_index + 1))
        plane_channels="${PLANE_CHANNELS[plane_index]}"
        log "Starting plane ${plane_number}; scanning channels ${plane_channels} while other planes stay at ${NOMINAL_HV} kV."
        for voltage in "${VOLTAGES[@]}"; do
            printf '%s\n' '***************************'
            log "Starting plane ${plane_number} at ${voltage} kV."
            set_hv_channels "${voltage}" "${plane_channels}" ||
                die "Failed to set plane ${plane_number} channels to ${voltage} kV."
            sleep_for "${SETTLE_SECONDS}" "HV settling"
            start_daq || die "DAQ failed to start at plane ${plane_number}, ${voltage} kV."
            sleep_for "${TIME_PER_VOLTAGE_SECONDS}" \
                "plane ${plane_number} measurement at ${voltage} kV"
            stop_daq_cleanly ||
                die "DAQ failed to stop cleanly after plane ${plane_number}, ${voltage} kV."
            log "Completed plane ${plane_number} point at ${voltage} kV."
        done
        set_hv_channels "${NOMINAL_HV}" "${plane_channels}" ||
            die "Failed to restore plane ${plane_number} to nominal HV."
    done
    FINAL_HV="${NOMINAL_HV}"
else
    for voltage in "${VOLTAGES[@]}"; do
        printf '%s\n' '***************************'
        log "Starting simultaneous all-plane point at ${voltage} kV."
        set_hv_all_channels "${voltage}" ||
            die "Failed to set all CAEN channels to ${voltage} kV."
        sleep_for "${SETTLE_SECONDS}" "HV settling"
        start_daq || die "DAQ failed to start at ${voltage} kV."
        sleep_for "${TIME_PER_VOLTAGE_SECONDS}" "measurement at ${voltage} kV"
        stop_daq_cleanly ||
            die "DAQ failed to stop cleanly after measurement at ${voltage} kV."
        log "Completed simultaneous all-plane point at ${voltage} kV."
    done
    FINAL_HV="${SAFE_HV}"
fi

if [[ "${SCAN_MODE}" == "plane-by-plane" ]]; then
    set_hv_channels "${FINAL_HV}" "${ALL_CAEN_CHANNELS}" ||
        die "Failed to restore all CAEN channels to the nominal HV."
else
    set_hv_all_channels "${FINAL_HV}" ||
        die "Failed to restore all configured CAEN channels to the final HV."
fi

start_daq ||
    die "DAQ failed to restart at the safe HV."

COMPLETED=1

log "Plateau measurement ended; final HV ${FINAL_HV} kV restored on all configured CAEN channels and DAQ running."
