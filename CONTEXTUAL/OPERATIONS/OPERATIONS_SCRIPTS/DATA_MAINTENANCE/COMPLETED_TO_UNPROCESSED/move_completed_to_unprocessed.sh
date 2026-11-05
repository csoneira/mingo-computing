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
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/COMPLETED_TO_UNPROCESSED/move_completed_to_unprocessed.sh
# Purpose: Move completed to unprocessed.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/DATA_MAINTENANCE/COMPLETED_TO_UNPROCESSED/move_completed_to_unprocessed.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: move_completed_to_unprocessed.sh [OPTIONS] [BASE_DIR ...]

Search each BASE_DIR (default: repository root) for directories named COMPLETED
and move every file they contain into the sibling UNPROCESSED directory.
Files are skipped when the UNPROCESSED directory is missing or a naming
collision would overwrite an existing file. Multiple base directories can be
provided and will be processed sequentially.

Options:
  -p, --preview   Print a formatted list of planned moves per directory.
  -n, --dry-run   Preview moves without moving any files (implies --preview).
  -h, --help      Show this help message and exit.

Configuration:
  When no BASE_DIR arguments are provided, directories listed in
  move_completed_to_unprocessed_config.txt (same directory as this script)
  are used. If the file is missing or matches nothing, the repository root
  becomes the fallback base directory.
EOF
}

PREVIEW=0
DRY_RUN=0
BASE_DIRS=()
SKIP_PATTERNS=(
  "${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/LOG_DATA"
  "${DATAFLOW_ROOT}/PIPELINE/MINGO_ANALYSIS/MINGO_ANALYSIS_STATIONS/MINGO0*/STAGE_1/LOG_DATA/*"
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/move_completed_to_unprocessed_config.txt"
DEFAULT_BASE="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

declare -a CONFIG_PATTERNS=()
declare -a CONFIG_BASE_DIRS=()

load_config_base_dirs() {
  [[ -f "$CONFIG_FILE" ]] || return

  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    local line="$raw_line"
    line="${line%%#*}"
    line="${line%"${line##*[![:space:]]}"}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" ]] && continue
    CONFIG_PATTERNS+=("$line")
  done < "$CONFIG_FILE"

  local pattern
  for pattern in "${CONFIG_PATTERNS[@]}"; do
    local matches=()
    while IFS= read -r match; do
      matches+=("$match")
    done < <(compgen -G "$pattern" || true)

    if ((${#matches[@]} == 0)); then
      echo "Config pattern matched no directories: $pattern" >&2
      continue
    fi

    local candidate
    for candidate in "${matches[@]}"; do
      if [[ -d "$candidate" ]]; then
        CONFIG_BASE_DIRS+=("$candidate")
      else
        echo "Config match is not a directory, skipping: $candidate" >&2
      fi
    done
  done

  if ((${#CONFIG_BASE_DIRS[@]} > 1)); then
    local -A seen=()
    local -a unique=()
    local dir
    for dir in "${CONFIG_BASE_DIRS[@]}"; do
      if [[ -n ${seen["$dir"]+_} ]]; then
        continue
      fi
      seen["$dir"]=1
      unique+=("$dir")
    done
    CONFIG_BASE_DIRS=("${unique[@]}")
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--preview)
      PREVIEW=1
      shift
      ;;
    -n|--dry-run)
      PREVIEW=1
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      BASE_DIRS+=("$@")
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      BASE_DIRS+=("$1")
      shift
      ;;
  esac
done

load_config_base_dirs
if ((${#BASE_DIRS[@]} == 0)); then
  if ((${#CONFIG_BASE_DIRS[@]} > 0)); then
    BASE_DIRS=("${CONFIG_BASE_DIRS[@]}")
    echo "Using ${#BASE_DIRS[@]} base director$( (( ${#BASE_DIRS[@]} == 1 )) && printf 'y' || printf 'ies') from config: $CONFIG_FILE"
  else
    BASE_DIRS=("$DEFAULT_BASE")
  fi
fi

shopt -s nullglob dotglob

files_moved=0
files_skipped=0
missing_targets=0
found_completed=0

for BASE_DIR in "${BASE_DIRS[@]}"; do
  if [[ ! -d "$BASE_DIR" ]]; then
    echo "Base directory not found: $BASE_DIR" >&2
    exit 1
  fi

  mapfile -t COMPLETED_DIRS < <(find "$BASE_DIR" -type d \( -name COMPLETED -o -name COMPLETED_DIRECTORY \) | sort)

  if ((${#COMPLETED_DIRS[@]} == 0)); then
    echo "No COMPLETED directories found under $BASE_DIR"
    continue
  fi

  found_completed=1

  for completed_dir in "${COMPLETED_DIRS[@]}"; do
    completed_name="$(basename "$completed_dir")"
    case "$completed_name" in
      COMPLETED) target_name="UNPROCESSED" ;;
      COMPLETED_DIRECTORY) target_name="UNPROCESSED_DIRECTORY" ;;
      *)
        target_name="${completed_name/COMPLETED/UNPROCESSED}"
        ;;
    esac
    skip_match=""
    for skip_pattern in "${SKIP_PATTERNS[@]}"; do
      [[ -z "$skip_pattern" ]] && continue
      if [[ "$completed_dir" == $skip_pattern ]]; then
        skip_match="$skip_pattern"
        break
      fi
    done
    if [[ -n "$skip_match" ]]; then
      echo "Skipping $completed_dir (inside excluded path: $skip_match)"
      continue
    fi

    target_dir="$(dirname "$completed_dir")/$target_name"

    if ((PREVIEW)); then
      echo
      echo "=== COMPLETED directory ==="
      echo "  $completed_dir"
      echo "  -> $target_dir"
    fi

    if [[ ! -d "$target_dir" ]]; then
      ((missing_targets+=1))
      echo "Skipping $completed_dir (missing UNPROCESSED directory)" >&2
      continue
    fi

    entries=("$completed_dir"/*)
    if ((${#entries[@]} == 0)); then
      echo "No files to move in $completed_dir"
      continue
    fi

    for entry in "${entries[@]}"; do
      if [[ ! -f "$entry" ]]; then
        continue
      fi

      filename="$(basename "$entry")"
      destination="$target_dir/$filename"

      if [[ -e "$destination" ]]; then
        ((files_skipped+=1))
        echo "Skipping $entry (destination exists)" >&2
        continue
      fi

      if ((PREVIEW)); then
        printf '    - %s -> %s\n' "$filename" "$destination"
      fi

      if ((DRY_RUN)); then
        echo "DRY RUN: would move $entry -> $destination"
        continue
      fi

      mv "$entry" "$destination"
      ((files_moved+=1))
      echo "Moved $entry -> $destination"
    done
  done
done

if (( ! found_completed )); then
  echo "No COMPLETED directories found in the provided base directories."
  exit 0
fi

if ((DRY_RUN)); then
  echo "Dry run complete. No files were moved."
fi

echo "Finished. Files moved: $files_moved, skipped: $files_skipped, missing UNPROCESSED dirs: $missing_targets."
