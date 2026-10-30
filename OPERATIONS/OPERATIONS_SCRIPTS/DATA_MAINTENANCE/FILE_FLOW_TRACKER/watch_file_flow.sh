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
FORWARD_ARGS=()

for arg in "$@"; do
    case "$arg" in
        -h|--help)
            usage
            exit 0
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
