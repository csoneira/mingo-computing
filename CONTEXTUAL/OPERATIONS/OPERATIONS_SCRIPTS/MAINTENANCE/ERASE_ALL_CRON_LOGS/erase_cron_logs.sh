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
# Script: CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/ERASE_ALL_CRON_LOGS/erase_cron_logs.sh
# Purpose: Truncate cron log files under CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS.
# Owner: DATAFLOW_v3 contributors
# Sign-off: csoneira <csoneira@ucm.es>
# Last Updated: 2026-03-02
# Runtime: bash
# Usage: bash CONTEXTUAL/OPERATIONS/OPERATIONS_SCRIPTS/MAINTENANCE/ERASE_ALL_CRON_LOGS/erase_cron_logs.sh [options]
# Inputs: CLI args, config files, environment variables, and/or upstream files.
# Outputs: Files, logs, or process-level side effects.
# Notes: Keep behavior configuration-driven and reproducible.
# =============================================================================

# Truncate cron log files under CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS.
set -euo pipefail

usage() {
  cat <<'EOF'
erase_cron_logs.sh [--dry-run] [--keep-lines N] [--log-dir PATH] [--crontab-file PATH]

Keeps only the most recent N lines in cron logs under CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS.
Targets include:
1) files declared as redirection targets in CONTEXTUAL/CONFIG/add_to_crontab.info
2) existing regular files found recursively under the cron log directory

Options:
  --dry-run             Show what would be truncated without editing files.
  --keep-lines N        Number of tail lines to keep per file (default: 1000).
  --log-dir PATH        Cron logs root directory.
  --crontab-file PATH   Crontab source to parse for declared log files.
  -h,--help             Show this help message.
EOF
}

DRY_RUN=false
KEEP_LINES="${CRON_LOG_KEEP_LINES:-1000}"
LOG_DIR="${CRON_LOG_DIR:-${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS}"
CRONTAB_FILE="${CRONTAB_FILE:-${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/analysis_pc.crontab}"

while (( $# > 0 )); do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      ;;
    --keep-lines)
      KEEP_LINES="${2:-}"
      shift
      ;;
    --log-dir)
      LOG_DIR="${2:-}"
      shift
      ;;
    --crontab-file)
      CRONTAB_FILE="${2:-}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ ! "$KEEP_LINES" =~ ^[0-9]+$ ]] || (( KEEP_LINES <= 0 )); then
  echo "--keep-lines must be a positive integer, got: $KEEP_LINES" >&2
  exit 1
fi

if [[ ! -d "$LOG_DIR" ]]; then
  echo "Cron logs directory not found: $LOG_DIR" >&2
  exit 1
fi

if [[ ! -f "$CRONTAB_FILE" ]]; then
  echo "Crontab file not found: $CRONTAB_FILE" >&2
  exit 1
fi

LOCK_FILE="${DATAFLOW_ROOT}/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/LOCKS/cron/truncate_cron_logs.lock"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another cron log truncation run is already in progress."
  exit 0
fi

# The wrapper-owned destination must not be rewritten after output begins, but
# it can be compacted safely here before this script emits its first line.
if [[ -n "${CRON_LOG_PATH:-}" && -f "$CRON_LOG_PATH" ]]; then
  self_line_count="$(wc -l < "$CRON_LOG_PATH" || echo 0)"
  if [[ "$self_line_count" =~ ^[0-9]+$ ]] && (( self_line_count > KEEP_LINES )); then
    self_tmp="$(mktemp "${CRON_LOG_PATH}.truncate.XXXXXX")"
    tail -n "$KEEP_LINES" "$CRON_LOG_PATH" > "$self_tmp"
    cat "$self_tmp" > "$CRON_LOG_PATH"
    rm -f "$self_tmp"
  fi
fi

declare -A files=()
declare -A skip_files=()

# Avoid truncating the file currently receiving script output.
for fd in 1 2; do
  fd_target="$(readlink -f "/proc/$$/fd/$fd" 2>/dev/null || true)"
  if [[ -n "$fd_target" && -f "$fd_target" && "$fd_target" == "$LOG_DIR/"* ]]; then
    skip_files["$fd_target"]=1
  fi
