#!/bin/bash
# Purpose: Ensure cron log paths.

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
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-${DATAFLOW_ROOT}}"
CRONTAB_FILE="${CRONTAB_FILE:-$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/SETUP/analysis_pc.crontab}"
QUIET=false
CREATE_DIRS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --create-files)
      # Retained for CLI compatibility. Empty cron log files are intentionally
      # no longer created.
      shift
      ;;
    --create-dirs)
      CREATE_DIRS=true
      shift
      ;;
    --quiet)
      QUIET=true
      shift
      ;;
    --crontab-file)
      CRONTAB_FILE="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$CRONTAB_FILE" ]]; then
  echo "Crontab file not found: $CRONTAB_FILE" >&2
  exit 1
fi

created_dirs=0
removed_empty_files=0
removed_empty_dirs=0
while IFS= read -r target; do
  [[ -z "$target" ]] && continue
  [[ "$target" != /* ]] && continue

  log_dir="$(dirname "$target")"
  if $CREATE_DIRS && [[ ! -d "$log_dir" ]]; then
    mkdir -p "$log_dir"
    created_dirs=$((created_dirs + 1))
  fi

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

cron_log_root="$REPO_ROOT/CONTEXTUAL/OPERATIONS/OPERATIONS_RUNTIME/CRON_LOGS"
if [[ -d "$cron_log_root" ]]; then
  while IFS= read -r -d '' empty_path; do
    rm -f "$empty_path"
    removed_empty_files=$((removed_empty_files + 1))
  done < <(find "$cron_log_root" -type f -empty -print0)
  while IFS= read -r -d '' empty_dir; do
    if rmdir "$empty_dir" 2>/dev/null; then
      removed_empty_dirs=$((removed_empty_dirs + 1))
    fi
  done < <(find "$cron_log_root" -depth -mindepth 1 -type d -empty -print0)
fi

if ! $QUIET; then
  echo "ensure_cron_log_paths: created_dirs=$created_dirs empty_log_files_created=0 removed_empty_files=$removed_empty_files removed_empty_dirs=$removed_empty_dirs"
fi
