#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ENGINE="$SCRIPT_DIR/watch_file_flow_engine.sh"

usage() {
    cat <<EOF_USAGE
Usage:
    $(basename "$0")                         Table mode, all stations (default)
    $(basename "$0") NUMBER                  Table mode, one station
    $(basename "$0") table [NUMBER]          Table mode explicitly
    $(basename "$0") timeline [NUMBER]       Timeline mode
    $(basename "$0") --interactive [MODE] [NUMBER]  Toggle modes with T; quit with Q
    $(basename "$0") --test [table|timeline] [NUMBER]

Examples:
    $(basename "$0")
    $(basename "$0") 2
    $(basename "$0") timeline
    $(basename "$0") timeline 2
    $(basename "$0") --test
    $(basename "$0") --test timeline

The ~/.bashrc wrapper therefore supports:
    watch_file_flow
    watch_file_flow 2
    watch_file_flow timeline
    watch_file_flow timeline 2
EOF_USAGE
}

MODE="table"
MODE_SEEN=0
INTERACTIVE=0
FORWARD_ARGS=()

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
            ;;
        --interactive)
            INTERACTIVE=1
            ;;
        table|timeline)
            if (( MODE_SEEN )); then
                printf '\033[31mERROR: select only one display mode.\033[0m\n' >&2
                exit 2
            fi
            MODE="$arg"
            MODE_SEEN=1
            ;;
        *)
            FORWARD_ARGS+=("$arg")
            ;;
    esac
done

if [[ ! -x "$ENGINE" ]]; then
    printf '\033[31mERROR: missing executable tracker engine: %s\033[0m\n' "$ENGINE" >&2
    exit 1
fi

render_mode() {
    case "$MODE" in
        table)
            "$ENGINE" "${FORWARD_ARGS[@]}" |
                awk '
                    /RECENT FILE FLOW/ { hidden=1 }
                    !hidden { print }
                '
            ;;
        timeline)
            "$ENGINE" "${FORWARD_ARGS[@]}" |
                awk '
                    found || /RECENT FILE FLOW/ {
                        found=1
                        print
                    }
                ' |
                sed 's/RECENT FILE FLOW/FILE FLOW TIMELINE/'
            ;;
    esac
}

if (( INTERACTIVE == 0 )); then
    render_mode
    exit
fi

if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'Interactive mode requires a terminal.\n' >&2
    exit 2
fi

refresh_seconds="${FILE_FLOW_REFRESH_SECONDS:-2}"
printf '\033[2J\033[H'
while :; do
    frame="$(render_mode)"
    frame+=$'\n\033[2mPress T to switch table/timeline; Q to quit. Current: '"$MODE"$'.\033[0m'
    printf '\033[H%s\033[J' "$frame"
    key=""
    IFS= read -r -s -n 1 -t "$refresh_seconds" key || true
    case "${key,,}" in
        t)
            if [[ "$MODE" == "table" ]]; then MODE="timeline"; else MODE="table"; fi
            ;;
        q|$'\e')
            printf '\033[H\033[2J'
            break
            ;;
    esac
done