done
skip_files["$LOCK_FILE"]=1
if [[ -n "${CRON_LOG_PATH:-}" ]]; then
  skip_files["$(readlink -f "$CRON_LOG_PATH" 2>/dev/null || printf '%s' "$CRON_LOG_PATH")"]=1
fi

while IFS= read -r target; do
  [[ -z "$target" ]] && continue
  [[ "$target" != /* ]] && continue
  [[ "$target" != "$LOG_DIR/"* ]] && continue
  files["$target"]=1
done < <(
  awk '
    /^[[:space:]]*#/ {next}
    NF == 0 {next}
    {
      for (i = 1; i <= NF; i++) {
        tok = $i
        if (tok ~ /^>>/) {
          p = substr(tok, 3)
          if (p == "") {
            if (i + 1 <= NF) print $(i + 1)
          } else {
            print p
          }
          continue
        }
        if (tok ~ /^>/ && tok !~ /^[0-9]+>/ && tok !~ /^>&/) {
          p = substr(tok, 2)
          if (p == "") {
            if (i + 1 <= NF) print $(i + 1)
          } else {
            print p
          }
        }
        if (tok ~ /\/cron_run_logged\.sh$/ && i + 1 <= NF) {
          print $(i + 1)
        }
      }
    }
  ' "$CRONTAB_FILE" | sort -u
)

while IFS= read -r -d '' path; do
  files["$path"]=1
done < <(find "$LOG_DIR" -type f -print0)

mapfile -t targets < <(printf '%s\n' "${!files[@]}" | sort)

if (( ${#targets[@]} == 0 )); then
  echo "No files found under $LOG_DIR."
  exit 0
fi

checked=0
already_small=0
truncated=0
would_truncate=0
lines_removed=0
skipped=0
errors=0
removed_empty_dirs=0

for path in "${targets[@]}"; do
  if [[ -n "${skip_files[$path]:-}" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  if [[ ! -f "$path" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  if [[ ! -s "$path" ]]; then
    if $DRY_RUN; then
      echo "[DRY-RUN] Would remove empty cron log $path"
      would_truncate=$((would_truncate + 1))
    else
      rm -f "$path"
      echo "Removed empty cron log $path"
      truncated=$((truncated + 1))
    fi
    continue
  fi

  checked=$((checked + 1))
  line_count="$(wc -l < "$path" || echo 0)"
  if [[ ! "$line_count" =~ ^[0-9]+$ ]]; then
    echo "Could not count lines in $path" >&2
    errors=$((errors + 1))
    continue
  fi

  if (( line_count <= KEEP_LINES )); then
    already_small=$((already_small + 1))
    continue
  fi

  removed=$((line_count - KEEP_LINES))
  if $DRY_RUN; then
    echo "[DRY-RUN] Would truncate $path (lines: $line_count -> $KEEP_LINES)"
    would_truncate=$((would_truncate + 1))
    lines_removed=$((lines_removed + removed))
    continue
  fi

  tmp_file="$(mktemp "${path}.truncate.XXXXXX")"
  if ! tail -n "$KEEP_LINES" "$path" > "$tmp_file"; then
    rm -f "$tmp_file"
    echo "Failed to collect tail lines for $path" >&2
    errors=$((errors + 1))
    continue
  fi
  if ! cat "$tmp_file" > "$path"; then
    rm -f "$tmp_file"
    echo "Failed to write truncated content to $path" >&2
    errors=$((errors + 1))
    continue
  fi
  rm -f "$tmp_file"

  echo "Truncated $path (lines: $line_count -> $KEEP_LINES)"
  truncated=$((truncated + 1))
  lines_removed=$((lines_removed + removed))
done

if ! $DRY_RUN; then
  while IFS= read -r -d '' empty_dir; do
    if rmdir "$empty_dir" 2>/dev/null; then
      removed_empty_dirs=$((removed_empty_dirs + 1))
    fi
  done < <(find "$LOG_DIR" -depth -mindepth 1 -type d -empty -print0)
fi

if $DRY_RUN; then
  echo "Summary (dry-run): checked=$checked would_truncate=$would_truncate already_small=$already_small skipped=$skipped lines_to_remove=$lines_removed errors=$errors"
else
  echo "Summary: checked=$checked truncated=$truncated already_small=$already_small skipped=$skipped lines_removed=$lines_removed removed_empty_dirs=$removed_empty_dirs errors=$errors"
fi
