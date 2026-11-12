#!/usr/bin/env bash
# Purpose: Display the latest CAEN voltage-monitor readings by channel.

# Display the latest CAEN VMON values as horizontal 0–6 kV bars.
#
# Channel/plane mapping:
#   Plane 1: UP=CH0, DOWN=CH4
#   Plane 2: UP=CH1, DOWN=CH5
#   Plane 3: UP=CH2, DOWN=CH6
#   Plane 4: UP=CH3, DOWN=CH7
#
# Usage:
#   ./caen_bars_monitor.sh
#   ./caen_bars_monitor.sh /home/rpcuser/logs/hv_2026-07-30.log
#   ./caen_bars_monitor.sh /home/rpcuser/logs/hv_2026-07-30.log 2
#
# Arguments:
#   1: optional legacy log path; its directory is used, but the newest log
#      is selected automatically on every refresh
#   2: refresh interval in seconds

set -Eeuo pipefail

LOG_DIR="${CAEN_LOG_DIR:-/home/rpcuser/logs}"
if [[ -n "${1:-}" ]]; then
    LOG_DIR="${CAEN_LOG_DIR:-$(dirname -- "$1")}"
fi
REFRESH_SECONDS="${2:-30}"

MIN_KV=0
MAX_KV=6
BAR_WIDTH=60

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

latest_log_file() {
    local candidate candidate_date best_date="" best_path=""
    local candidates=("${LOG_DIR}"/done/hv_????-??-??.log "${LOG_DIR}"/hv_????-??-??.log)

    for candidate in "${candidates[@]}"; do
        [[ -f "${candidate}" ]] || continue
        candidate_date="${candidate##*hv_}"
        candidate_date="${candidate_date%.log}"
        # The root copy wins over the archived copy while today's log is open.
        if [[ -z "${best_date}" || "${candidate_date}" > "${best_date}" || "${candidate_date}" == "${best_date}" ]]; then
            best_date="${candidate_date}"
            best_path="${candidate}"
        fi
    done

    printf '%s' "${best_path}"
}

[[ "${REFRESH_SECONDS}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
    die "Refresh interval must be a nonnegative number."

command -v awk >/dev/null 2>&1 || die "awk is required."
command -v tail >/dev/null 2>&1 || die "tail is required."
command -v tput >/dev/null 2>&1 || die "tput is required."

cleanup() {
    tput cnorm 2>/dev/null || true
}
trap cleanup EXIT INT TERM

blank_lines() {
    local count="$1"
    local i
    for ((i = 0; i < count; i++)); do
        printf '\n'
    done
}

render_bar() {
    local label="$1"
    local channel="$2"
    local volts="$3"

    awk \
        -v label="${label}" \
        -v channel="${channel}" \
        -v volts="${volts}" \
        -v min_kv="${MIN_KV}" \
        -v max_kv="${MAX_KV}" \
        -v width="${BAR_WIDTH}" '
        BEGIN {
            # Positive magnitude used to construct the bar.
            kv = volts / 1000.0

            clipped = kv
            if (clipped < min_kv) clipped = min_kv
            if (clipped > max_kv) clipped = max_kv

            fraction = (clipped - min_kv) / (max_kv - min_kv)
            filled = int(fraction * width + 0.5)

            bar = ""
            for (i = 0; i < filled; i++) bar = bar "#"
            for (i = filled; i < width; i++) bar = bar "."

            # Display channels 4–7 as negative, while preserving the bar.
            displayed_kv = kv
            if (channel >= 4)
                displayed_kv = -kv

            printf "  %-4s CH%-1d  [%s]  %+7.3f kV\n",
                   label, channel, bar, displayed_kv
        }
    '
}

while true; do
    LOG_FILE="$(latest_log_file)"

    tput civis
    clear

    printf 'CAEN HIGH-VOLTAGE MONITOR\n'
    printf 'Scale: %.0f kV [%*s] %.0f kV\n' \
        "${MIN_KV}" "${BAR_WIDTH}" "" "${MAX_KV}"
    if [[ -n "${LOG_FILE}" ]]; then
        printf 'Log: %s\n\n' "${LOG_FILE}"
    else
        printf 'Log: waiting for the newest hv_YYYY-MM-DD.log in %s or %s/done\n\n' \
            "${LOG_DIR}" "${LOG_DIR}"
    fi

    if [[ -z "${LOG_FILE}" || ! -r "${LOG_FILE}" ]]; then
        printf 'Waiting for a readable CAEN HV log file...\n'
        sleep "${REFRESH_SECONDS}"
        continue
    fi

    latest_line="$(awk 'NF {line=$0} END {print line}' "${LOG_FILE}")"

    if [[ -z "${latest_line}" ]]; then
        printf 'Waiting for the first log entry...\n'
        sleep "${REFRESH_SECONDS}"
        continue
    fi

    read -r -a fields <<<"${latest_line}"

    # One timestamp plus 8 parameters for each of the 8 channels:
    # 1 + (8 × 8) = 65 fields.
    if (( ${#fields[@]} < 65 )); then
        printf 'Malformed latest entry: expected at least 65 fields, found %d.\n' \
            "${#fields[@]}"
        printf 'Entry: %s\n' "${latest_line}"
        sleep "${REFRESH_SECONDS}"
        continue
    fi

    timestamp="${fields[0]}"

    # VMON is the second value in each channel's eight-value block.
    vmon=(
        "${fields[2]}"
        "${fields[10]}"
        "${fields[18]}"
        "${fields[26]}"
        "${fields[34]}"
        "${fields[42]}"
        "${fields[50]}"
        "${fields[58]}"
    )

    printf 'Latest sample: %s\n\n' "${timestamp}"

    printf 'PLANE 1\n'
    render_bar "UP"   0 "${vmon[0]}"
    render_bar "DOWN" 4 "${vmon[4]}"

    blank_lines 2

    printf 'PLANE 2\n'
    render_bar "UP"   1 "${vmon[1]}"
    render_bar "DOWN" 5 "${vmon[5]}"

    blank_lines 2

    printf 'PLANE 3\n'
    render_bar "UP"   2 "${vmon[2]}"
    render_bar "DOWN" 6 "${vmon[6]}"

    blank_lines 4

    printf 'PLANE 4\n'
    render_bar "UP"   3 "${vmon[3]}"
    render_bar "DOWN" 7 "${vmon[7]}"

    printf '\n\nPress Ctrl+C to exit.\n'
    sleep "${REFRESH_SECONDS}"
done
