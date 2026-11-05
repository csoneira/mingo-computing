#!/usr/bin/env bash
# =============================================================================
# DATAFLOW_v3 Script Header v1
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/top_large_dirs.sh
# Purpose: Top large dirs.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/CLEANERS/top_large_dirs.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

if [[ -z "${DATAFLOW_ROOT:-}" ]]; then
  _repo_probe="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  while [[ "$_repo_probe" != "/" && ! -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]]; do
    _repo_probe="$(dirname -- "$_repo_probe")"
  done
  [[ -f "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh" ]] || {
    echo "Could not locate repository root from ${BASH_SOURCE[0]}" >&2
    exit 2
  }
  # shellcheck source=/dev/null
  source "$_repo_probe/CONTEXTUAL/CONFIG/CONTENTS/environment/dataflow.sh"
fi
unset _repo_probe

show_help() {
  cat <<'EOF'
top_large_dirs.sh
Lists the largest directories under the current checkout and .safe-mingo-computing.

Usage:
  top_large_dirs.sh [count] [--depth N]

Options:
  -d, --depth N  Directory depth to inspect below each root (default: 2).
  -h, --help    Show this help message and exit.

Arguments:
  count         Number of entries to show (default: 30).

By default the script runs without sudo and only examines the current checkout
and .safe-mingo-computing under the current user's home.
EOF
}

LIMIT=30
DEPTH=2

while (( $# )); do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -d|--depth)
      if (( $# < 2 )); then
        echo "ERROR: $1 requires a positive integer depth" >&2
        exit 2
      fi
      DEPTH="$2"
      shift 2
      ;;
    --depth=*)
      DEPTH="${1#*=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
    *)
      LIMIT="$1"
      shift
      ;;
  esac
done

if ! [[ "${LIMIT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: count must be a positive integer: ${LIMIT}" >&2
  exit 2
fi

if ! [[ "${DEPTH}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: depth must be a positive integer: ${DEPTH}" >&2
  exit 2
fi

HOME_DIR="${HOME:?HOME is not set}"
SEARCH_ROOTS=(
  "${DATAFLOW_ROOT}"
  "${HOME_DIR}/.safe-mingo-computing"
)

ROOTS=()
for root in "${SEARCH_ROOTS[@]}"; do
  if [[ -d "${root}" ]]; then
    ROOTS+=("${root}")
  else
    echo "Skipping missing directory: ${root}" >&2
  fi
done

if (( ${#ROOTS[@]} == 0 )); then
  echo "No search directories found under ${HOME_DIR}" >&2
  exit 0
fi

echo "Scanning directories to depth ${DEPTH} under: ${ROOTS[*]}" >&2

ENTRIES=()
while IFS= read -r -d '' path; do
  ENTRIES+=("${path}")
done < <(find "${ROOTS[@]}" -xdev -mindepth 1 -maxdepth "${DEPTH}" -type d -print0 2>/dev/null)

if (( ${#ENTRIES[@]} == 0 )); then
  echo "No directories found below the selected roots" >&2
  exit 0
fi

du -xsk -- "${ENTRIES[@]}" 2>/dev/null \
  | sort -nrk1 \
  | awk -v limit="${LIMIT}" '
      NR <= limit {
        path = $0
        sub(/^[0-9]+[[:space:]]+/, "", path)
        printf "%8.2f GiB\t%s\n", $1/1024/1024, path
      }
    '
